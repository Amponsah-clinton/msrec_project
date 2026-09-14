from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from applicant_dashboard import oversight
from applicant_dashboard import storage as application_storage
from applicant_dashboard.models import Application
from messaging.access import is_staff_side
from notifications import services as notification_services
from notifications.models import Notification
from payments import services as payment_services

staff_required = user_passes_test(is_staff_side, login_url="pages:login")


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
def application_detail(request, pk):
    application = get_object_or_404(oversight.staff_queryset(), pk=pk)

    if request.method == "POST":
        ok, note = oversight.apply_transition(application, request.POST.get("action"))
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
