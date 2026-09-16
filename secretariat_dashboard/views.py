from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Prefetch, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from accounts import storage as accounts_storage
from accounts.models import RoleApprovalLog, User
from applicant_dashboard import oversight
from applicant_dashboard import storage as application_storage
from applicant_dashboard.models import Application
from communications import services as communications_services
from communications.emails_preview import render_template_preview
from communications.models import Announcement, AudienceChoices, EmailTemplate, Reminder
from messaging.access import is_staff_side
from notifications import services as notification_services
from notifications.emails import send_branded_email
from notifications.models import Notification
from payments import services as payment_services
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
REVIEWER_ASSIGNMENT_TABS = {"assign", "pending", "workload"}


@login_required
@staff_required
def home(request):
    base_qs = oversight.staff_queryset()
    counts = {
        "submitted": base_qs.filter(status=Application.Status.SUBMITTED).count(),
        "under_review": base_qs.filter(status=Application.Status.UNDER_REVIEW).count(),
        "revisions": base_qs.filter(status=Application.Status.REVISIONS_REQUIRED).count(),
        "approved": base_qs.filter(status=Application.Status.APPROVED).count(),
    }
    submitted_qs = base_qs.filter(status=Application.Status.SUBMITTED)
    recent_submissions = submitted_qs.order_by("-submitted_at")[:8]
    oldest_submission = submitted_qs.order_by("submitted_at").first()

    return render(request, "dashboards/secretariat.html", {
        "counts": counts,
        "recent_submissions": recent_submissions,
        "oldest_submission": oldest_submission,
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


@login_required
@staff_required
def application_detail(request, pk):
    application = get_object_or_404(oversight.staff_queryset(), pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        comment = request.POST.get("revision_comment", "")
        ok, note = oversight.apply_transition(application, action, comment=comment)
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

    return render(request, "dashboards/secretariat/application_detail.html", {
        "application": application,
        "documents": documents,
    })


FINANCE_TABS = {"all", "success", "pending", "failed"}


@login_required
@staff_required
def finance(request):
    active_tab = request.GET.get("tab", "all")
    if active_tab not in FINANCE_TABS:
        active_tab = "all"

    base_qs = payment_services.all_payments()
    counts = payment_services.status_counts(base_qs)
    total_collected = payment_services.total_collected(base_qs)

    return render(request, "dashboards/secretariat/finance.html", {
        "all_payments": list(base_qs),
        "counts": counts,
        "active_tab": active_tab,
        "total_collected": total_collected,
        "fee_schedule": payment_services.fee_schedule_rows(),
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
                ReviewAssignment, pk=assignment_id, status=ReviewAssignment.Status.NEW,
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
        "workload": len(reviewers),
    }

    return render(request, "dashboards/secretariat/reviewer-assignment.html", {
        "active_tab": active_tab,
        "needs_assignment": needs_assignment,
        "pending": pending,
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
