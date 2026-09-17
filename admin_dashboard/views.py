import csv
from datetime import timedelta

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts import storage
from accounts.models import AuditLog, RoleApprovalLog, User
from accounts.sessions import active_sessions_for, describe_user_agent
from applicant_dashboard import oversight
from applicant_dashboard import storage as application_storage
from applicant_dashboard.models import Application
from messaging.access import is_staff_side
from notifications.emails import send_branded_email
from pages import documents_storage
from pages import storage as pages_storage
from pages.models import (
    CommitteeAppointment,
    CommitteeMeeting,
    ConflictDeclaration,
    GovernanceMember,
    Inquiry,
    MeetingDocument,
    PolicyDocument,
    SiteSettings,
    TrainingRecord,
)
from payments import fees
from payments import services as payment_services
from reviewer_dashboard import storage as reviewer_storage

TABS = {"all", "pending", "applicants", "reviewers", "committee", "admins"}
INQUIRY_TABS = {"all", "new", "resolved"}

# Roles whose account security (2FA adoption, active sessions) actually
# matters for platform integrity -- reviewers/committee/applicants have
# their own Security pages already; this is specifically about who holds
# elevated, cross-account access.
STAFF_SECURITY_ROLES = [User.Role.ADMIN, User.Role.SECRETARIAT, User.Role.CHAIR]

# Presentation-only detail for the dashboard's "Users by Role" panel, keyed
# by the labels _role_counts() returns. Kept out of _role_counts() itself so
# the Reports page and its CSV export -- which want numbers, not blurbs and
# badge colours -- are unaffected by anything the dashboard wants to show.
ROLE_PANEL_META = {
    "Applicants": ("Researchers submitting studies", "blue"),
    "Reviewers": ("Assigned to expedited & full review", "teal"),
    "Committee": ("Full committee reviewers", "purple"),
    "Secretariat": ("Day-to-day operations", "navy"),
    "Chair": ("Governance & final sign-off", "orange"),
    "Admins": ("Full platform access", "green"),
}


def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.role == User.Role.ADMIN)


admin_required = user_passes_test(is_admin, login_url="pages:login")

# Accounts, Site Settings, and Profile & Security are the three admin
# pages Secretariat's own sidebar links into (Users & Access / System
# Settings / Profile & Security) -- reusing the same view/template rather
# than building a parallel Secretariat copy, so this is deliberately
# `is_staff_side` (Admin + Secretariat), not `admin_required`. Every
# other admin_dashboard view (Finance, Reports, Access Security, Board &
# Committee, Help & Support) stays admin-only.
admin_or_secretariat_required = user_passes_test(is_staff_side, login_url="pages:login")


def _categorize(user):
    """Single tab each user belongs to (so tab counts sum to the total)."""
    if user.is_superuser or user.role == User.Role.ADMIN:
        return "admins"
    if user.has_pending_requests:
        return "pending"
    if user.role == User.Role.REVIEWER and user.reviewer_status == User.RequestStatus.APPROVED:
        return "reviewers"
    if user.role == User.Role.COMMITTEE and user.committee_status == User.RequestStatus.APPROVED:
        return "committee"
    return "applicants"


def _send_role_approved_email(request, target, role):
    """Tells an applicant their Reviewer/Committee Member request was
    approved and that they can now log in to the matching dashboard.
    Same fail_silently contract as the Contact-page reply email below --
    a missing/misconfigured SMTP setup must never block the approval
    itself, it just means this particular applicant doesn't get emailed
    (they'll still see the unlocked dashboard next time they log in).
    Returns True/False so the caller's flash message doesn't claim an
    email went out when it actually didn't."""
    role_label = User.Role(role).label
    login_url = request.build_absolute_uri(reverse("pages:login"))
    return send_branded_email(
        subject=f"Your MSREC {role_label} request has been approved",
        to=target.email,
        heading="Your request has been approved",
        paragraphs=[
            f"Hi {target.full_name},",
            f"Good news — your request to join MSREC as a {role_label} has been approved. "
            f"You can now log in and access the {role_label} dashboard whenever you're ready.",
        ],
        cta_text="Log in to MSREC",
        cta_url=login_url,
        preheader=f"Your {role_label} request has been approved.",
    )


def _handle_role_decision(request, target, role, action):
    if role not in (User.Role.REVIEWER, User.Role.COMMITTEE) or action not in ("approve", "reject"):
        messages.error(request, "That request could not be processed.")
        return

    if action == "approve":
        target.approve_role(role)
        RoleApprovalLog.objects.create(
            user=target, role=role, action=RoleApprovalLog.Action.APPROVED, acted_by=request.user,
        )
        AuditLog.record(request.user, f"role.{role}.approved", target=target)
        emailed = _send_role_approved_email(request, target, role)
        suffix = "and notified by email." if emailed else "(the approval email couldn't be sent -- check the email settings)."
        messages.success(request, f"{target.full_name} approved as {target.get_role_display()} {suffix}")
    else:
        target.reject_role(role)
        RoleApprovalLog.objects.create(
            user=target, role=role, action=RoleApprovalLog.Action.REJECTED, acted_by=request.user,
        )
        AuditLog.record(request.user, f"role.{role}.rejected", target=target)
        messages.success(request, f"{role.title()} request for {target.full_name} was declined.")


def _actor_is_admin(request):
    return request.user.is_superuser or request.user.role == User.Role.ADMIN


def _handle_suspend(request, target, *, suspend):
    if target.pk == request.user.pk:
        messages.error(request, "You can't suspend your own account.")
        return
    if suspend and target.is_superuser:
        messages.error(request, "Superuser accounts can't be suspended from here.")
        return
    if target.role == User.Role.ADMIN and not _actor_is_admin(request):
        messages.error(request, "Only an administrator can suspend an Administrator account.")
        return

    target.is_active = not suspend
    target.save(update_fields=["is_active"])
    # Suspension must take effect immediately, not just block the next
    # login -- kill every session already open under this account.
    if suspend:
        Session.objects.filter(
            pk__in=[
                s.pk for s in Session.objects.all()
                if s.get_decoded().get("_auth_user_id") == str(target.pk)
            ]
        ).delete()
        AuditLog.record(request.user, "user.suspended", target=target)
        messages.success(request, f"{target.full_name}'s account has been suspended.")
    else:
        AuditLog.record(request.user, "user.activated", target=target)
        messages.success(request, f"{target.full_name}'s account has been reactivated.")


def _cleanup_user_storage(target):
    """Best-effort: delete every Storage object this account owns before
    the row itself goes -- signup CVs/photo, and (since Application
    cascade-deletes along with the user -- see Application.applicant's
    on_delete=CASCADE) every document attached to their own applications.
    A Storage failure never blocks the account deletion itself; it just
    risks leaving an orphaned object behind, same fail-open contract as
    every other Storage call in this project."""
    photo = target.profile_photo_path
    if photo:
        # Three possible buckets depending on when the photo was (last)
        # set -- see reviewer_dashboard.storage / applicant_dashboard.
        # storage's upload_avatar_file docstrings: a "reviewers/<id>/..."
        # prefix means it replaced the signup photo via a reviewer's
        # Profile & Expertise page; "avatars/<id>/..." means Profile &
        # Security (applicant); anything else is still the one uploaded
        # at signup (accounts.storage, private bucket).
        if photo.startswith("reviewers/"):
            reviewer_storage.delete_object(photo)
        elif photo.startswith("avatars/"):
            application_storage.delete_object(photo)
        else:
            storage.delete_object(photo)

    for profile_field in ("reviewer_profile", "committee_profile", "applicant_profile"):
        cv_path = (getattr(target, profile_field) or {}).get("cv_path")
        if cv_path:
            storage.delete_object(cv_path)

    for application in target.applications.all():
        for document in application.documents or []:
            doc_path = document.get("path")
            if doc_path:
                application_storage.delete_object(doc_path)


def _handle_delete(request, target):
    if target.pk == request.user.pk:
        messages.error(request, "You can't delete your own account.")
        return
    if target.is_superuser:
        messages.error(request, "Superuser accounts can't be deleted from here.")
        return
    if target.role == User.Role.ADMIN and not _actor_is_admin(request):
        messages.error(request, "Only an administrator can delete an Administrator account.")
        return
    name = target.full_name
    AuditLog.record(request.user, "user.deleted", target=target)
    _cleanup_user_storage(target)
    target.delete()
    messages.success(request, f"{name}'s account and files have been deleted.")


def _handle_edit(request, target):
    if target.role == User.Role.ADMIN and not _actor_is_admin(request):
        messages.error(request, "Only an administrator can edit an Administrator account.")
        return

    email = request.POST.get("email", "").strip().lower()
    confirm_email = request.POST.get("confirm_email", "").strip().lower()
    if not email:
        messages.error(request, "Email is required.")
        return
    if email != confirm_email:
        messages.error(request, "Email and Confirm Email don't match.")
        return
    if User.objects.exclude(pk=target.pk).filter(email=email).exists():
        messages.error(request, "Another account already uses that email address.")
        return

    role = request.POST.get("role", target.role)
    if role not in User.Role.values:
        role = target.role
    if role == User.Role.ADMIN and not _actor_is_admin(request):
        messages.error(request, "Only an administrator can grant the Administrator role.")
        return

    target.first_name = request.POST.get("first_name", "").strip()
    target.middle_name = request.POST.get("middle_name", "").strip()
    target.last_name = request.POST.get("last_name", "").strip()
    target.email = email
    target.phone = request.POST.get("phone", "").strip()
    target.institution = request.POST.get("institution", "").strip()
    target.department = request.POST.get("department", "").strip()
    target.position = request.POST.get("position", "").strip()
    if not target.is_superuser:
        target.role = role
    target.save(update_fields=[
        "first_name", "middle_name", "last_name", "email", "phone",
        "institution", "department", "position", "role",
    ])
    AuditLog.record(request.user, "user.edited", target=target)
    messages.success(request, f"{target.full_name}'s account has been updated.")


@login_required
@admin_or_secretariat_required
def accounts(request, template_name="dashboards/admin/accounts.html"):
    if request.method == "POST":
        target = get_object_or_404(User, pk=request.POST.get("user_id"))
        action = request.POST.get("action")

        if action in ("approve", "reject"):
            _handle_role_decision(request, target, request.POST.get("role"), action)
        elif action == "suspend":
            _handle_suspend(request, target, suspend=True)
        elif action == "activate":
            _handle_suspend(request, target, suspend=False)
        elif action == "delete":
            _handle_delete(request, target)
        elif action == "edit":
            _handle_edit(request, target)
        else:
            messages.error(request, "That request could not be processed.")

        return redirect(f"{request.path}?tab={request.POST.get('tab', 'all')}")

    all_users = list(User.objects.all().order_by("-date_joined"))
    counts = {"all": len(all_users), "pending": 0, "applicants": 0, "reviewers": 0, "committee": 0, "admins": 0}
    for u in all_users:
        u.category = _categorize(u)
        counts[u.category] += 1
        # Signed links to whatever the applicant uploaded at signup, so an
        # admin can actually look at the CV before approving a role request
        # instead of taking it on faith. Only bothered for rows an admin
        # would plausibly need them on (pending, or already-approved
        # reviewer/committee) -- not worth a Storage round trip per row on
        # every tab.
        if u.category in ("pending", "reviewers", "committee"):
            u.reviewer_cv_url = storage.create_signed_url(u.reviewer_profile.get("cv_path"))
            u.committee_cv_url = storage.create_signed_url(u.committee_profile.get("cv_path"))
        else:
            u.reviewer_cv_url = None
            u.committee_cv_url = None

    active_tab = request.GET.get("tab", "all")
    if active_tab not in TABS:
        active_tab = "all"

    return render(request, template_name, {
        "all_users": all_users,
        "counts": counts,
        "active_tab": active_tab,
    })


def _handle_inquiry_reply(request, inquiry):
    reply_message = request.POST.get("reply_message", "").strip()
    if not reply_message:
        messages.error(request, "Write a reply message before sending.")
        return

    inquiry.reply_message = reply_message
    inquiry.replied_at = timezone.now()
    inquiry.replied_by = request.user
    inquiry.status = Inquiry.Status.RESOLVED
    inquiry.resolved_at = inquiry.replied_at
    inquiry.save(update_fields=["reply_message", "replied_at", "replied_by", "status", "resolved_at"])

    # A missing/broken SMTP config must never break replying from the
    # dashboard -- fail_silently plus the console-backend fallback in
    # settings.py mean this only ever actually emails the sender when
    # EMAIL_HOST is configured.
    emailed = send_branded_email(
        subject=f"Re: Your message to MSREC ({inquiry.get_reason_display()})",
        to=inquiry.email,
        heading=f"Hi {inquiry.name},",
        paragraphs=[reply_message],
        quote_label=f"Your original message ({inquiry.created_at:%d %b %Y})",
        quote_text=inquiry.message,
        preheader=reply_message[:120],
    )
    if emailed:
        messages.success(request, f"Reply sent to {inquiry.name} ({inquiry.email}).")
    else:
        messages.error(request, f"Reply saved, but the email to {inquiry.email} couldn't be sent -- check the email settings.")


@login_required
@admin_required
def inquiries(request):
    if request.method == "POST":
        inquiry = get_object_or_404(Inquiry, pk=request.POST.get("inquiry_id"))
        action = request.POST.get("action")

        if action == "reply":
            _handle_inquiry_reply(request, inquiry)
        elif action == "resolve":
            inquiry.status = Inquiry.Status.RESOLVED
            inquiry.resolved_at = timezone.now()
            inquiry.save(update_fields=["status", "resolved_at"])
            messages.success(request, "Inquiry marked as resolved.")
        elif action == "reopen":
            inquiry.status = Inquiry.Status.NEW
            inquiry.resolved_at = None
            inquiry.save(update_fields=["status", "resolved_at"])
            messages.success(request, "Inquiry reopened.")
        elif action == "delete":
            inquiry.delete()
            messages.success(request, "Inquiry deleted.")
            return redirect(f"{request.path}?tab={request.POST.get('tab', 'all')}")
        else:
            messages.error(request, "That request could not be processed.")

        tab = request.POST.get("tab", "all")
        return redirect(f"{request.path}?tab={tab}&selected={inquiry.pk}")

    all_inquiries = list(Inquiry.objects.select_related("replied_by").all())
    counts = {"all": len(all_inquiries), "new": 0, "resolved": 0}
    for inquiry in all_inquiries:
        counts[inquiry.status] += 1

    active_tab = request.GET.get("tab", "all")
    if active_tab not in INQUIRY_TABS:
        active_tab = "all"

    # Which thread panel (and its reply composer) renders open. Resolved
    # here -- not left to inquiries.js alone -- so the right thread (and
    # its "no reply mechanism" -looking composer) is actually there in the
    # HTML on first paint, not just after JS runs: a ?selected=<id> deep
    # link (e.g. the redirect after replying/resolving) always wins, and
    # only falls back to the newest inquiry when it's missing or stale.
    selected_param = request.GET.get("selected")
    selected_id = int(selected_param) if selected_param and selected_param.isdigit() else None
    valid_ids = {inquiry.pk for inquiry in all_inquiries}
    if selected_id not in valid_ids:
        selected_id = all_inquiries[0].pk if all_inquiries else None

    return render(request, "dashboards/admin/inquiries.html", {
        "all_inquiries": all_inquiries,
        "counts": counts,
        "active_tab": active_tab,
        "selected_id": selected_id,
    })


@login_required
@admin_required
def home(request):
    base_qs = oversight.staff_queryset()
    application_counts = oversight.status_counts(base_qs)
    recent_applications = base_qs.order_by("-submitted_at")[:8]

    all_users = User.objects.all()
    # Distinct users with a pending request, not a sum across both roles --
    # someone pending on both reviewer and committee should still count once.
    pending_qs = all_users.filter(
        reviewer_status=User.RequestStatus.PENDING
    ) | all_users.filter(committee_status=User.RequestStatus.PENDING)
    pending_qs = pending_qs.distinct()
    user_counts = {
        "total": all_users.count(),
        "pending": pending_qs.count(),
    }
    oldest_pending = pending_qs.order_by("date_joined").first()

    # Institutions aren't a model of their own -- an institution exists on
    # this platform exactly when someone registered against it, so count
    # the distinct non-blank names rather than invent a table for them.
    institution_count = (
        all_users.exclude(institution="")
        .values("institution")
        .distinct()
        .count()
    )

    return render(request, "dashboards/admin.html", {
        "page_subtitle": f"Welcome back, {request.user.first_name}",
        "application_counts": application_counts,
        # "Active" means still moving through the pipeline. application_counts
        # ["all"] is every non-draft application ever, decided ones included,
        # so it overstates the live workload it was being used to label.
        "active_application_count": (
            application_counts["submitted"]
            + application_counts["under_review"]
            + application_counts["revisions"]
        ),
        "recent_applications": recent_applications,
        "user_counts": user_counts,
        "oldest_pending": oldest_pending,
        "institution_count": institution_count,
        "open_inquiry_count": Inquiry.objects.filter(status=Inquiry.Status.NEW).count(),
        # Same helper the Reports page and its CSV export use, so the
        # dashboard's role breakdown can never drift from the report's.
        "role_rows": [
            {
                "label": label,
                "count": count,
                "blurb": ROLE_PANEL_META.get(label, ("", "gray"))[0],
                "tone": ROLE_PANEL_META.get(label, ("", "gray"))[1],
            }
            for label, count in _role_counts()
        ],
    })


@login_required
@admin_required
def applications(request):
    active_tab = request.GET.get("tab", "all")
    if active_tab not in oversight.STATUS_TABS:
        active_tab = "all"

    base_qs = oversight.staff_queryset().order_by("-submitted_at")
    counts = oversight.status_counts(base_qs)

    all_applications = list(base_qs)
    for application in all_applications:
        application.tab = oversight.STATUS_TO_TAB.get(application.status, "all")
        # The stored value is the form's slug ("not-sure", "expedited").
        # Show the same wording the fee schedule and Reports page use.
        application.review_type_label = fees.label_for(application.review_type)

    return render(request, "dashboards/admin/applications.html", {
        "all_applications": all_applications,
        "counts": counts,
        "active_tab": active_tab,
    })


PATHWAY_INFO = {
    "exemption": {
        "label": "Determination / Exemption",
        "short_label": "Exemption",
        "accent": "green",
        "summary": "Minimal-risk studies that qualify for an ethics determination without full board review.",
        "criteria": [
            "Research on standard educational practices in established or commonly accepted educational settings.",
            "Anonymous surveys, interviews, or observation of public behaviour where no participant can be identified, directly or indirectly.",
            "Secondary analysis of existing, de-identified data, records, or specimens already collected for another purpose.",
            "Evaluation or quality-improvement activity conducted by an institution about its own programs, where findings are not intended to contribute to generalizable knowledge.",
        ],
    },
    "expedited": {
        "label": "Expedited Review",
        "short_label": "Expedited",
        "accent": "teal",
        "summary": "Minimal-risk studies reviewed by one or two designated reviewers rather than the full committee.",
        "criteria": [
            "Collection of biological specimens by minimally invasive means (e.g. venipuncture, buccal swab, hair or nail clippings).",
            "Research involving materials collected solely for non-research purposes, such as routine clinical or diagnostic records.",
            "Non-invasive procedures routinely used in clinical practice, excluding X-ray or microwave exposure.",
            "Research employing surveys, interviews, or focus groups on non-sensitive topics with identifiable but not vulnerable participants.",
        ],
    },
    "full": {
        "label": "Full Committee Review",
        "short_label": "Full Committee",
        "accent": "purple",
        "summary": "Greater-than-minimal-risk studies that require deliberation by the full committee at a convened meeting.",
        "criteria": [
            "Research presenting more than minimal risk to participants, including invasive procedures or experimental interventions.",
            "Studies involving vulnerable populations -- children, pregnant women, prisoners, or persons with diminished decision-making capacity.",
            "Research on sensitive topics where disclosure could expose participants to legal, financial, or reputational harm.",
            "Any study a designated reviewer refers up because it doesn't clearly meet the exemption or expedited criteria above.",
        ],
    },
}


def _review_pathway_queryset(pathway):
    return oversight.staff_queryset().filter(review_type=pathway).order_by("-submitted_at")


@login_required
@admin_required
def review_pathway(request, pathway):
    info = PATHWAY_INFO.get(pathway)
    if info is None:
        messages.error(request, "That review pathway doesn't exist.")
        return redirect("admin_dashboard:applications")

    active_tab = request.GET.get("tab", "all")
    if active_tab not in oversight.STATUS_TABS:
        active_tab = "all"

    base_qs = _review_pathway_queryset(pathway)
    counts = oversight.status_counts(base_qs)

    pathway_applications = list(base_qs)
    for application in pathway_applications:
        application.tab = oversight.STATUS_TO_TAB.get(application.status, "all")

    return render(request, "dashboards/admin/review-pathway.html", {
        "pathway": pathway,
        "info": info,
        "fee": fees.fee_for(pathway),
        "currency": fees.CURRENCY,
        "all_applications": pathway_applications,
        "counts": counts,
        "active_tab": active_tab,
    })


@login_required
@admin_required
def applications_counts(request):
    """Polled by live-counts.js to keep the Applications tab badges and
    summary strip current without a page reload."""
    return JsonResponse(oversight.status_counts(oversight.staff_queryset()))


@login_required
@admin_required
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
        return redirect("admin_dashboard:application_detail", pk=application.pk)

    application.tab = oversight.STATUS_TO_TAB.get(application.status, "all")
    application.review_type_label = fees.label_for(application.review_type)
    application.applicant_category_label = fees.label_for(application.applicant_category)
    application.fee_charged = fees.fee_for_application(application.review_type, application.applicant_category)

    documents = [
        {**doc, "url": application_storage.public_url(doc.get("path"))}
        for doc in (application.documents or [])
    ]

    return render(request, "dashboards/admin/application_detail.html", {
        "application": application,
        "documents": documents,
    })


FINANCE_TABS = {"all", "success", "pending", "failed"}


@login_required
@admin_required
def finance(request):
    if request.method == "POST" and request.POST.get("action") == "update_fee":
        ok, note = payment_services.update_fee(
            request.POST.get("review_type", ""),
            request.POST.get("amount", ""),
            updated_by=request.user,
        )
        (messages.success if ok else messages.error)(request, note)
        return redirect(f"{request.path}?tab={request.POST.get('tab', 'all')}")

    active_tab = request.GET.get("tab", "all")
    if active_tab not in FINANCE_TABS:
        active_tab = "all"

    base_qs = payment_services.all_payments()
    counts = payment_services.status_counts(base_qs)
    total_collected = payment_services.total_collected(base_qs)

    return render(request, "dashboards/admin/finance.html", {
        "all_payments": list(base_qs),
        "counts": counts,
        "active_tab": active_tab,
        "total_collected": total_collected,
        "fee_schedule": payment_services.fee_schedule_rows(),
    })


# ---------------------------------------------------------------------
# Reports & Analytics
# ---------------------------------------------------------------------

REPORT_MONTHS = 6


def _role_counts():
    """Distinct-per-user counts across every role, in the same order the
    Reports page and its CSV export both use. Admin also folds in any
    is_superuser account that was created outside the normal role field
    (e.g. `createsuperuser`) so the total always reconciles with
    User.objects.count()."""
    all_users = User.objects.all()
    admins = all_users.filter(role=User.Role.ADMIN) | all_users.filter(is_superuser=True)
    return [
        ("Applicants", all_users.filter(role=User.Role.APPLICANT).count()),
        ("Reviewers", all_users.filter(role=User.Role.REVIEWER, reviewer_status=User.RequestStatus.APPROVED).count()),
        ("Committee", all_users.filter(role=User.Role.COMMITTEE, committee_status=User.RequestStatus.APPROVED).count()),
        ("Secretariat", all_users.filter(role=User.Role.SECRETARIAT).count()),
        ("Chair", all_users.filter(role=User.Role.CHAIR).count()),
        ("Admins", admins.distinct().count()),
    ]


def _monthly_submission_counts():
    """Submitted-application counts for the last REPORT_MONTHS calendar
    months (oldest first), zero-filled for months with nothing submitted
    -- a flat column chart needs every month present, not just the ones
    with data."""
    today = timezone.localdate()
    month_starts = []
    cursor = today.replace(day=1)
    for _ in range(REPORT_MONTHS):
        month_starts.append(cursor)
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    month_starts.reverse()

    counted = {
        row["month"]: row["count"]
        for row in (
            oversight.staff_queryset()
            .annotate(month=TruncMonth("submitted_at"))
            .values("month")
            .annotate(count=Count("id"))
        )
    }
    # TruncMonth keeps whatever submitted_at's type is (a datetime), so
    # match on the same shape rather than assuming a plain date.
    normalized = {}
    for key, count in counted.items():
        if key is None:
            continue
        normalized[key.date() if hasattr(key, "date") else key] = count

    return [{"label": m.strftime("%b"), "count": normalized.get(m, 0)} for m in month_starts]


@login_required
@admin_required
def reports_analytics(request):
    base_qs = oversight.staff_queryset()
    status_breakdown = oversight.status_counts(base_qs)

    decided_qs = base_qs.filter(status__in=[Application.Status.APPROVED, Application.Status.NOT_APPROVED])
    decided_count = decided_qs.count()
    approval_rate = round(status_breakdown["approved"] / decided_count * 100) if decided_count else None

    durations = [
        (a.decided_at - a.submitted_at).days
        for a in decided_qs.exclude(decided_at__isnull=True).exclude(submitted_at__isnull=True)
    ]
    avg_turnaround = round(sum(durations) / len(durations), 1) if durations else None

    review_type_breakdown = [
        {"label": fees.label_for(row["review_type"]), "count": row["count"]}
        for row in base_qs.values("review_type").annotate(count=Count("id")).order_by("-count")
        if row["count"]
    ]
    max_review_type_count = max((r["count"] for r in review_type_breakdown), default=0)

    monthly_breakdown = _monthly_submission_counts()
    max_monthly_count = max((m["count"] for m in monthly_breakdown), default=0)

    payments_qs = payment_services.all_payments()
    payment_counts = payment_services.status_counts(payments_qs)
    total_collected = payment_services.total_collected(payments_qs)

    role_counts = _role_counts()
    max_role_count = max((c for _, c in role_counts), default=0)

    return render(request, "dashboards/admin/reports-analytics.html", {
        "status_breakdown": status_breakdown,
        "approval_rate": approval_rate,
        "avg_turnaround": avg_turnaround,
        "review_type_breakdown": review_type_breakdown,
        "max_review_type_count": max_review_type_count,
        "monthly_breakdown": monthly_breakdown,
        "max_monthly_count": max_monthly_count,
        "payment_counts": payment_counts,
        "total_collected": total_collected,
        "role_counts": role_counts,
        "max_role_count": max_role_count,
        "total_users": User.objects.count(),
    })


@login_required
@admin_required
def reports_analytics_export(request):
    """A plain CSV snapshot of the same numbers the Reports & Analytics
    page shows -- exists so "Export Report" produces something real
    rather than a decorative button with nowhere to go."""
    base_qs = oversight.staff_queryset()
    status_breakdown = oversight.status_counts(base_qs)
    payments_qs = payment_services.all_payments()
    payment_counts = payment_services.status_counts(payments_qs)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="msrec-report-{timezone.localdate().isoformat()}.csv"'
    writer = csv.writer(response)

    writer.writerow(["MSREC Platform Report", timezone.localdate().isoformat()])
    writer.writerow([])
    writer.writerow(["Applications by Status"])
    for key, label in [
        ("submitted", "Submitted"), ("under_review", "Under Review"), ("revisions", "Revisions Required"),
        ("approved", "Approved"), ("not_approved", "Not Approved"),
    ]:
        writer.writerow([label, status_breakdown.get(key, 0)])
    writer.writerow([])
    writer.writerow(["Applications by Review Pathway"])
    for row in base_qs.values("review_type").annotate(count=Count("id")).order_by("-count"):
        writer.writerow([fees.label_for(row["review_type"]), row["count"]])
    writer.writerow([])
    writer.writerow(["Users by Role"])
    for label, count in _role_counts():
        writer.writerow([label, count])
    writer.writerow([])
    writer.writerow(["Payments"])
    writer.writerow(["Successful", payment_counts["success"]])
    writer.writerow(["Pending", payment_counts["pending"]])
    writer.writerow(["Failed", payment_counts["failed"]])
    writer.writerow(["Total Collected (GHS)", payment_services.total_collected(payments_qs)])

    return response


# ---------------------------------------------------------------------
# Access & Security
# ---------------------------------------------------------------------

@login_required
@admin_required
def access_security(request):
    staff_qs = (User.objects.filter(role__in=STAFF_SECURITY_ROLES) | User.objects.filter(is_superuser=True)).distinct()
    staff_list = list(staff_qs)
    total_staff = len(staff_list)
    two_factor_count = sum(1 for u in staff_list if u.two_factor_app or u.two_factor_sms)
    two_factor_pct = round(two_factor_count / total_staff * 100) if total_staff else 0

    staff_by_id = {str(u.pk): u for u in staff_list}
    now = timezone.now()
    sessions = []
    for session in Session.objects.filter(expire_date__gte=now):
        data = session.get_decoded()
        user = staff_by_id.get(data.get("_auth_user_id"))
        if not user:
            continue
        os_label, browser = describe_user_agent(data.get("ua", ""))
        sessions.append({
            "user": user,
            "os": os_label,
            "browser": browser,
            "ip": data.get("login_ip", ""),
            "login_at": parse_datetime(data.get("login_at", "") or ""),
            "is_current": session.session_key == request.session.session_key,
        })
    sessions.sort(key=lambda row: row["login_at"] or now, reverse=True)

    role_counts = _role_counts()
    inactive_count = User.objects.filter(is_active=False).count()

    return render(request, "dashboards/admin/access-security.html", {
        "total_staff": total_staff,
        "two_factor_count": two_factor_count,
        "two_factor_pct": two_factor_pct,
        "sessions": sessions,
        "role_counts": role_counts,
        "inactive_count": inactive_count,
    })


# ---------------------------------------------------------------------
# Profile & Security (the admin's own account)
# ---------------------------------------------------------------------

def _handle_admin_update_profile(request):
    user = request.user
    title = request.POST.get("title", "").strip()
    first_name = request.POST.get("first_name", "").strip()
    last_name = request.POST.get("last_name", "").strip()
    phone = request.POST.get("phone", "").strip()
    email = request.POST.get("email", "").strip().lower()
    confirm_email = request.POST.get("confirm_email", "").strip().lower()

    if not first_name or not last_name:
        messages.error(request, "First and last name are required.")
        return
    if not email:
        messages.error(request, "Email is required.")
        return
    if email != confirm_email:
        messages.error(request, "Email and Confirm Email don't match.")
        return
    if User.objects.exclude(pk=user.pk).filter(email=email).exists():
        messages.error(request, "Another account already uses that email address.")
        return

    user.title = title
    user.first_name = first_name
    user.last_name = last_name
    user.phone = phone
    user.email = email
    user.two_factor_app = bool(request.POST.get("two_factor_app"))
    user.two_factor_sms = bool(request.POST.get("two_factor_sms"))
    user.notify_new_signin = bool(request.POST.get("notify_new_signin"))

    update_fields = [
        "title", "first_name", "last_name", "phone", "email",
        "two_factor_app", "two_factor_sms", "notify_new_signin",
    ]

    current_password = request.POST.get("current_password", "")
    new_password = request.POST.get("new_password", "")
    confirm_password = request.POST.get("confirm_password", "")
    if current_password or new_password or confirm_password:
        if not current_password or not user.check_password(current_password):
            messages.error(request, "Your current password is incorrect.")
            return
        if new_password != confirm_password:
            messages.error(request, "New password and confirmation don't match.")
            return
        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return
        user.set_password(new_password)
        update_fields.append("password")

    user.save(update_fields=update_fields)
    if "password" in update_fields:
        update_session_auth_hash(request, user)
        messages.success(request, "Profile updated and password changed.")
    else:
        messages.success(request, "Profile updated.")


def _handle_admin_update_avatar(request):
    uploaded = request.FILES.get("avatar")
    if not uploaded:
        messages.error(request, "Choose an image to upload first.")
        return
    if not (uploaded.content_type or "").startswith("image/"):
        messages.error(request, "Please upload an image file (JPG, PNG or WEBP).")
        return

    object_path = application_storage.upload_avatar_file(uploaded, user_id=request.user.pk)
    if not object_path:
        messages.error(request, "Couldn't upload your photo right now. Please try again.")
        return

    request.user.profile_photo_path = object_path
    request.user.save(update_fields=["profile_photo_path"])
    messages.success(request, "Profile photo updated.")


def _handle_admin_remove_avatar(request):
    user = request.user
    if user.profile_photo_path:
        if user.profile_photo_path.startswith("reviewers/"):
            reviewer_storage.delete_object(user.profile_photo_path)
        elif user.profile_photo_path.startswith("avatars/"):
            application_storage.delete_object(user.profile_photo_path)
        else:
            storage.delete_object(user.profile_photo_path)
        user.profile_photo_path = ""
        user.save(update_fields=["profile_photo_path"])
    messages.success(request, "Profile photo removed.")


def _handle_admin_revoke_session(request):
    session_key = request.POST.get("session_key", "")
    if session_key and session_key != request.session.session_key:
        session = Session.objects.filter(pk=session_key).first()
        if session and session.get_decoded().get("_auth_user_id") == str(request.user.pk):
            session.delete()
            messages.success(request, "That session has been signed out.")
            return
    messages.error(request, "That session could not be found.")


@login_required
@admin_or_secretariat_required
def profile_security(request, template_name="dashboards/admin/profile-security.html"):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_profile":
            _handle_admin_update_profile(request)
        elif action == "update_avatar":
            _handle_admin_update_avatar(request)
        elif action == "remove_avatar":
            _handle_admin_remove_avatar(request)
        elif action == "revoke_session":
            _handle_admin_revoke_session(request)
        else:
            messages.error(request, "That request could not be processed.")
        return redirect(request.path)

    sessions = active_sessions_for(request.user, current_session_key=request.session.session_key)
    return render(request, template_name, {"sessions": sessions})


# ---------------------------------------------------------------------
# Help & Support
# ---------------------------------------------------------------------

@login_required
@admin_required
def help_support(request):
    return render(request, "dashboards/admin/help-support.html")


BOARD_COMMITTEE_TABS = {"all", "board", "committee", "secretariat"}


def _handle_governance_add(request):
    full_name = request.POST.get("full_name", "").strip()
    role_title = request.POST.get("role_title", "").strip()
    tag = request.POST.get("tag", "").strip()
    group = request.POST.get("group", "")
    display_order = request.POST.get("display_order", "").strip()

    if not full_name or not role_title:
        messages.error(request, "Name and role/title are required.")
        return
    if group not in {c for c, _ in GovernanceMember.Group.choices}:
        messages.error(request, "Choose a valid group (Board, Committee or Secretariat).")
        return

    member = GovernanceMember.objects.create(
        full_name=full_name, role_title=role_title, tag=tag, group=group,
        display_order=int(display_order) if display_order.isdigit() else 0,
    )

    photo = request.FILES.get("photo")
    if photo:
        object_path = pages_storage.upload_member_photo(photo, member_id=member.pk)
        if object_path:
            member.photo_path = object_path
            member.save(update_fields=["photo_path"])
        else:
            messages.warning(request, f"{full_name} was added, but the photo couldn't be uploaded right now.")

    messages.success(request, f"{full_name} added to {member.get_group_display()}.")


def _handle_governance_edit(request, member):
    full_name = request.POST.get("full_name", "").strip()
    role_title = request.POST.get("role_title", "").strip()
    tag = request.POST.get("tag", "").strip()
    group = request.POST.get("group", "")
    display_order = request.POST.get("display_order", "").strip()

    if not full_name or not role_title:
        messages.error(request, "Name and role/title are required.")
        return
    if group not in {c for c, _ in GovernanceMember.Group.choices}:
        messages.error(request, "Choose a valid group (Board, Committee or Secretariat).")
        return

    member.full_name = full_name
    member.role_title = role_title
    member.tag = tag
    member.group = group
    member.display_order = int(display_order) if display_order.isdigit() else 0
    member.is_active = bool(request.POST.get("is_active"))

    photo = request.FILES.get("photo")
    if photo:
        old_path = member.photo_path
        object_path = pages_storage.upload_member_photo(photo, member_id=member.pk)
        if object_path:
            member.photo_path = object_path
            if old_path and old_path != object_path:
                pages_storage.delete_object(old_path)
        else:
            messages.warning(request, "The new photo couldn't be uploaded right now -- everything else was saved.")

    member.save()
    messages.success(request, f"{full_name} updated.")


def _handle_governance_delete(request, member):
    if member.photo_path:
        pages_storage.delete_object(member.photo_path)
    name = member.full_name
    member.delete()
    messages.success(request, f"{name} removed from the Board & Committee page.")


@login_required
@admin_required
def board_committee(request):
    if request.method == "POST":
        action = request.POST.get("action")
        tab = request.POST.get("tab", "all")

        if action == "add":
            _handle_governance_add(request)
        else:
            member_id = request.POST.get("member_id", "")
            if not member_id.isdigit():
                messages.error(request, "That request could not be processed.")
                return redirect(f"{request.path}?tab={tab}")
            member = get_object_or_404(GovernanceMember, pk=member_id)

            if action == "edit":
                _handle_governance_edit(request, member)
            elif action == "delete":
                _handle_governance_delete(request, member)
            else:
                messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}?tab={tab}")

    active_tab = request.GET.get("tab", "all")
    if active_tab not in BOARD_COMMITTEE_TABS:
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

    return render(request, "dashboards/admin/board-committee.html", {
        "members": members,
        "counts": counts,
        "active_tab": active_tab,
        "groups": GovernanceMember.Group.choices,
    })


# ---------------------------------------------------------------------
# Committee -- Overview, Membership/Appointments, Terms & Expiry,
# Training and Conflict Records. All four read/write the governance
# tables added alongside GovernanceMember (pages.models): one
# appointment/training/conflict history per Board or Committee member.
# Membership/Appointments and Terms & Expiry are two views onto the same
# CommitteeAppointment table -- one for "who holds what seat", the other
# sorted/filtered by how soon a term runs out.
# ---------------------------------------------------------------------

def _active_governance_members():
    return list(GovernanceMember.objects.filter(is_active=True).order_by("group", "display_order", "full_name"))


@login_required
@admin_required
def committee_overview(request):
    members = list(GovernanceMember.objects.all())
    appointments = list(CommitteeAppointment.objects.select_related("member").all())
    training_records = list(TrainingRecord.objects.select_related("member").all())
    conflicts = list(ConflictDeclaration.objects.select_related("member").all())

    counts = {
        "members": sum(1 for m in members if m.is_active),
        "board": sum(1 for m in members if m.is_active and m.group == GovernanceMember.Group.BOARD),
        "committee": sum(1 for m in members if m.is_active and m.group == GovernanceMember.Group.COMMITTEE),
        "secretariat": sum(1 for m in members if m.is_active and m.group == GovernanceMember.Group.SECRETARIAT),
        "appointments_expiring": sum(1 for a in appointments if a.expiry_state == "expiring"),
        "appointments_expired": sum(1 for a in appointments if a.expiry_state == "expired"),
        "training_expiring": sum(1 for t in training_records if t.expiry_state == "expiring"),
        "training_expired": sum(1 for t in training_records if t.expiry_state == "expired"),
        "conflicts_open": sum(1 for c in conflicts if c.status in (ConflictDeclaration.Status.PENDING, ConflictDeclaration.Status.REVIEWED)),
    }

    upcoming_expiries = sorted(
        (a for a in appointments if a.expiry_state in ("expiring", "expired")),
        key=lambda a: (a.end_date is None, a.end_date),
    )[:6]
    upcoming_training = sorted(
        (t for t in training_records if t.expiry_state in ("expiring", "expired")),
        key=lambda t: (t.expiry_date is None, t.expiry_date),
    )[:6]
    recent_conflicts = sorted(conflicts, key=lambda c: c.date_declared, reverse=True)[:6]

    return render(request, "dashboards/admin/committee/overview.html", {
        "counts": counts,
        "upcoming_expiries": upcoming_expiries,
        "upcoming_training": upcoming_training,
        "recent_conflicts": recent_conflicts,
    })


def _handle_appointment_add(request):
    member = get_object_or_404(GovernanceMember, pk=request.POST.get("member_id"))
    seat_title = request.POST.get("seat_title", "").strip()
    start_date = request.POST.get("start_date", "").strip()

    if not seat_title or not start_date:
        messages.error(request, "Seat / title and start date are required.")
        return

    appointment = CommitteeAppointment.objects.create(
        member=member,
        seat_title=seat_title,
        appointed_by=request.POST.get("appointed_by", "").strip(),
        start_date=start_date,
        end_date=request.POST.get("end_date") or None,
        status=request.POST.get("status") or CommitteeAppointment.Status.ACTIVE,
        notes=request.POST.get("notes", "").strip(),
    )

    letter = request.FILES.get("letter")
    if letter:
        object_path = documents_storage.upload_document(letter, folder=f"appointments/{appointment.pk}")
        if object_path:
            appointment.letter_path = object_path
            appointment.save(update_fields=["letter_path"])
        else:
            messages.warning(request, "The appointment was saved, but the letter couldn't be uploaded right now.")

    messages.success(request, f"Appointment recorded for {member.full_name}.")


def _handle_appointment_edit(request, appointment):
    seat_title = request.POST.get("seat_title", "").strip()
    start_date = request.POST.get("start_date", "").strip()

    if not seat_title or not start_date:
        messages.error(request, "Seat / title and start date are required.")
        return

    appointment.seat_title = seat_title
    appointment.appointed_by = request.POST.get("appointed_by", "").strip()
    appointment.start_date = start_date
    appointment.end_date = request.POST.get("end_date") or None
    appointment.status = request.POST.get("status") or CommitteeAppointment.Status.ACTIVE
    appointment.notes = request.POST.get("notes", "").strip()

    letter = request.FILES.get("letter")
    if letter:
        old_path = appointment.letter_path
        object_path = documents_storage.upload_document(letter, folder=f"appointments/{appointment.pk}")
        if object_path:
            appointment.letter_path = object_path
            if old_path and old_path != object_path:
                documents_storage.delete_object(old_path)
        else:
            messages.warning(request, "The new letter couldn't be uploaded right now -- everything else was saved.")

    appointment.save()
    messages.success(request, "Appointment updated.")


APPOINTMENT_TABS = {"all", "active", "renewed", "expired", "terminated"}


@login_required
@admin_required
def membership_appointments(request):
    if request.method == "POST":
        action = request.POST.get("action")
        tab = request.POST.get("tab", "all")

        if action == "add":
            _handle_appointment_add(request)
        else:
            appointment = get_object_or_404(CommitteeAppointment, pk=request.POST.get("appointment_id", ""))
            if action == "edit":
                _handle_appointment_edit(request, appointment)
            elif action == "delete":
                if appointment.letter_path:
                    documents_storage.delete_object(appointment.letter_path)
                name = appointment.member.full_name
                appointment.delete()
                messages.success(request, f"Appointment record for {name} removed.")
            else:
                messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}?tab={tab}")

    active_tab = request.GET.get("tab", "all")
    if active_tab not in APPOINTMENT_TABS:
        active_tab = "all"

    appointments = list(CommitteeAppointment.objects.select_related("member").all())
    for appointment in appointments:
        appointment.letter_url = documents_storage.public_url(appointment.letter_path)

    counts = {"all": len(appointments)}
    for value, _label in CommitteeAppointment.Status.choices:
        counts[value] = sum(1 for a in appointments if a.status == value)

    return render(request, "dashboards/admin/committee/appointments.html", {
        "appointments": appointments,
        "counts": counts,
        "active_tab": active_tab,
        "members": _active_governance_members(),
        "statuses": CommitteeAppointment.Status.choices,
    })


EXPIRY_TABS = {"all", "expiring", "expired", "ongoing"}


@login_required
@admin_required
def terms_expiry(request):
    if request.method == "POST":
        action = request.POST.get("action")
        tab = request.POST.get("tab", "all")
        appointment = get_object_or_404(CommitteeAppointment, pk=request.POST.get("appointment_id", ""))

        if action == "edit":
            _handle_appointment_edit(request, appointment)
        else:
            messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}?tab={tab}")

    active_tab = request.GET.get("tab", "all")
    if active_tab not in EXPIRY_TABS:
        active_tab = "all"

    appointments = list(CommitteeAppointment.objects.select_related("member").all())
    appointments.sort(key=lambda a: (a.end_date is None, a.end_date))

    counts = {
        "all": len(appointments),
        "expiring": sum(1 for a in appointments if a.expiry_state == "expiring"),
        "expired": sum(1 for a in appointments if a.expiry_state == "expired"),
        "ongoing": sum(1 for a in appointments if a.expiry_state in ("ongoing", "current")),
    }

    return render(request, "dashboards/admin/committee/terms-expiry.html", {
        "appointments": appointments,
        "counts": counts,
        "active_tab": active_tab,
        "statuses": CommitteeAppointment.Status.choices,
    })


def _handle_training_add(request):
    member = get_object_or_404(GovernanceMember, pk=request.POST.get("member_id"))
    course_title = request.POST.get("course_title", "").strip()

    if not course_title:
        messages.error(request, "Course / training title is required.")
        return

    record = TrainingRecord.objects.create(
        member=member,
        course_title=course_title,
        provider=request.POST.get("provider", "").strip(),
        completed_date=request.POST.get("completed_date") or None,
        expiry_date=request.POST.get("expiry_date") or None,
        notes=request.POST.get("notes", "").strip(),
    )

    certificate = request.FILES.get("certificate")
    if certificate:
        object_path = documents_storage.upload_document(certificate, folder=f"training/{record.pk}")
        if object_path:
            record.certificate_path = object_path
            record.save(update_fields=["certificate_path"])
        else:
            messages.warning(request, "The record was saved, but the certificate couldn't be uploaded right now.")

    messages.success(request, f"Training record added for {member.full_name}.")


def _handle_training_edit(request, record):
    course_title = request.POST.get("course_title", "").strip()
    if not course_title:
        messages.error(request, "Course / training title is required.")
        return

    record.course_title = course_title
    record.provider = request.POST.get("provider", "").strip()
    record.completed_date = request.POST.get("completed_date") or None
    record.expiry_date = request.POST.get("expiry_date") or None
    record.notes = request.POST.get("notes", "").strip()

    certificate = request.FILES.get("certificate")
    if certificate:
        old_path = record.certificate_path
        object_path = documents_storage.upload_document(certificate, folder=f"training/{record.pk}")
        if object_path:
            record.certificate_path = object_path
            if old_path and old_path != object_path:
                documents_storage.delete_object(old_path)
        else:
            messages.warning(request, "The new certificate couldn't be uploaded right now -- everything else was saved.")

    record.save()
    messages.success(request, "Training record updated.")


TRAINING_TABS = {"all", "current", "expiring", "expired", "ongoing"}


@login_required
@admin_required
def training(request):
    if request.method == "POST":
        action = request.POST.get("action")
        tab = request.POST.get("tab", "all")

        if action == "add":
            _handle_training_add(request)
        else:
            record = get_object_or_404(TrainingRecord, pk=request.POST.get("record_id", ""))
            if action == "edit":
                _handle_training_edit(request, record)
            elif action == "delete":
                if record.certificate_path:
                    documents_storage.delete_object(record.certificate_path)
                name = record.member.full_name
                record.delete()
                messages.success(request, f"Training record for {name} removed.")
            else:
                messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}?tab={tab}")

    active_tab = request.GET.get("tab", "all")
    if active_tab not in TRAINING_TABS:
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

    return render(request, "dashboards/admin/committee/training.html", {
        "records": records,
        "counts": counts,
        "active_tab": active_tab,
        "members": _active_governance_members(),
    })


def _handle_conflict_add(request):
    member = get_object_or_404(GovernanceMember, pk=request.POST.get("member_id"))
    description = request.POST.get("description", "").strip()

    if not description:
        messages.error(request, "A description of the conflict is required.")
        return

    ConflictDeclaration.objects.create(
        member=member,
        related_to=request.POST.get("related_to", "").strip(),
        date_declared=request.POST.get("date_declared") or timezone.now().date(),
        description=description,
        status=request.POST.get("status") or ConflictDeclaration.Status.PENDING,
        recorded_by=request.user,
    )
    messages.success(request, f"Conflict of interest record added for {member.full_name}.")


def _handle_conflict_edit(request, record):
    description = request.POST.get("description", "").strip()
    if not description:
        messages.error(request, "A description of the conflict is required.")
        return

    new_status = request.POST.get("status") or ConflictDeclaration.Status.PENDING
    record.related_to = request.POST.get("related_to", "").strip()
    record.date_declared = request.POST.get("date_declared") or record.date_declared
    record.description = description
    record.resolution_notes = request.POST.get("resolution_notes", "").strip()

    if new_status in (ConflictDeclaration.Status.RESOLVED, ConflictDeclaration.Status.RECUSED) and record.status != new_status:
        record.resolved_at = timezone.now()
    record.status = new_status

    record.save()
    messages.success(request, "Conflict of interest record updated.")


CONFLICT_TABS = {"all", "pending", "reviewed", "recused", "resolved"}


@login_required
@admin_required
def conflict_records(request):
    if request.method == "POST":
        action = request.POST.get("action")
        tab = request.POST.get("tab", "all")

        if action == "add":
            _handle_conflict_add(request)
        else:
            record = get_object_or_404(ConflictDeclaration, pk=request.POST.get("record_id", ""))
            if action == "edit":
                _handle_conflict_edit(request, record)
            elif action == "delete":
                name = record.member.full_name
                record.delete()
                messages.success(request, f"Conflict of interest record for {name} removed.")
            else:
                messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}?tab={tab}")

    active_tab = request.GET.get("tab", "all")
    if active_tab not in CONFLICT_TABS:
        active_tab = "all"

    records = list(ConflictDeclaration.objects.select_related("member").all())

    counts = {"all": len(records)}
    for value, _label in ConflictDeclaration.Status.choices:
        counts[value] = sum(1 for r in records if r.status == value)

    return render(request, "dashboards/admin/committee/conflict-records.html", {
        "records": records,
        "counts": counts,
        "active_tab": active_tab,
        "members": _active_governance_members(),
        "statuses": ConflictDeclaration.Status.choices,
    })


# ---------------------------------------------------------------------
# Site Settings -- the one SiteSettings row (pages.models.SiteSettings.
# get_solo()). Four independent forms on one page, each its own POST
# `action`, the same "several small forms on one page" shape as
# finance()'s Fee Schedule editor above.
# ---------------------------------------------------------------------

def _mask_secret(key):
    """Never echo a saved secret back in full -- last 4 characters only,
    so an admin can confirm which key is active without the real value
    ever round-tripping into rendered HTML (view-source, browser
    autofill, a shoulder-surfed screen share, etc.)."""
    if not key:
        return ""
    return f"{'•' * 10}{key[-4:]}" if len(key) > 4 else "••••"


def _handle_settings_identity(request, site):
    site_name = request.POST.get("site_name", "").strip()
    if not site_name:
        messages.error(request, "Site name is required.")
        return
    site.site_name = site_name

    logo = request.FILES.get("logo")
    if logo:
        if not (logo.content_type or "").startswith("image/"):
            messages.error(request, "Logo must be an image file.")
            return
        old_path = site.logo_path
        object_path = pages_storage.upload_site_logo(logo)
        if object_path:
            site.logo_path = object_path
            if old_path and old_path != object_path:
                pages_storage.delete_object(old_path)
        else:
            messages.warning(request, "Site name saved, but the new logo couldn't be uploaded right now.")

    site.updated_by = request.user
    site.save()
    messages.success(request, "Site identity updated.")


def _handle_settings_footer(request, site):
    footer_email = request.POST.get("footer_email", "").strip()
    if footer_email:
        try:
            validate_email(footer_email)
        except ValidationError:
            messages.error(request, "Enter a valid footer contact email.")
            return

    site.footer_about = request.POST.get("footer_about", "").strip()
    site.footer_address = request.POST.get("footer_address", "").strip()
    site.footer_phone = request.POST.get("footer_phone", "").strip()
    site.footer_email = footer_email
    site.social_twitter_url = request.POST.get("social_twitter_url", "").strip()
    site.social_facebook_url = request.POST.get("social_facebook_url", "").strip()
    site.social_instagram_url = request.POST.get("social_instagram_url", "").strip()
    site.social_linkedin_url = request.POST.get("social_linkedin_url", "").strip()
    site.updated_by = request.user
    site.save()
    messages.success(request, "Footer updated.")


def _handle_settings_contact(request, site):
    email_fields = {
        "contact_secretariat_email": "Secretariat",
        "contact_applications_email": "Application Support",
        "contact_complaints_email": "Complaints",
        "contact_ethics_email": "Ethics Concerns",
        "contact_techsupport_email": "Technical Support",
    }
    cleaned = {}
    for field, label in email_fields.items():
        value = request.POST.get(field, "").strip()
        if value:
            try:
                validate_email(value)
            except ValidationError:
                messages.error(request, f"Enter a valid {label} email address.")
                return
        cleaned[field] = value

    for field, value in cleaned.items():
        setattr(site, field, value)
    site.contact_phone = request.POST.get("contact_phone", "").strip()
    site.updated_by = request.user
    site.save()
    messages.success(request, "Contact page details updated.")


def _handle_settings_paystack(request, site):
    site.paystack_public_key = request.POST.get("paystack_public_key", "").strip()
    # A blank secret-key input means "keep the saved one" -- the field is
    # never pre-filled with the real value (see _mask_secret / the view
    # below), so treating an empty submit as "clear it" would silently
    # break checkout the next time someone saves this form without also
    # retyping a secret they were never shown.
    secret_key = request.POST.get("paystack_secret_key", "").strip()
    if secret_key:
        site.paystack_secret_key = secret_key
    site.updated_by = request.user
    site.save()
    messages.success(request, "Payment gateway settings updated.")


def _parse_local_datetime(value):
    """Parses an <input type="datetime-local"> value into a timezone-aware
    datetime -- that input has no timezone of its own, so naive-vs-aware
    is resolved once, here, the same idea as
    secretariat_dashboard.views.parse_datetime_local."""
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        return None
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def _handle_settings_add_meeting(request, site):
    title = request.POST.get("meeting_title", "").strip()
    scheduled_at = _parse_local_datetime(request.POST.get("meeting_scheduled_at"))
    if not title or not scheduled_at:
        messages.error(request, "A meeting needs at least a title and a date/time.")
        return

    CommitteeMeeting.objects.create(
        title=title,
        scheduled_at=scheduled_at,
        location=request.POST.get("meeting_location", "").strip(),
        meeting_link=request.POST.get("meeting_link", "").strip(),
        agenda=request.POST.get("meeting_agenda", "").strip(),
    )
    messages.success(request, f'"{title}" was added to the meetings calendar.')


def _handle_settings_delete_meeting(request, site):
    meeting = get_object_or_404(CommitteeMeeting, pk=request.POST.get("meeting_id"))
    for doc in meeting.documents.all():
        if doc.file_path:
            documents_storage.delete_object(doc.file_path)
    title = meeting.title
    meeting.delete()
    messages.success(request, f'"{title}" and its documents were deleted.')


def _handle_settings_add_meeting_document(request, site):
    meeting = get_object_or_404(CommitteeMeeting, pk=request.POST.get("meeting_id"))
    title = request.POST.get("document_title", "").strip()
    doc_type = request.POST.get("doc_type", MeetingDocument.DocType.OTHER)
    upload = request.FILES.get("document_file")

    if not title:
        messages.error(request, "Give the document a title.")
        return
    if doc_type not in MeetingDocument.DocType.values:
        doc_type = MeetingDocument.DocType.OTHER

    document = MeetingDocument.objects.create(meeting=meeting, title=title, doc_type=doc_type)
    if upload:
        object_path = documents_storage.upload_document(upload, folder=f"meetings/{meeting.pk}")
        if object_path:
            document.file_path = object_path
            document.file_size = upload.size
            document.save(update_fields=["file_path", "file_size"])
        else:
            messages.warning(request, f'"{title}" was saved, but the file upload failed -- try again from here.')
    messages.success(request, f'"{title}" was added to {meeting.title}.')


def _handle_settings_delete_meeting_document(request, site):
    document = get_object_or_404(MeetingDocument, pk=request.POST.get("document_id"))
    if document.file_path:
        documents_storage.delete_object(document.file_path)
    title = document.title
    document.delete()
    messages.success(request, f'"{title}" was deleted.')


def _handle_settings_add_policy_document(request, site):
    category = request.POST.get("category", "")
    title = request.POST.get("policy_title", "").strip()
    upload = request.FILES.get("policy_file")

    if category not in PolicyDocument.Category.values:
        messages.error(request, "Choose a valid category.")
        return
    if not title:
        messages.error(request, "Give the document a title.")
        return

    document = PolicyDocument.objects.create(
        category=category,
        title=title,
        description=request.POST.get("policy_description", "").strip(),
        version=request.POST.get("policy_version", "").strip(),
        display_order=request.POST.get("policy_display_order") or 0,
    )
    if upload:
        object_path = documents_storage.upload_document(upload, folder=f"policies/{document.pk}")
        if object_path:
            document.file_path = object_path
            document.file_size = upload.size
            document.save(update_fields=["file_path", "file_size"])
        else:
            messages.warning(request, f'"{title}" was saved, but the file upload failed -- try again from here.')
    messages.success(request, f'"{title}" was added to {document.get_category_display()}.')


def _handle_settings_edit_policy_document(request, site):
    document = get_object_or_404(PolicyDocument, pk=request.POST.get("document_id"))
    title = request.POST.get("policy_title", "").strip()
    if not title:
        messages.error(request, "Give the document a title.")
        return

    document.title = title
    document.description = request.POST.get("policy_description", "").strip()
    document.version = request.POST.get("policy_version", "").strip()
    document.display_order = request.POST.get("policy_display_order") or 0

    upload = request.FILES.get("policy_file")
    if upload:
        old_path = document.file_path
        object_path = documents_storage.upload_document(upload, folder=f"policies/{document.pk}")
        if object_path:
            document.file_path = object_path
            document.file_size = upload.size
            if old_path and old_path != object_path:
                documents_storage.delete_object(old_path)
        else:
            messages.warning(request, "Details saved, but the replacement file upload failed -- try again.")
    document.save()
    messages.success(request, f'"{title}" was updated.')


def _handle_settings_delete_policy_document(request, site):
    document = get_object_or_404(PolicyDocument, pk=request.POST.get("document_id"))
    if document.file_path:
        documents_storage.delete_object(document.file_path)
    title = document.title
    document.delete()
    messages.success(request, f'"{title}" was deleted.')


@login_required
@admin_or_secretariat_required
def site_settings(request):
    site = SiteSettings.get_solo()

    if request.method == "POST":
        handler = {
            "update_identity": _handle_settings_identity,
            "update_footer": _handle_settings_footer,
            "update_contact": _handle_settings_contact,
            "update_paystack": _handle_settings_paystack,
            "add_meeting": _handle_settings_add_meeting,
            "delete_meeting": _handle_settings_delete_meeting,
            "add_meeting_document": _handle_settings_add_meeting_document,
            "delete_meeting_document": _handle_settings_delete_meeting_document,
            "add_policy_document": _handle_settings_add_policy_document,
            "edit_policy_document": _handle_settings_edit_policy_document,
            "delete_policy_document": _handle_settings_delete_policy_document,
        }.get(request.POST.get("action"))
        if handler:
            handler(request, site)
        else:
            messages.error(request, "That request could not be processed.")
        return redirect("admin_dashboard:settings")

    meetings = list(
        CommitteeMeeting.objects.prefetch_related("documents").order_by("-scheduled_at")
    )
    for meeting in meetings:
        for doc in meeting.documents.all():
            doc.download_url = documents_storage.public_url(doc.file_path)

    policy_documents = list(PolicyDocument.objects.all())
    for doc in policy_documents:
        doc.download_url = documents_storage.public_url(doc.file_path)
    policy_groups = [
        (value, label, [doc for doc in policy_documents if doc.category == value])
        for value, label in PolicyDocument.Category.choices
    ]

    editing_policy = None
    edit_policy_id = request.GET.get("edit_policy")
    if edit_policy_id:
        editing_policy = get_object_or_404(PolicyDocument, pk=edit_policy_id)

    return render(request, "dashboards/admin/settings.html", {
        "site": site,
        "logo_url": pages_storage.public_url(site.logo_path),
        "paystack_secret_key_masked": _mask_secret(site.paystack_secret_key),
        "using_env_public_key": not site.paystack_public_key,
        "using_env_secret_key": not site.paystack_secret_key,
        "env_paystack_public_key": django_settings.PAYSTACK_PUBLIC_KEY,
        "meetings": meetings,
        "meeting_doc_types": MeetingDocument.DocType.choices,
        "policy_categories": PolicyDocument.Category.choices,
        "policy_groups": policy_groups,
        "editing_policy": editing_policy,
    })
