from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from accounts import storage as accounts_storage
from accounts.models import AuditLog, RoleApprovalLog, User
from applicant_dashboard import oversight
from applicant_dashboard import storage as application_storage
from applicant_dashboard.models import (
    POSTAPPROVAL_FIELDS,
    POSTAPPROVAL_LIST_LABELS,
    POSTAPPROVAL_TITLES,
    Application,
    PostApprovalSubmission,
)
from communications import services as communications_services
from communications.emails_preview import render_template_preview
from communications.models import Announcement, AudienceChoices, EmailTemplate, Reminder
from meetings import services as meetings_services
from meetings.models import AgendaItem, Decision, Meeting, MeetingMinutes, MeetingParticipant
from messaging.access import is_staff_side
from notifications import services as notification_services
from notifications.emails import send_branded_email
from notifications.models import Notification
from payments import fees
from payments import services as payment_services
from pages import committee_services
from pages import documents_storage
from pages import storage as pages_storage
from pages.models import (
    GOVERNANCE_TAG_CHOICES,
    GOVERNANCE_TITLE_CHOICES,
    CommitteeAppointment,
    ConflictDeclaration,
    GovernanceMember,
    Inquiry,
    TrainingRecord,
)
from reviewer_dashboard.models import ReviewAssignment

from . import reports as reports_data

staff_required = user_passes_test(is_staff_side, login_url="pages:login")


def parse_datetime_local(value):
    """Parses an <input type="datetime-local"> value ("YYYY-MM-DDTHH:MM")
    into a timezone-aware datetime in the server's current timezone --
    that input has no timezone of its own, so naive-vs-aware is resolved
    once, here, rather than at every call site."""
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def parse_date_as_datetime(value, *, end_of_day=False):
    """Same idea as parse_datetime_local, for the plain <input type="date">
    fields on Announcements (a start/expiry day, not a specific time)."""
    day = parse_date(value or "")
    if day is None:
        return None
    naive = timezone.datetime.combine(day, timezone.datetime.max.time() if end_of_day else timezone.datetime.min.time())
    return timezone.make_aware(naive)


REVIEWER_DIRECTORY_TABS = {"all", "available", "limited", "unavailable"}
REVIEWER_ASSIGNMENT_TABS = {"assign", "pending", "completed", "workload"}


@login_required
@staff_required
def home(request):
    base_qs = oversight.staff_queryset()
    counts = {
        "submitted": base_qs.filter(status=Application.Status.SUBMITTED).count(),
        "under_review": base_qs.filter(status=Application.Status.UNDER_REVIEW).count(),
        "revisions": base_qs.filter(status=Application.Status.REVISIONS_REQUIRED).count(),
        "approved": base_qs.filter(status=Application.Status.APPROVED).count(),
        # The stats strip is a 5-up grid (see .stats-grid) -- Pending
        # Assignments is the fifth card, reusing the same "open" definition
        # as the Reviewer Assignment page's own Pending tab (_open_assignments).
        "pending_assignments": _open_assignments().count(),
    }
    submitted_qs = base_qs.filter(status=Application.Status.SUBMITTED)
    recent_submissions = submitted_qs.order_by("-submitted_at")[:8]
    oldest_submission = submitted_qs.order_by("submitted_at").first()

    recent_activity = list(AuditLog.objects.select_related("actor").order_by("-created_at")[:6])
    for log in recent_activity:
        log.category = _audit_log_category(log.action)

    return render(request, "dashboards/secretariat.html", {
        "counts": counts,
        "recent_submissions": recent_submissions,
        "oldest_submission": oldest_submission,
        "recent_activity": recent_activity,
        "notifications": notification_services.for_user(request.user, Notification.Audience.SECRETARIAT, limit=6),
        "unread_count": notification_services.unread_count(request.user, Notification.Audience.SECRETARIAT),
    })


@login_required
@staff_required
def applications(request):
    active_tab = request.GET.get("tab", "all")
    if active_tab not in oversight.STATUS_TABS:
        active_tab = "all"

    base_qs = oversight.staff_queryset().order_by("-submitted_at").prefetch_related(
        Prefetch(
            "review_assignments",
            queryset=ReviewAssignment.objects.select_related("reviewer").order_by("-assigned_at"),
        )
    )
    counts = oversight.status_counts(base_qs)

    all_applications = list(base_qs)
    for application in all_applications:
        application.tab = oversight.STATUS_TO_TAB.get(application.status, "all")
        # .all() reads the Prefetch above instead of re-querying per card --
        # this is what keeps the "reviewer, deadline & stage" modal button
        # on every card from turning into an N+1.
        application.assignments = list(application.review_assignments.all())
        # Surfaced directly on the card (not just inside the Reviewer &
        # Stage modal) so a reviewer's finished assessment is visible at a
        # glance instead of requiring an extra click to discover.
        completed = [a for a in application.assignments if a.status == ReviewAssignment.Status.COMPLETED]
        application.has_completed_review = bool(completed)
        # Most-recently-completed first -- with multiple reviewers, the
        # card only has room for one name, and the latest decision is the
        # one most likely to be what the Secretariat is waiting on.
        application.completed_reviewers = sorted(completed, key=lambda a: a.completed_at, reverse=True)

    return render(request, "dashboards/secretariat/applications.html", {
        "all_applications": all_applications,
        "counts": counts,
        "active_tab": active_tab,
    })


@login_required
@staff_required
def applications_counts(request):
    """Polled by live-counts.js to keep the Applications tab badges and
    summary strip current without a page reload -- e.g. a second staff
    member moves something to Under Review while this page is still open."""
    return JsonResponse(oversight.status_counts(oversight.staff_queryset()))


def _send_deadline_updated_email(request, assignment):
    login_url = request.build_absolute_uri(reverse("pages:login"))
    ref = f"\"{assignment.application.title}\" ({assignment.application.reference_no or 'reference pending'})"
    if assignment.due_date:
        change_line = f"The MSREC Secretariat has updated the due date for your review of {ref} to {assignment.due_date:%d %b %Y}."
    else:
        change_line = f"The MSREC Secretariat has removed the due date for your review of {ref} -- no deadline is set right now."
    return send_branded_email(
        subject=f"Review deadline updated — {assignment.application.reference_no or assignment.application.title}",
        to=assignment.reviewer.email,
        heading="Your review deadline has changed",
        paragraphs=[f"Hi {assignment.reviewer.full_name},", change_line],
        cta_text="Log in to MSREC",
        cta_url=login_url,
        preheader="Your review deadline has been updated.",
    )


@login_required
@staff_required
def set_reviewer_deadline(request):
    """Sets/changes/clears the due date on one existing ReviewAssignment --
    the "set a deadline for him" half of the Applications list's small
    Reviewer & Stage modal button. Deliberately its own tiny endpoint
    rather than reusing reviewer_assignment()'s POST branch: that view's
    "assign"/"withdraw" actions redirect back to the Reviewer Assignment
    page, but this modal lives on the Applications page and needs to
    redirect back there instead."""
    if request.method != "POST":
        return redirect("secretariat_dashboard:applications")

    tab = request.POST.get("tab", "all")
    redirect_url = f"{reverse('secretariat_dashboard:applications')}?tab={tab}"

    assignment_id = request.POST.get("assignment_id", "")
    if not assignment_id.isdigit():
        messages.error(request, "That request could not be processed.")
        return redirect(redirect_url)

    assignment = get_object_or_404(
        ReviewAssignment.objects.select_related("application", "reviewer"), pk=assignment_id,
    )
    assignment.due_date = parse_date(request.POST.get("due_date") or "") or None
    assignment.save(update_fields=["due_date"])

    emailed = _send_deadline_updated_email(request, assignment)
    ref = assignment.application.reference_no or assignment.application.title
    if assignment.due_date:
        note = f"Deadline for {assignment.reviewer.full_name} on {ref} set to {assignment.due_date:%d %b %Y}"
    else:
        note = f"Deadline for {assignment.reviewer.full_name} on {ref} cleared"
    note += " and they've been notified by email." if emailed else " (the notification email couldn't be sent)."
    messages.success(request, note)
    return redirect(redirect_url)


# One entry per "Review Pathways" sidebar link/URL -- the pathway an
# application is actually reviewed under (Application.review_type),
# which MSREC assigns during screening rather than the applicant
# choosing it (see applicant_dashboard.models.Application.
# fee_for_application's docstring). Order matches the sidebar.
PATHWAY_META = {
    "exemption": {
        "label": "Determination / Exemption",
        "short_label": "Determination",
        "description": (
            "For submissions where the first question is whether formal ethical review is even "
            "required, or whether the study's risk profile qualifies it for exemption. This is a "
            "flat-rate, fastest-turnaround pathway -- a Secretariat determination, not a full review."
        ),
        "criteria": [
            "No more than minimal risk to participants",
            "Uses only existing, de-identified data, or purely observational methods",
            "Falls within a category MSREC's policy recognizes as exempt",
        ],
        "icon": '<path d="m5 13 4 4L19 7"/>',
    },
    "expedited": {
        "label": "Expedited Review",
        "short_label": "Expedited",
        "description": (
            "For minimal-risk studies that meet MSREC's expedited criteria. One or two assigned "
            "reviewers evaluate it directly, without waiting on a full Committee meeting -- same "
            "assessment domains as a full review, on a shorter clock."
        ),
        "criteria": [
            "Minimal risk, with a well-established, low-risk methodology",
            "No vulnerable populations without an already-approved safeguard",
            "No more than minor changes to a previously approved protocol",
        ],
        "icon": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8Z"/>',
    },
    "full": {
        "label": "Full Committee Review",
        "short_label": "Full Committee",
        "description": (
            "For studies presenting more than minimal risk, or raising complex ethical, privacy or "
            "vulnerability considerations. Requires deliberation and a quorate decision at a "
            "scheduled Committee meeting, not a single reviewer's sign-off."
        ),
        "criteria": [
            "More than minimal risk, or a vulnerable participant population",
            "Novel, sensitive or ethically complex methodology",
            "Anything the Secretariat isn't confident qualifies for a faster pathway",
        ],
        "icon": '<circle cx="9" cy="7" r="4"/><path d="M2 21v-2a5 5 0 0 1 5-5h2a5 5 0 0 1 5 5v2"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/><path d="M22 21v-2a4 4 0 0 0-3-3.85"/>',
    },
}


def _pathway_card_list(qs):
    applications_list = list(qs.order_by("-submitted_at"))
    for application in applications_list:
        application.tab = oversight.STATUS_TO_TAB.get(application.status, "all")
    return applications_list


@login_required
@staff_required
def review_pathway(request, pathway):
    meta = PATHWAY_META.get(pathway)
    if meta is None:
        return HttpResponse(status=404)

    if request.method == "POST":
        action = request.POST.get("action")
        application = get_object_or_404(oversight.staff_queryset(), pk=request.POST.get("application_id"))
        if action == "assign_pathway":
            application.review_type = pathway
            application.save(update_fields=["review_type"])
            AuditLog.record(
                request.user, "application.assign_pathway", target=application,
                description=f"Routed to {meta['label']}",
            )
            messages.success(request, f'"{application.title}" was routed to {meta["label"]}.')
        elif action == "unassign_pathway":
            application.review_type = ""
            application.save(update_fields=["review_type"])
            AuditLog.record(
                request.user, "application.assign_pathway", target=application,
                description="Pathway assignment cleared",
            )
            messages.success(request, f'"{application.title}" was moved back to awaiting assignment.')
        else:
            messages.error(request, "That request could not be processed.")
        return redirect("secretariat_dashboard:review_pathway", pathway=pathway)

    base_qs = oversight.staff_queryset()
    unassigned_applications = _pathway_card_list(base_qs.filter(review_type=""))
    assigned_applications = _pathway_card_list(base_qs.filter(review_type=pathway))

    return render(request, "dashboards/secretariat/review_pathway.html", {
        "pathway": pathway,
        "meta": meta,
        "unassigned_applications": unassigned_applications,
        "assigned_applications": assigned_applications,
        "unassigned_count": len(unassigned_applications),
        "assigned_count": len(assigned_applications),
    })


# ---------------------------------------------------------------------
# Post-Approval Management
# ---------------------------------------------------------------------

# The one form_data field, if any, worth its own column on a type's list
# page -- everything else only shows up inside the Review modal. Mirrors
# what the applicant-side list pages already single out (e.g.
# postapproval-amendments.html's "Amendment Type" column).
POSTAPPROVAL_HIGHLIGHT = {
    PostApprovalSubmission.Type.AMENDMENT: ("amendment_type", "Type"),
    PostApprovalSubmission.Type.PROGRESS_REPORT: ("period", "Period"),
    PostApprovalSubmission.Type.ADVERSE_EVENT: ("severity", "Severity"),
    PostApprovalSubmission.Type.DEVIATION: ("deviation_type", "Type"),
    PostApprovalSubmission.Type.CLOSURE: ("completion_date", "Completed"),
}


@login_required
@staff_required
def post_approval(request, ptype):
    if ptype not in PostApprovalSubmission.Type.values:
        return HttpResponse(status=404)

    type_title = POSTAPPROVAL_TITLES[ptype]

    if request.method == "POST":
        submission = get_object_or_404(PostApprovalSubmission, pk=request.POST.get("submission_id"), type=ptype)
        new_status = request.POST.get("status")
        if new_status not in PostApprovalSubmission.Status.values:
            messages.error(request, "Choose a valid status.")
            return redirect("secretariat_dashboard:post_approval", ptype=ptype)

        submission.status = new_status
        submission.secretariat_note = request.POST.get("secretariat_note", "").strip()
        update_fields = ["status", "secretariat_note"]
        if new_status in (PostApprovalSubmission.Status.APPROVED, PostApprovalSubmission.Status.ACKNOWLEDGED):
            submission.decided_at = timezone.now()
            update_fields.append("decided_at")
        submission.save(update_fields=update_fields)

        AuditLog.record(
            request.user, "application.postapproval_status", target=submission.application,
            description=f"{type_title} set to {submission.get_status_display()}",
        )
        messages.success(request, f'{type_title} for "{submission.application.title}" set to {submission.get_status_display()}.')
        return redirect("secretariat_dashboard:post_approval", ptype=ptype)

    field_defs = POSTAPPROVAL_FIELDS[ptype]
    highlight_key, highlight_label = POSTAPPROVAL_HIGHLIGHT.get(ptype, (None, None))

    submissions = list(
        PostApprovalSubmission.objects.filter(type=ptype)
        .select_related("application", "applicant").order_by("-submitted_at")
    )
    counts = {"all": len(submissions)}
    for status_key, _label in PostApprovalSubmission.Status.choices:
        counts[status_key] = 0
    for submission in submissions:
        counts[submission.status] += 1
        submission.detail_rows = [
            {"label": label, "value": submission.form_data.get(key, "")}
            for key, label, _widget, _choices in field_defs
        ]
        submission.highlight_value = submission.form_data.get(highlight_key, "") if highlight_key else ""

    return render(request, "dashboards/secretariat/post_approval.html", {
        "ptype": ptype,
        "type_label": POSTAPPROVAL_LIST_LABELS[ptype],
        "type_title": type_title,
        "submissions": submissions,
        "counts": counts,
        "status_choices": PostApprovalSubmission.Status.choices,
        "highlight_label": highlight_label,
    })


_CONCERN_REASONS = [Inquiry.Reason.COMPLAINTS, Inquiry.Reason.ETHICS_CONCERNS]


@login_required
@staff_required
def post_approval_complaints(request):
    if request.method == "POST":
        concern = get_object_or_404(Inquiry.objects.filter(reason__in=_CONCERN_REASONS), pk=request.POST.get("inquiry_id"))
        action = request.POST.get("action")

        if action == "reply":
            reply_message = request.POST.get("reply_message", "").strip()
            if not reply_message:
                messages.error(request, "Write a reply message before sending.")
            else:
                concern.reply_message = reply_message
                concern.replied_at = timezone.now()
                concern.replied_by = request.user
                concern.status = Inquiry.Status.RESOLVED
                concern.resolved_at = concern.replied_at
                concern.save(update_fields=["reply_message", "replied_at", "replied_by", "status", "resolved_at"])
                emailed = send_branded_email(
                    subject=f"Re: Your message to MSREC ({concern.get_reason_display()})",
                    to=concern.email,
                    heading=f"Hi {concern.name},",
                    paragraphs=[reply_message],
                    quote_label=f"Your original message ({concern.created_at:%d %b %Y})",
                    quote_text=concern.message,
                    preheader=reply_message[:120],
                )
                if emailed:
                    messages.success(request, f"Reply sent to {concern.name} ({concern.email}).")
                else:
                    messages.error(request, f"Reply saved, but the email to {concern.email} couldn't be sent -- check the email settings.")
        elif action == "resolve":
            concern.status = Inquiry.Status.RESOLVED
            concern.resolved_at = timezone.now()
            concern.save(update_fields=["status", "resolved_at"])
            messages.success(request, "Marked as resolved.")
        elif action == "reopen":
            concern.status = Inquiry.Status.NEW
            concern.resolved_at = None
            concern.save(update_fields=["status", "resolved_at"])
            messages.success(request, "Reopened.")
        else:
            messages.error(request, "That request could not be processed.")
        return redirect("secretariat_dashboard:post_approval_complaints")

    concerns = list(
        Inquiry.objects.filter(reason__in=_CONCERN_REASONS).select_related("replied_by").order_by("-created_at")
    )
    counts = {"all": len(concerns), "new": 0, "resolved": 0}
    for concern in concerns:
        counts[concern.status] += 1

    return render(request, "dashboards/secretariat/post_approval_complaints.html", {
        "concerns": concerns,
        "counts": counts,
    })


# ---------------------------------------------------------------------
# Document Templates -- read-only, printable letters generated live
# from the record they describe, the same "no stored file, print-to-
# PDF covers download" approach applicant_dashboard.application_letter
# already uses for an applicant's own copy of a decision/approval
# letter (see templates/dashboards/applicant/letter.html). These pages
# are how the Secretariat browses and reprints any letter ever
# generated, across every applicant -- not a separate editable-
# template system with its own content to maintain.
# ---------------------------------------------------------------------

DOCUMENT_LETTER_META = {
    "decision": {
        "label": "Decision Letters",
        "note": "Every reviewed application's decision letter -- approved, not approved, or revisions required.",
    },
    "approval": {
        "label": "Approval Letters",
        "note": "The formal approval letter for every approved study.",
    },
    "amendment": {
        "label": "Amendment Letters",
        "note": "The outcome letter for every decided amendment request.",
    },
    "continuing_review": {
        "label": "Continuing Review Letters",
        "note": "The outcome letter for every decided continuing review.",
    },
    "closure": {
        "label": "Closure Letters",
        "note": "The acknowledgement letter for every decided study closure.",
    },
}

_DECISION_LETTER_STATUSES = (
    Application.Status.REVISIONS_REQUIRED, Application.Status.APPROVED, Application.Status.NOT_APPROVED,
)
_POSTAPPROVAL_LETTER_STATUSES = (
    PostApprovalSubmission.Status.ACTION_REQUIRED,
    PostApprovalSubmission.Status.APPROVED,
    PostApprovalSubmission.Status.ACKNOWLEDGED,
)


@login_required
@staff_required
def document_letters(request, doc_type):
    meta = DOCUMENT_LETTER_META.get(doc_type)
    if meta is None:
        return HttpResponse(status=404)

    if doc_type in ("decision", "approval"):
        statuses = _DECISION_LETTER_STATUSES if doc_type == "decision" else (Application.Status.APPROVED,)
        applications = list(oversight.staff_queryset().filter(status__in=statuses).order_by("-decided_at"))
        rows = [
            {
                "pk": a.pk, "ref_no": a.reference_no, "study_title": a.title,
                "applicant_name": a.applicant.full_name,
                "letter_date": a.decided_at or a.revision_requested_at,
                "status_display": a.get_status_display(),
            }
            for a in applications
        ]
    else:
        submissions = list(
            PostApprovalSubmission.objects.filter(type=doc_type, status__in=_POSTAPPROVAL_LETTER_STATUSES)
            .select_related("application", "applicant").order_by("-decided_at")
        )
        rows = [
            {
                "pk": s.pk, "ref_no": s.application.reference_no, "study_title": s.application.title,
                "applicant_name": s.applicant.full_name, "letter_date": s.decided_at,
                "status_display": s.get_status_display(),
            }
            for s in submissions
        ]

    return render(request, "dashboards/secretariat/document_letters.html", {
        "doc_type": doc_type,
        "meta": meta,
        "rows": rows,
    })


@login_required
@staff_required
def document_letter_view(request, doc_type, pk):
    meta = DOCUMENT_LETTER_META.get(doc_type)
    if meta is None:
        return HttpResponse(status=404)

    if doc_type in ("decision", "approval"):
        statuses = _DECISION_LETTER_STATUSES if doc_type == "decision" else (Application.Status.APPROVED,)
        application = get_object_or_404(oversight.staff_queryset(), pk=pk, status__in=statuses)
        return render(request, "dashboards/secretariat/letter.html", {
            "doc_type": doc_type,
            "meta": meta,
            "application": application,
            "submission": None,
            "letter_date": application.decided_at or application.revision_requested_at,
            "review_type_label": fees.label_for(application.review_type),
        })

    submission = get_object_or_404(
        PostApprovalSubmission.objects.select_related("application", "applicant"),
        pk=pk, type=doc_type, status__in=_POSTAPPROVAL_LETTER_STATUSES,
    )
    return render(request, "dashboards/secretariat/letter.html", {
        "doc_type": doc_type,
        "meta": meta,
        "submission": submission,
        "letter_date": submission.decided_at,
        "application": submission.application,
    })


@login_required
@staff_required
def application_detail(request, pk):
    application = get_object_or_404(oversight.staff_queryset(), pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        comment = request.POST.get("revision_comment", "")
        ok, note = oversight.apply_transition(application, action, comment=comment, actor=request.user)
        if ok and action == "request_revisions":
            emailed = oversight.send_revisions_requested_email(request, application)
            note += " Applicant notified by email." if emailed else " (the notification email couldn't be sent)."
        (messages.success if ok else messages.error)(request, note)
        return redirect("secretariat_dashboard:application_detail", pk=application.pk)

    application.tab = oversight.STATUS_TO_TAB.get(application.status, "all")

    documents = [
        {**doc, "url": application_storage.public_url(doc.get("path"))}
        for doc in (application.documents or [])
    ]

    assignments = list(
        application.review_assignments.select_related("reviewer").order_by("-assigned_at")
    )

    return render(request, "dashboards/secretariat/application_detail.html", {
        "application": application,
        "documents": documents,
        "assignments": assignments,
    })


FINANCE_TABS = {"all", "success", "pending", "failed"}


@login_required
@staff_required
def finance(request):
    active_tab = request.GET.get("tab", "all")
    if active_tab not in FINANCE_TABS:
        active_tab = "all"

    query = request.GET.get("q", "").strip()
    date_from_raw = request.GET.get("date_from", "")
    date_to_raw = request.GET.get("date_to", "")
    date_from = payment_services.parse_filter_date(date_from_raw)
    date_to = payment_services.parse_filter_date(date_to_raw)

    scoped_qs = payment_services.filter_payments(
        payment_services.all_payments(), query=query, date_from=date_from, date_to=date_to,
    )
    counts = payment_services.status_counts(scoped_qs)
    total_collected = payment_services.total_collected(scoped_qs)

    filtered_qs = scoped_qs if active_tab == "all" else scoped_qs.filter(status=active_tab)

    if request.GET.get("export") == "csv":
        return payment_services.export_payments_csv(filtered_qs)

    return render(request, "dashboards/secretariat/finance.html", {
        "all_payments": list(filtered_qs),
        "counts": counts,
        "active_tab": active_tab,
        "total_collected": total_collected,
        "fee_schedule": payment_services.fee_schedule_rows(),
        "query": query,
        "date_from": date_from_raw,
        "date_to": date_to_raw,
        "has_active_filters": bool(query or date_from_raw or date_to_raw),
    })


def _approved_reviewers():
    # Only accounts an admin has actually approved as Reviewer belong in
    # the directory -- a pending or rejected request is not a reviewer
    # yet (see accounts.models.User.approve_role, which is the only place
    # reviewer_status becomes "approved").
    return User.objects.filter(
        role=User.Role.REVIEWER, reviewer_status=User.RequestStatus.APPROVED
    ).order_by("first_name", "last_name")


@login_required
@staff_required
def reviewer_directory(request):
    if request.method == "POST":
        target = get_object_or_404(
            User, pk=request.POST.get("user_id"),
            role=User.Role.REVIEWER, reviewer_status=User.RequestStatus.APPROVED,
        )
        availability = request.POST.get("availability", "")
        if availability in User.Availability.values:
            target.reviewer_availability = availability
            target.save(update_fields=["reviewer_availability"])
            messages.success(
                request,
                f"{target.full_name}'s availability set to {target.get_reviewer_availability_display()}.",
            )
        else:
            messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}?tab={request.POST.get('tab', 'all')}")

    reviewers = list(_approved_reviewers())
    counts = {"all": len(reviewers), "available": 0, "limited": 0, "unavailable": 0}
    for r in reviewers:
        counts[r.reviewer_availability] += 1
        r.cv_url = accounts_storage.create_signed_url(r.reviewer_profile.get("cv_path"))

    active_tab = request.GET.get("tab", "all")
    if active_tab not in REVIEWER_DIRECTORY_TABS:
        active_tab = "all"

    return render(request, "dashboards/secretariat/reviewer-directory.html", {
        "reviewers": reviewers,
        "counts": counts,
        "active_tab": active_tab,
    })


@login_required
@staff_required
def reviewer_directory_counts(request):
    """Polled by live-counts.js -- the Reviewer Directory's own counts,
    same idea as applications_counts (e.g. the secretariat changes
    someone's availability in one tab while this page is open in
    another)."""
    reviewers = _approved_reviewers()
    counts = {"all": reviewers.count(), "available": 0, "limited": 0, "unavailable": 0}
    for availability in reviewers.values_list("reviewer_availability", flat=True):
        counts[availability] += 1
    return JsonResponse(counts)


@login_required
@staff_required
def reviewer_assignment_history(request):
    # "Assignment History" here means the Reviewer role's own audit trail
    # -- who was approved/rejected as a Reviewer, when, and by whom (see
    # accounts.models.RoleApprovalLog, written by admin_dashboard's
    # Accounts page every time an admin acts on a request). Assigning a
    # *reviewer to an application* is the separate "Reviewer Assignment"
    # page below (reviewer_assignment / ReviewAssignment) -- different
    # feature, different "Reviewers" sidebar entry from this one.
    logs = (
        RoleApprovalLog.objects.filter(role=User.Role.REVIEWER)
        .select_related("user", "acted_by")
        .order_by("-created_at")
    )
    return render(request, "dashboards/secretariat/reviewer-assignment-history.html", {
        "logs": logs,
    })


def _open_assignments():
    """Every assignment still "in play" -- not yet completed, and not a
    reviewer's declined "no". Excluding completed here (rather than in
    every caller) is what keeps a reviewer's finished work off both the
    "needs a reviewer" exclusion list and the Pending Assignments tab."""
    return ReviewAssignment.objects.exclude(
        status__in=[ReviewAssignment.Status.COMPLETED, ReviewAssignment.Status.DECLINED]
    )


def _needs_assignment_qs():
    # Under Review is the point an application is actually being
    # evaluated, so that's when it needs a reviewer -- and once every
    # reviewer on it has finished (or it hasn't been assigned at all),
    # it belongs on the Assign Reviewer tab. Excludes anything that
    # already has an open (not completed/declined) assignment, so a
    # study already out for review doesn't get assigned a second time
    # by mistake -- adding a second reviewer to one still happens, just
    # from that application's row once it already shows an assignment.
    assigned_ids = _open_assignments().values_list("application_id", flat=True)
    return (
        oversight.staff_queryset()
        .filter(status=Application.Status.UNDER_REVIEW)
        .exclude(pk__in=assigned_ids)
        .order_by("submitted_at")
    )


def _send_assignment_email(request, assignment):
    login_url = request.build_absolute_uri(reverse("pages:login"))
    due_text = f" by {assignment.due_date:%d %b %Y}" if assignment.due_date else ""
    return send_branded_email(
        subject=f"New review assignment — {assignment.application.reference_no or assignment.application.title}",
        to=assignment.reviewer.email,
        heading="You've been assigned a new review",
        paragraphs=[
            f"Hi {assignment.reviewer.full_name},",
            f"The MSREC Secretariat has assigned you to review \"{assignment.application.title}\" "
            f"({assignment.application.reference_no or 'reference pending'}), due for a decision"
            f"{due_text}.",
            "Log in to My Reviews to accept it and get started.",
        ],
        cta_text="Log in to MSREC",
        cta_url=login_url,
        preheader="You've been assigned a new application to review.",
    )


@login_required
@staff_required
def reviewer_assignment(request):
    if request.method == "POST":
        action = request.POST.get("action")
        tab = request.POST.get("tab", "assign")

        if action == "assign":
            # request.POST.get(...) is '' (never None) when a field posts
            # empty -- e.g. "Assign" clicked before a reviewer was chosen
            # in the modal, or with JS disabled, so the hidden reviewer_id
            # input never got filled in. get_object_or_404(pk="") raises a
            # raw ValueError (a bigint field's get_prep_value rejects '',
            # and get_object_or_404 only ever catches DoesNotExist) instead
            # of a friendly 404, so both ids are checked as real integers
            # before either query ever runs.
            application_id = request.POST.get("application_id", "")
            reviewer_id = request.POST.get("reviewer_id", "")
            if not application_id.isdigit() or not reviewer_id.isdigit():
                messages.error(request, "Choose a reviewer before assigning.")
                return redirect(f"{request.path}?tab={tab}")

            application = get_object_or_404(oversight.staff_queryset(), pk=application_id)
            reviewer = get_object_or_404(
                User, pk=reviewer_id,
                role=User.Role.REVIEWER, reviewer_status=User.RequestStatus.APPROVED,
            )
            # ReviewAssignment.objects.create() only coerces the DB column;
            # the in-memory instance keeps whatever type was passed in, so a
            # raw string here would later crash _send_assignment_email's
            # strftime-style formatting. Parse to a real date up front.
            due_date = parse_date(request.POST.get("due_date") or "") or None
            assignment = ReviewAssignment.objects.create(
                application=application, reviewer=reviewer, assigned_by=request.user, due_date=due_date,
            )
            AuditLog.record(
                request.user, "review_assignment.created", target=application,
                description=f"Assigned to {reviewer.full_name}.",
            )
            emailed = _send_assignment_email(request, assignment)
            suffix = "and notified by email." if emailed else "(the notification email couldn't be sent)."
            messages.success(
                request,
                f"{reviewer.full_name} assigned to review {application.reference_no or application.title} {suffix}",
            )
        elif action == "withdraw":
            assignment_id = request.POST.get("assignment_id", "")
            if not assignment_id.isdigit():
                messages.error(request, "That request could not be processed.")
                return redirect(f"{request.path}?tab={tab}")
            assignment = get_object_or_404(
                ReviewAssignment.objects.select_related("application", "reviewer"),
                pk=assignment_id, status=ReviewAssignment.Status.NEW,
            )
            AuditLog.record(
                request.user, "review_assignment.withdrawn", target=assignment.application,
                description=f"Withdrawn from {assignment.reviewer.full_name}.",
            )
            assignment.delete()
            messages.success(request, "Assignment withdrawn -- the application is available to assign again.")
        else:
            messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}?tab={tab}")

    active_tab = request.GET.get("tab", "assign")
    if active_tab not in REVIEWER_ASSIGNMENT_TABS:
        active_tab = "assign"

    reviewers = list(_approved_reviewers())
    needs_assignment = list(_needs_assignment_qs())

    # A reviewer's decline doesn't just drop the application back into this
    # list looking freshly unassigned -- it's surfaced right on the card so
    # the Secretariat can see *why* it needs a reviewer again, not just that
    # it does.
    declined_by_application = {}
    declines = (
        ReviewAssignment.objects.filter(
            application_id__in=[a.pk for a in needs_assignment],
            status=ReviewAssignment.Status.DECLINED,
        )
        .select_related("reviewer")
        .order_by("-declined_at")
    )
    for decline in declines:
        declined_by_application.setdefault(decline.application_id, []).append(decline)
    for application in needs_assignment:
        application.recent_declines = declined_by_application.get(application.pk, [])

    pending = list(
        _open_assignments()
        .select_related("application", "reviewer")
        .order_by("due_date", "-assigned_at")
    )
    for assignment in pending:
        assignment.tab_value = assignment.tab

    completed = list(
        ReviewAssignment.objects.filter(status=ReviewAssignment.Status.COMPLETED)
        .select_related("application", "reviewer")
        .order_by("-completed_at")
    )

    workload = list(
        User.objects.filter(role=User.Role.REVIEWER, reviewer_status=User.RequestStatus.APPROVED)
        .annotate(
            active_count=Count(
                "review_assignments",
                filter=Q(review_assignments__status__in=["new", "accepted"]),
                distinct=True,
            ),
            overdue_count=Count(
                "review_assignments",
                filter=Q(
                    review_assignments__status="accepted",
                    review_assignments__due_date__lte=timezone.localdate(),
                ),
                distinct=True,
            ),
            completed_count=Count(
                "review_assignments",
                filter=Q(review_assignments__status="completed"),
                distinct=True,
            ),
        )
        .order_by("active_count", "first_name", "last_name")
    )

    counts = {
        "assign": len(needs_assignment),
        "pending": len(pending),
        "completed": len(completed),
        "workload": len(reviewers),
    }

    return render(request, "dashboards/secretariat/reviewer-assignment.html", {
        "active_tab": active_tab,
        "needs_assignment": needs_assignment,
        "pending": pending,
        "completed": completed,
        "workload": workload,
        "reviewers": reviewers,
        "counts": counts,
    })


@login_required
@staff_required
def reviewer_assignment_counts(request):
    """Polled by live-counts.js -- e.g. a second staff member assigns the
    last un-assigned application while this page is open in another tab."""
    return JsonResponse({
        "assign": _needs_assignment_qs().count(),
        "pending": _open_assignments().count(),
        "completed": ReviewAssignment.objects.filter(status=ReviewAssignment.Status.COMPLETED).count(),
        "workload": User.objects.filter(
            role=User.Role.REVIEWER, reviewer_status=User.RequestStatus.APPROVED
        ).count(),
    })


# ---------------------------------------------------------------------
# Communications -- Email Templates
# ---------------------------------------------------------------------

EMAIL_TEMPLATE_CATEGORIES = {c for c, _ in EmailTemplate.Category.choices}


@login_required
@staff_required
def email_templates(request):
    active_category = request.GET.get("category", "all")
    templates = EmailTemplate.objects.all()
    if active_category in EMAIL_TEMPLATE_CATEGORIES:
        templates = templates.filter(category=active_category)

    editing = None
    edit_id = request.GET.get("edit")
    if edit_id and edit_id != "new":
        editing = get_object_or_404(EmailTemplate, pk=edit_id)
    compose_open = bool(edit_id)

    return render(request, "dashboards/secretariat/email-templates.html", {
        "templates": templates.order_by("name"),
        "categories": EmailTemplate.Category.choices,
        "active_category": active_category,
        "placeholders": EmailTemplate.PLACEHOLDERS,
        "editing": editing,
        "compose_open": compose_open,
        "counts": {
            "all": EmailTemplate.objects.count(),
            "active": EmailTemplate.objects.filter(is_active=True).count(),
        },
    })


@login_required
@staff_required
def email_template_save(request):
    if request.method != "POST":
        return redirect("secretariat_dashboard:email_templates")

    pk = request.POST.get("pk")
    name = (request.POST.get("name") or "").strip()
    subject = (request.POST.get("subject") or "").strip()
    body = (request.POST.get("body") or "").strip()
    category = request.POST.get("category") or EmailTemplate.Category.GENERAL

    if not name or not subject or not body:
        messages.error(request, "Name, subject and body are all required.")
        return redirect(f"{reverse('secretariat_dashboard:email_templates')}?edit={pk or 'new'}")

    if category not in EMAIL_TEMPLATE_CATEGORIES:
        category = EmailTemplate.Category.GENERAL

    if pk:
        template = get_object_or_404(EmailTemplate, pk=pk)
        template.name, template.subject, template.body, template.category = name, subject, body, category
        template.is_active = bool(request.POST.get("is_active"))
        template.save()
        messages.success(request, f'"{template.name}" was updated.')
    else:
        EmailTemplate.objects.create(
            name=name, subject=subject, body=body, category=category,
            is_active=bool(request.POST.get("is_active", True)), created_by=request.user,
        )
        messages.success(request, f'"{name}" was created.')

    return redirect("secretariat_dashboard:email_templates")


@login_required
@staff_required
def email_template_delete(request, pk):
    template = get_object_or_404(EmailTemplate, pk=pk)
    if request.method == "POST":
        name = template.name
        template.delete()
        messages.success(request, f'"{name}" was deleted.')
    return redirect("secretariat_dashboard:email_templates")


@login_required
@staff_required
def email_template_preview(request, pk):
    template = get_object_or_404(EmailTemplate, pk=pk)
    return HttpResponse(render_template_preview(template))


# ---------------------------------------------------------------------
# Communications -- Notifications (compose + sent history, across every
# audience -- the Secretariat's own bell only ever shows its own).
# ---------------------------------------------------------------------

@login_required
@staff_required
def notifications_page(request):
    active_audience = request.GET.get("audience", "all")
    notices = Notification.objects.all()
    if active_audience != "all" and active_audience in Notification.Audience.values:
        notices = notices.filter(audience=active_audience)

    audience_rows = [
        (value, label, Notification.objects.filter(audience=value).count())
        for value, label in Notification.Audience.choices
    ]

    return render(request, "dashboards/secretariat/notifications.html", {
        "notices": notices.order_by("-created_at")[:200],
        "audiences": Notification.Audience.choices,
        "audience_rows": audience_rows,
        "active_audience": active_audience,
        "icons": Notification.Icon.choices,
    })


@login_required
@staff_required
def notification_send(request):
    if request.method != "POST":
        return redirect("secretariat_dashboard:notifications_page")

    audience = request.POST.get("audience")
    message_text = (request.POST.get("message") or "").strip()
    icon = request.POST.get("icon") or Notification.Icon.INFO

    if audience not in Notification.Audience.values or not message_text:
        messages.error(request, "Pick an audience and write a message before sending.")
        return redirect("secretariat_dashboard:notifications_page")

    if icon not in Notification.Icon.values:
        icon = Notification.Icon.INFO

    notification_services.notify(audience, message_text, icon=icon)
    messages.success(request, f"Notification sent to {dict(Notification.Audience.choices)[audience]}.")
    return redirect("secretariat_dashboard:notifications_page")


# ---------------------------------------------------------------------
# Communications -- Announcements
# ---------------------------------------------------------------------

@login_required
@staff_required
def announcements(request):
    editing = None
    edit_id = request.GET.get("edit")
    if edit_id and edit_id != "new":
        editing = get_object_or_404(Announcement, pk=edit_id)

    now = timezone.now()
    all_announcements = list(Announcement.objects.all())
    for a in all_announcements:
        a.live = a.is_live(now=now)

    return render(request, "dashboards/secretariat/announcements.html", {
        "announcements": all_announcements,
        "audiences": AudienceChoices.choices,
        "editing": editing,
        "compose_open": bool(edit_id),
        "counts": {
            "all": len(all_announcements),
            "live": sum(1 for a in all_announcements if a.live),
        },
    })


@login_required
@staff_required
def announcement_save(request):
    if request.method != "POST":
        return redirect("secretariat_dashboard:announcements")

    pk = request.POST.get("pk")
    title = (request.POST.get("title") or "").strip()
    body = (request.POST.get("body") or "").strip()
    audience = request.POST.get("audience") or AudienceChoices.ALL
    if audience not in AudienceChoices.values:
        audience = AudienceChoices.ALL

    if not title or not body:
        messages.error(request, "Title and body are both required.")
        return redirect(f"{reverse('secretariat_dashboard:announcements')}?edit={pk or 'new'}")

    starts_at = parse_date_as_datetime(request.POST.get("starts_at"))
    expires_at = parse_date_as_datetime(request.POST.get("expires_at"), end_of_day=True)
    is_pinned = bool(request.POST.get("is_pinned"))

    if pk:
        announcement = get_object_or_404(Announcement, pk=pk)
        announcement.title, announcement.body, announcement.audience = title, body, audience
        announcement.is_pinned = is_pinned
        announcement.starts_at = starts_at
        announcement.expires_at = expires_at
        announcement.save()
        messages.success(request, f'"{announcement.title}" was updated.')
    else:
        Announcement.objects.create(
            title=title, body=body, audience=audience, is_pinned=is_pinned,
            starts_at=starts_at, expires_at=expires_at, created_by=request.user,
        )
        messages.success(request, f'"{title}" was published.')

    return redirect("secretariat_dashboard:announcements")


@login_required
@staff_required
def announcement_toggle(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == "POST":
        announcement.is_active = not announcement.is_active
        announcement.save(update_fields=["is_active"])
        messages.success(
            request,
            f'"{announcement.title}" is now {"active" if announcement.is_active else "hidden"}.',
        )
    return redirect("secretariat_dashboard:announcements")


@login_required
@staff_required
def announcement_delete(request, pk):
    announcement = get_object_or_404(Announcement, pk=pk)
    if request.method == "POST":
        title = announcement.title
        announcement.delete()
        messages.success(request, f'"{title}" was deleted.')
    return redirect("secretariat_dashboard:announcements")


# ---------------------------------------------------------------------
# Communications -- Reminders
# ---------------------------------------------------------------------

@login_required
@staff_required
def reminders(request):
    communications_services.dispatch_due_reminders()

    active_tab = request.GET.get("tab", "scheduled")
    if active_tab not in {"scheduled", "sent", "cancelled"}:
        active_tab = "scheduled"

    all_reminders = Reminder.objects.select_related("application", "created_by")
    status_map = {"scheduled": Reminder.Status.SCHEDULED, "sent": Reminder.Status.SENT, "cancelled": Reminder.Status.CANCELLED}

    return render(request, "dashboards/secretariat/reminders.html", {
        "reminders": all_reminders.filter(status=status_map[active_tab]),
        "active_tab": active_tab,
        "audiences": AudienceChoices.choices,
        "recent_applications": Application.objects.order_by("-submitted_at")[:100],
        "counts": {key: all_reminders.filter(status=value).count() for key, value in status_map.items()},
    })


@login_required
@staff_required
def reminder_save(request):
    if request.method != "POST":
        return redirect("secretariat_dashboard:reminders")

    title = (request.POST.get("title") or "").strip()
    message_text = (request.POST.get("message") or "").strip()
    audience = request.POST.get("audience") or AudienceChoices.APPLICANT
    if audience not in AudienceChoices.values:
        audience = AudienceChoices.APPLICANT
    remind_at = parse_datetime_local(request.POST.get("remind_at"))
    application_id = request.POST.get("application_id") or None

    if not title or not message_text or not remind_at:
        messages.error(request, "Title, message and a date/time are all required.")
        return redirect("secretariat_dashboard:reminders")

    Reminder.objects.create(
        title=title, message=message_text, audience=audience, remind_at=remind_at,
        application_id=application_id, send_email=bool(request.POST.get("send_email", True)),
        created_by=request.user,
    )
    messages.success(request, f'Reminder "{title}" scheduled.')
    return redirect("secretariat_dashboard:reminders")


@login_required
@staff_required
def reminder_cancel(request, pk):
    reminder = get_object_or_404(Reminder, pk=pk)
    if request.method == "POST" and reminder.status == Reminder.Status.SCHEDULED:
        reminder.status = Reminder.Status.CANCELLED
        reminder.save(update_fields=["status"])
        messages.success(request, f'Reminder "{reminder.title}" was cancelled.')
    return redirect("secretariat_dashboard:reminders")


@login_required
@staff_required
def reminder_send_now(request, pk):
    reminder = get_object_or_404(Reminder, pk=pk)
    if request.method == "POST" and reminder.status == Reminder.Status.SCHEDULED:
        communications_services.dispatch_reminder(reminder)
        messages.success(request, f'Reminder "{reminder.title}" was sent.')
    return redirect("secretariat_dashboard:reminders")


# ---------------------------------------------------------------------
# Meetings -- Schedule, Calendar, Agenda, Attendance, Quorum, Minutes,
# Decisions. All seven pages share one "which meeting am I looking at"
# picker (the ?meeting= query param, defaulting to the next upcoming
# one) so jumping between them keeps you on the same meeting.
# ---------------------------------------------------------------------

MEETING_PARTICIPANT_ROLES = (User.Role.CHAIR, User.Role.COMMITTEE, User.Role.SECRETARIAT)


def _eligible_meeting_participants():
    return User.objects.filter(role__in=MEETING_PARTICIPANT_ROLES, is_active=True).order_by("role", "first_name")


def _meeting_queryset():
    return Meeting.objects.select_related("chair", "created_by").prefetch_related(
        "participants__user", "agenda_items", "decisions",
    )


def _selected_meeting(request):
    meeting_id = request.GET.get("meeting") or request.POST.get("meeting")
    qs = _meeting_queryset()
    if meeting_id:
        return get_object_or_404(qs, pk=meeting_id)
    upcoming = qs.filter(
        scheduled_at__gte=timezone.now(), status=Meeting.Status.SCHEDULED,
    ).order_by("scheduled_at").first()
    return upcoming or qs.order_by("-scheduled_at").first()


def _default_role_for_user(user):
    return {
        User.Role.CHAIR: MeetingParticipant.ParticipantRole.CHAIR,
        User.Role.SECRETARIAT: MeetingParticipant.ParticipantRole.SECRETARY,
    }.get(user.role, MeetingParticipant.ParticipantRole.MEMBER)


@login_required
@staff_required
def meetings_schedule(request):
    upcoming = _meeting_queryset().filter(
        scheduled_at__gte=timezone.now(), status=Meeting.Status.SCHEDULED,
    ).order_by("scheduled_at")
    return render(request, "dashboards/secretariat/meetings/schedule.html", {
        "upcoming_meetings": upcoming,
        "eligible_participants": _eligible_meeting_participants(),
        "meeting_types": Meeting.MeetingType.choices,
        "modes": Meeting.Mode.choices,
        "now": timezone.now(),
    })


@login_required
@staff_required
def meeting_save(request):
    if request.method != "POST":
        return redirect("secretariat_dashboard:meetings_schedule")

    title = (request.POST.get("title") or "").strip()
    scheduled_at = parse_datetime_local(request.POST.get("scheduled_at"))
    meeting_type = request.POST.get("meeting_type") or Meeting.MeetingType.FULL_COMMITTEE
    mode = request.POST.get("mode") or Meeting.Mode.IN_PERSON
    participant_ids = request.POST.getlist("participants")

    if not title or not scheduled_at:
        messages.error(request, "Title and date/time are both required.")
        return redirect("secretariat_dashboard:meetings_schedule")
    if meeting_type not in Meeting.MeetingType.values:
        meeting_type = Meeting.MeetingType.FULL_COMMITTEE
    if mode not in Meeting.Mode.values:
        mode = Meeting.Mode.IN_PERSON

    chair_id = request.POST.get("chair_id") or None
    duration_minutes = request.POST.get("duration_minutes") or 120
    quorum_required = request.POST.get("quorum_required") or 0

    meeting = Meeting.objects.create(
        title=title,
        meeting_type=meeting_type,
        description=(request.POST.get("description") or "").strip(),
        scheduled_at=scheduled_at,
        duration_minutes=int(duration_minutes) if str(duration_minutes).isdigit() else 120,
        mode=mode,
        location=(request.POST.get("location") or "").strip(),
        meeting_link=(request.POST.get("meeting_link") or "").strip(),
        quorum_required=int(quorum_required) if str(quorum_required).isdigit() else 0,
        chair_id=chair_id,
        created_by=request.user,
    )

    participants = []
    for user in _eligible_meeting_participants().filter(pk__in=participant_ids):
        participants.append(MeetingParticipant.objects.create(
            meeting=meeting, user=user, role_at_meeting=_default_role_for_user(user),
        ))

    agenda_titles = request.POST.getlist("agenda_title")
    agenda_presenters = request.POST.getlist("agenda_presenter")
    agenda_durations = request.POST.getlist("agenda_duration")
    for index, agenda_title in enumerate(agenda_titles):
        agenda_title = agenda_title.strip()
        if not agenda_title:
            continue
        duration = agenda_durations[index] if index < len(agenda_durations) else "10"
        AgendaItem.objects.create(
            meeting=meeting, order=index, title=agenda_title,
            presenter=(agenda_presenters[index].strip() if index < len(agenda_presenters) else ""),
            duration_minutes=int(duration) if str(duration).isdigit() else 10,
        )

    AuditLog.record(request.user, "meeting.scheduled", target=meeting, description=f"{len(participants)} participant(s) invited.")

    emailed = meetings_services.send_meeting_invites(meeting, participants=participants, kind="invitation")
    messages.success(
        request,
        f'"{meeting.title}" scheduled for {meeting.scheduled_at:%d %b %Y, %I:%M %p} — {emailed} invitation email(s) sent.',
    )
    return redirect("secretariat_dashboard:meetings_schedule")


@login_required
@staff_required
def meeting_cancel(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    if request.method == "POST" and meeting.status != Meeting.Status.CANCELLED:
        meeting.status = Meeting.Status.CANCELLED
        meeting.save(update_fields=["status"])
        meetings_services.send_meeting_invites(meeting, kind="cancellation")
        AuditLog.record(request.user, "meeting.cancelled", target=meeting)
        messages.success(request, f'"{meeting.title}" was cancelled and participants were notified.')
    return redirect("secretariat_dashboard:meetings_schedule")


@login_required
@staff_required
def meetings_calendar(request):
    import calendar as _calendar
    from collections import defaultdict

    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
    except ValueError:
        year, month = today.year, today.month

    first_of_month = timezone.datetime(year, month, 1)
    if month == 12:
        next_month = timezone.datetime(year + 1, 1, 1)
    else:
        next_month = timezone.datetime(year, month + 1, 1)

    month_meetings = _meeting_queryset().filter(
        scheduled_at__date__gte=first_of_month.date(), scheduled_at__date__lt=next_month.date(),
    ).order_by("scheduled_at")

    by_day = defaultdict(list)
    for meeting in month_meetings:
        by_day[meeting.scheduled_at.day].append(meeting)

    cal = _calendar.Calendar(firstweekday=6)  # Sunday-first grid
    weeks = []
    for week in cal.monthdayscalendar(year, month):
        week_rows = []
        for day in week:
            week_rows.append({
                "day": day,
                "is_today": day and today.year == year and today.month == month and today.day == day,
                "meetings": by_day.get(day, []) if day else [],
            })
        weeks.append(week_rows)

    prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
    forward_month = (year, month + 1) if month < 12 else (year + 1, 1)

    return render(request, "dashboards/secretariat/meetings/calendar.html", {
        "weeks": weeks,
        "month_label": first_of_month.strftime("%B %Y"),
        "prev_year": prev_month[0], "prev_month": prev_month[1],
        "next_year": forward_month[0], "next_month": forward_month[1],
        "cur_year": year, "cur_month": month,
        "today_year": today.year, "today_month": today.month,
        "upcoming_meetings": _meeting_queryset().filter(
            scheduled_at__gte=timezone.now(), status=Meeting.Status.SCHEDULED,
        ).order_by("scheduled_at")[:6],
    })


@login_required
@staff_required
def meetings_agenda(request):
    meeting = _selected_meeting(request)
    return render(request, "dashboards/secretariat/meetings/agenda.html", {
        "meetings": _meeting_queryset().order_by("-scheduled_at")[:100],
        "meeting": meeting,
        "agenda_items": meeting.agenda_items.select_related("application").order_by("order", "id") if meeting else [],
        "recent_applications": Application.objects.order_by("-submitted_at")[:100],
    })


@login_required
@staff_required
def agenda_item_save(request):
    if request.method != "POST":
        return redirect("secretariat_dashboard:meetings_agenda")
    meeting = get_object_or_404(Meeting, pk=request.POST.get("meeting_id"))
    pk = request.POST.get("pk")
    title = (request.POST.get("title") or "").strip()
    if not title:
        messages.error(request, "An agenda item needs a title.")
        return redirect(f"{reverse('secretariat_dashboard:meetings_agenda')}?meeting={meeting.pk}")

    duration = request.POST.get("duration_minutes") or 10
    application_id = request.POST.get("application_id") or None
    fields = dict(
        title=title,
        description=(request.POST.get("description") or "").strip(),
        presenter=(request.POST.get("presenter") or "").strip(),
        duration_minutes=int(duration) if str(duration).isdigit() else 10,
        application_id=application_id,
    )
    if pk:
        AgendaItem.objects.filter(pk=pk, meeting=meeting).update(**fields)
        messages.success(request, "Agenda item updated.")
    else:
        fields["order"] = meeting.agenda_items.count()
        AgendaItem.objects.create(meeting=meeting, **fields)
        messages.success(request, "Agenda item added.")
    return redirect(f"{reverse('secretariat_dashboard:meetings_agenda')}?meeting={meeting.pk}")


@login_required
@staff_required
def agenda_item_delete(request, pk):
    item = get_object_or_404(AgendaItem, pk=pk)
    meeting_id = item.meeting_id
    if request.method == "POST":
        item.delete()
        messages.success(request, "Agenda item removed.")
    return redirect(f"{reverse('secretariat_dashboard:meetings_agenda')}?meeting={meeting_id}")


@login_required
@staff_required
def meetings_attendance(request):
    meeting = _selected_meeting(request)
    participants = meeting.participants.select_related("user").order_by("role_at_meeting", "user__first_name") if meeting else []
    return render(request, "dashboards/secretariat/meetings/attendance.html", {
        "meetings": _meeting_queryset().order_by("-scheduled_at")[:100],
        "meeting": meeting,
        "participants": participants,
        "eligible_participants": _eligible_meeting_participants(),
        "rsvp_statuses": MeetingParticipant.RsvpStatus.choices,
    })


@login_required
@staff_required
def attendance_add_participant(request):
    if request.method != "POST":
        return redirect("secretariat_dashboard:meetings_attendance")
    meeting = get_object_or_404(Meeting, pk=request.POST.get("meeting_id"))
    user = get_object_or_404(_eligible_meeting_participants(), pk=request.POST.get("user_id"))
    participant, created = MeetingParticipant.objects.get_or_create(
        meeting=meeting, user=user, defaults={"role_at_meeting": _default_role_for_user(user)},
    )
    if created:
        meetings_services.send_meeting_invites(meeting, participants=[participant], kind="invitation")
        messages.success(request, f"{user.full_name} added and invited.")
    else:
        messages.info(request, f"{user.full_name} is already on this meeting's list.")
    return redirect(f"{reverse('secretariat_dashboard:meetings_attendance')}?meeting={meeting.pk}")


@login_required
@staff_required
def attendance_mark(request, pk):
    participant = get_object_or_404(MeetingParticipant, pk=pk)
    if request.method == "POST":
        field = request.POST.get("field")
        if field == "attended":
            participant.attended = not participant.attended
            participant.checked_in_at = timezone.now() if participant.attended else None
            participant.save(update_fields=["attended", "checked_in_at"])
        elif field == "rsvp":
            rsvp = request.POST.get("rsvp_status")
            if rsvp in MeetingParticipant.RsvpStatus.values:
                participant.rsvp_status = rsvp
                participant.responded_at = timezone.now()
                participant.save(update_fields=["rsvp_status", "responded_at"])
    return redirect(f"{reverse('secretariat_dashboard:meetings_attendance')}?meeting={participant.meeting_id}")


@login_required
@staff_required
def attendance_remove_participant(request, pk):
    participant = get_object_or_404(MeetingParticipant, pk=pk)
    meeting_id = participant.meeting_id
    if request.method == "POST":
        participant.delete()
        messages.success(request, "Participant removed from this meeting.")
    return redirect(f"{reverse('secretariat_dashboard:meetings_attendance')}?meeting={meeting_id}")


@login_required
@staff_required
def meetings_quorum(request):
    meeting = _selected_meeting(request)
    quorum_pct = 0
    if meeting and meeting.quorum_required:
        quorum_pct = min(100, round(meeting.attended_voting_count() / meeting.quorum_required * 100))
    return render(request, "dashboards/secretariat/meetings/quorum.html", {
        "meetings": _meeting_queryset().order_by("-scheduled_at")[:100],
        "meeting": meeting,
        "quorum_pct": quorum_pct,
    })


@login_required
@staff_required
def quorum_update(request, pk):
    meeting = get_object_or_404(Meeting, pk=pk)
    if request.method == "POST":
        value = request.POST.get("quorum_required") or 0
        meeting.quorum_required = int(value) if str(value).isdigit() else 0
        meeting.save(update_fields=["quorum_required"])
        messages.success(request, f"Quorum requirement set to {meeting.quorum_required}.")
    return redirect(f"{reverse('secretariat_dashboard:meetings_quorum')}?meeting={meeting.pk}")


@login_required
@staff_required
def meetings_minutes(request):
    meeting = _selected_meeting(request)
    minutes = None
    if meeting:
        minutes, _ = MeetingMinutes.objects.get_or_create(meeting=meeting)
    return render(request, "dashboards/secretariat/meetings/minutes.html", {
        "meetings": _meeting_queryset().order_by("-scheduled_at")[:100],
        "meeting": meeting,
        "minutes": minutes,
    })


@login_required
@staff_required
def minutes_save(request):
    if request.method != "POST":
        return redirect("secretariat_dashboard:meetings_minutes")
    meeting = get_object_or_404(Meeting, pk=request.POST.get("meeting_id"))
    minutes, _ = MeetingMinutes.objects.get_or_create(meeting=meeting)
    minutes.content = request.POST.get("content") or ""
    minutes.recorded_by = request.user
    minutes.save(update_fields=["content", "recorded_by", "updated_at"])
    messages.success(request, "Minutes saved.")
    return redirect(f"{reverse('secretariat_dashboard:meetings_minutes')}?meeting={meeting.pk}")


@login_required
@staff_required
def minutes_finalize(request, pk):
    minutes = get_object_or_404(MeetingMinutes, pk=pk)
    if request.method == "POST":
        minutes.is_finalized = not minutes.is_finalized
        minutes.finalized_at = timezone.now() if minutes.is_finalized else None
        minutes.save(update_fields=["is_finalized", "finalized_at"])
        if minutes.is_finalized and minutes.meeting.status == Meeting.Status.SCHEDULED and minutes.meeting.is_past:
            minutes.meeting.status = Meeting.Status.COMPLETED
            minutes.meeting.save(update_fields=["status"])
        messages.success(request, "Minutes finalized." if minutes.is_finalized else "Minutes reopened for editing.")
    return redirect(f"{reverse('secretariat_dashboard:meetings_minutes')}?meeting={minutes.meeting_id}")


@login_required
@staff_required
def meetings_decisions(request):
    meeting_id = request.GET.get("meeting")
    all_decisions = Decision.objects.select_related("meeting", "agenda_item", "application")
    if meeting_id:
        all_decisions = all_decisions.filter(meeting_id=meeting_id)
        meeting = get_object_or_404(_meeting_queryset(), pk=meeting_id)
    else:
        meeting = _selected_meeting(request)
    return render(request, "dashboards/secretariat/meetings/decisions.html", {
        "meetings": _meeting_queryset().order_by("-scheduled_at")[:100],
        "meeting": meeting,
        "selected_meeting_id": meeting_id,
        "decisions": all_decisions[:200],
        "outcomes": Decision.Outcome.choices,
        "recent_applications": Application.objects.order_by("-submitted_at")[:100],
    })


@login_required
@staff_required
def decision_save(request):
    if request.method != "POST":
        return redirect("secretariat_dashboard:meetings_decisions")
    meeting = get_object_or_404(Meeting, pk=request.POST.get("meeting_id"))
    title = (request.POST.get("title") or "").strip()
    if not title:
        messages.error(request, "A decision needs a title.")
        return redirect(f"{reverse('secretariat_dashboard:meetings_decisions')}?meeting={meeting.pk}")

    outcome = request.POST.get("outcome") or Decision.Outcome.NOTED
    if outcome not in Decision.Outcome.values:
        outcome = Decision.Outcome.NOTED
    agenda_item_id = request.POST.get("agenda_item_id") or None
    application_id = request.POST.get("application_id") or None

    def _int(name):
        value = request.POST.get(name) or 0
        return int(value) if str(value).isdigit() else 0

    Decision.objects.create(
        meeting=meeting, agenda_item_id=agenda_item_id, application_id=application_id,
        title=title, outcome=outcome, details=(request.POST.get("details") or "").strip(),
        votes_for=_int("votes_for"), votes_against=_int("votes_against"), votes_abstain=_int("votes_abstain"),
        recorded_by=request.user,
    )
    AuditLog.record(request.user, "meeting.decision_recorded", target=meeting, description=title)
    messages.success(request, f'Decision "{title}" recorded.')
    return redirect(f"{reverse('secretariat_dashboard:meetings_decisions')}?meeting={meeting.pk}")


@login_required
@staff_required
def decision_delete(request, pk):
    decision = get_object_or_404(Decision, pk=pk)
    meeting_id = decision.meeting_id
    if request.method == "POST":
        decision.delete()
        messages.success(request, "Decision removed.")
    return redirect(f"{reverse('secretariat_dashboard:meetings_decisions')}?meeting={meeting_id}")


# ---------------------------------------------------------------------
# Reports & Analytics -- one page, seven tabs. All seven are computed
# and rendered on every request (see secretariat_dashboard/reports.py)
# so switching tabs in the browser is instant show/hide, no round trip
# -- the query volume behind each tab is small enough that this is
# cheaper than it sounds, and far nicer to use than a spinner per tab.
# ---------------------------------------------------------------------

@login_required
@staff_required
def reports(request):
    return render(request, "dashboards/secretariat/reports.html", {
        "application_stats": reports_data.application_statistics(),
        "status_report": reports_data.status_reports(),
        "turnaround": reports_data.turnaround_times(),
        "workload": reports_data.reviewer_workload(),
        "committee": reports_data.committee_activity(),
        "compliance": reports_data.post_approval_compliance(),
        "financial": reports_data.financial_reports(),
    })


# ---------------------------------------------------------------------
# Audit Logs -- read-only trail of AuditLog.record() calls across the
# whole platform (see accounts.models.AuditLog). Grouped by action
# prefix ("user.", "application.", "review_assignment.", "role.")
# rather than a fixed choices list, since that's how AuditLog itself
# stores actions -- new prefixes just show up under "Other" until this
# CATEGORY map is taught about them.
# ---------------------------------------------------------------------

AUDIT_LOG_CATEGORIES = {
    "all": None,
    "users": "user.",
    "applications": "application.",
    "reviews": "review_assignment.",
    "roles": "role.",
}


def _audit_log_category(action):
    for key, prefix in AUDIT_LOG_CATEGORIES.items():
        if prefix and action.startswith(prefix):
            return key
    return "other"


@login_required
@staff_required
def audit_logs(request, template_name="dashboards/secretariat/audit-logs.html"):
    active_tab = request.GET.get("tab", "all")
    if active_tab not in AUDIT_LOG_CATEGORIES:
        active_tab = "all"
    query = request.GET.get("q", "").strip()

    base_qs = AuditLog.objects.select_related("actor").order_by("-created_at")
    if query:
        base_qs = base_qs.filter(
            Q(actor__first_name__icontains=query) | Q(actor__last_name__icontains=query)
            | Q(actor__email__icontains=query) | Q(action__icontains=query)
            | Q(target_label__icontains=query) | Q(description__icontains=query)
        )

    counts = {"all": base_qs.count()}
    for key, prefix in AUDIT_LOG_CATEGORIES.items():
        if prefix:
            counts[key] = base_qs.filter(action__startswith=prefix).count()
    counts["other"] = counts["all"] - sum(v for k, v in counts.items() if k not in ("all", "other"))

    scoped_qs = base_qs
    prefix = AUDIT_LOG_CATEGORIES.get(active_tab)
    if prefix:
        scoped_qs = base_qs.filter(action__startswith=prefix)

    paginator = Paginator(scoped_qs, 40)
    page = paginator.get_page(request.GET.get("page"))
    for log in page:
        log.category = _audit_log_category(log.action)

    return render(request, template_name, {
        "page": page,
        "counts": counts,
        "active_tab": active_tab,
        "query": query,
    })


# ---------------------------------------------------------------------
# Committee -- Committee Members, Membership/Appointments, Terms &
# Expiry, Training and Conflict Records. Same governance tables
# admin_dashboard's Committee pages read and write (one Board/Committee
# roster, shared across both dashboards); the write-side logic itself
# lives in pages.committee_services so the two dashboards can't drift.
# ---------------------------------------------------------------------

COMMITTEE_MEMBERS_TABS = {"all", "board", "committee", "secretariat"}


@login_required
@staff_required
def committee_members(request):
    if request.method == "POST":
        action = request.POST.get("action")
        tab = request.POST.get("tab", "all")

        if action == "add":
            committee_services.handle_governance_add(request)
        else:
            member = get_object_or_404(GovernanceMember, pk=request.POST.get("member_id", ""))
            if action == "edit":
                committee_services.handle_governance_edit(request, member)
            elif action == "delete":
                committee_services.handle_governance_delete(request, member)
            else:
                messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}?tab={tab}")

    active_tab = request.GET.get("tab", "all")
    if active_tab not in COMMITTEE_MEMBERS_TABS:
        active_tab = "all"

    members = list(GovernanceMember.objects.all())
    for member in members:
        member.photo_url = pages_storage.public_url(member.photo_path)

    counts = {
        "all": len(members),
        "board": sum(1 for m in members if m.group == GovernanceMember.Group.BOARD),
        "committee": sum(1 for m in members if m.group == GovernanceMember.Group.COMMITTEE),
        "secretariat": sum(1 for m in members if m.group == GovernanceMember.Group.SECRETARIAT),
    }

    return render(request, "dashboards/secretariat/committee/members.html", {
        "members": members,
        "counts": counts,
        "active_tab": active_tab,
        "groups": GovernanceMember.Group.choices,
        "title_choices": GOVERNANCE_TITLE_CHOICES,
        "tag_choices": GOVERNANCE_TAG_CHOICES,
    })


COMMITTEE_APPOINTMENT_TABS = {"all", "active", "renewed", "expired", "terminated"}


@login_required
@staff_required
def committee_appointments(request):
    if request.method == "POST":
        action = request.POST.get("action")
        tab = request.POST.get("tab", "all")

        if action == "add":
            committee_services.handle_appointment_add(request)
        else:
            appointment = get_object_or_404(CommitteeAppointment, pk=request.POST.get("appointment_id", ""))
            if action == "edit":
                committee_services.handle_appointment_edit(request, appointment)
            elif action == "delete":
                committee_services.handle_appointment_delete(request, appointment)
            else:
                messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}?tab={tab}")

    active_tab = request.GET.get("tab", "all")
    if active_tab not in COMMITTEE_APPOINTMENT_TABS:
        active_tab = "all"

    appointments = list(CommitteeAppointment.objects.select_related("member").all())
    for appointment in appointments:
        appointment.letter_url = documents_storage.public_url(appointment.letter_path)

    counts = {"all": len(appointments)}
    for value, _label in CommitteeAppointment.Status.choices:
        counts[value] = sum(1 for a in appointments if a.status == value)

    return render(request, "dashboards/secretariat/committee/appointments.html", {
        "appointments": appointments,
        "counts": counts,
        "active_tab": active_tab,
        "members": committee_services.active_governance_members(),
        "statuses": CommitteeAppointment.Status.choices,
    })


COMMITTEE_EXPIRY_TABS = {"all", "expiring", "expired", "ongoing"}


@login_required
@staff_required
def committee_terms_expiry(request):
    if request.method == "POST":
        action = request.POST.get("action")
        tab = request.POST.get("tab", "all")
        appointment = get_object_or_404(CommitteeAppointment, pk=request.POST.get("appointment_id", ""))

        if action == "edit":
            committee_services.handle_appointment_edit(request, appointment)
        else:
            messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}?tab={tab}")

    active_tab = request.GET.get("tab", "all")
    if active_tab not in COMMITTEE_EXPIRY_TABS:
        active_tab = "all"

    appointments = list(CommitteeAppointment.objects.select_related("member").all())
    appointments.sort(key=lambda a: (a.end_date is None, a.end_date))

    counts = {
        "all": len(appointments),
        "expiring": sum(1 for a in appointments if a.expiry_state == "expiring"),
        "expired": sum(1 for a in appointments if a.expiry_state == "expired"),
        "ongoing": sum(1 for a in appointments if a.expiry_state in ("ongoing", "current")),
    }

    return render(request, "dashboards/secretariat/committee/terms-expiry.html", {
        "appointments": appointments,
        "counts": counts,
        "active_tab": active_tab,
        "statuses": CommitteeAppointment.Status.choices,
    })


COMMITTEE_TRAINING_TABS = {"all", "current", "expiring", "expired", "ongoing"}


@login_required
@staff_required
def committee_training(request):
    if request.method == "POST":
        action = request.POST.get("action")
        tab = request.POST.get("tab", "all")

        if action == "add":
            committee_services.handle_training_add(request)
        else:
            record = get_object_or_404(TrainingRecord, pk=request.POST.get("record_id", ""))
            if action == "edit":
                committee_services.handle_training_edit(request, record)
            elif action == "delete":
                committee_services.handle_training_delete(request, record)
            else:
                messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}?tab={tab}")

    active_tab = request.GET.get("tab", "all")
    if active_tab not in COMMITTEE_TRAINING_TABS:
        active_tab = "all"

    records = list(TrainingRecord.objects.select_related("member").all())
    for record in records:
        record.certificate_url = documents_storage.public_url(record.certificate_path)

    counts = {
        "all": len(records),
        "current": sum(1 for r in records if r.expiry_state == "current"),
        "expiring": sum(1 for r in records if r.expiry_state == "expiring"),
        "expired": sum(1 for r in records if r.expiry_state == "expired"),
        "ongoing": sum(1 for r in records if r.expiry_state == "ongoing"),
    }

    return render(request, "dashboards/secretariat/committee/training.html", {
        "records": records,
        "counts": counts,
        "active_tab": active_tab,
        "members": committee_services.active_governance_members(),
    })


COMMITTEE_CONFLICT_TABS = {"all", "pending", "reviewed", "recused", "resolved"}


@login_required
@staff_required
def committee_conflict_records(request):
    if request.method == "POST":
        action = request.POST.get("action")
        tab = request.POST.get("tab", "all")

        if action == "add":
            committee_services.handle_conflict_add(request)
        else:
            record = get_object_or_404(ConflictDeclaration, pk=request.POST.get("record_id", ""))
            if action == "edit":
                committee_services.handle_conflict_edit(request, record)
            elif action == "delete":
                committee_services.handle_conflict_delete(request, record)
            else:
                messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}?tab={tab}")

    active_tab = request.GET.get("tab", "all")
    if active_tab not in COMMITTEE_CONFLICT_TABS:
        active_tab = "all"

    records = list(ConflictDeclaration.objects.select_related("member").all())

    counts = {"all": len(records)}
    for value, _label in ConflictDeclaration.Status.choices:
        counts[value] = sum(1 for r in records if r.status == value)

    return render(request, "dashboards/secretariat/committee/conflict-records.html", {
        "records": records,
        "counts": counts,
        "active_tab": active_tab,
        "members": committee_services.active_governance_members(),
        "statuses": ConflictDeclaration.Status.choices,
    })
