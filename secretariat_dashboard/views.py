from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts import storage as accounts_storage
from accounts.models import RoleApprovalLog, User
from applicant_dashboard import oversight
from applicant_dashboard import storage as application_storage
from applicant_dashboard.models import Application
from messaging.access import is_staff_side
from notifications import services as notification_services
from notifications.emails import send_branded_email
from notifications.models import Notification
from payments import services as payment_services
from reviewer_dashboard.models import ReviewAssignment

staff_required = user_passes_test(is_staff_side, login_url="pages:login")

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

    base_qs = oversight.staff_queryset().order_by("-submitted_at")
    counts = oversight.status_counts(base_qs)

    all_applications = list(base_qs)
    for application in all_applications:
        application.tab = oversight.STATUS_TO_TAB.get(application.status, "all")

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
            due_date = request.POST.get("due_date") or None
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
