from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts import storage
from accounts.models import RoleApprovalLog, User
from applicant_dashboard import oversight
from applicant_dashboard import storage as application_storage
from pages.models import Inquiry
from payments import services as payment_services

TABS = {"all", "pending", "applicants", "reviewers", "committee", "admins"}
INQUIRY_TABS = {"all", "new", "resolved"}


def is_admin(user):
    return user.is_authenticated and (user.is_superuser or user.role == User.Role.ADMIN)


admin_required = user_passes_test(is_admin, login_url="pages:login")


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


def _handle_role_decision(request, target, role, action):
    if role not in (User.Role.REVIEWER, User.Role.COMMITTEE) or action not in ("approve", "reject"):
        messages.error(request, "That request could not be processed.")
        return

    if action == "approve":
        target.approve_role(role)
        RoleApprovalLog.objects.create(
            user=target, role=role, action=RoleApprovalLog.Action.APPROVED, acted_by=request.user,
        )
        messages.success(request, f"{target.full_name} approved as {target.get_role_display()}.")
    else:
        target.reject_role(role)
        RoleApprovalLog.objects.create(
            user=target, role=role, action=RoleApprovalLog.Action.REJECTED, acted_by=request.user,
        )
        messages.success(request, f"{role.title()} request for {target.full_name} was declined.")


def _handle_suspend(request, target, *, suspend):
    if target.pk == request.user.pk:
        messages.error(request, "You can't suspend your own account.")
        return
    if suspend and target.is_superuser:
        messages.error(request, "Superuser accounts can't be suspended from here.")
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
        messages.success(request, f"{target.full_name}'s account has been suspended.")
    else:
        messages.success(request, f"{target.full_name}'s account has been reactivated.")


def _handle_delete(request, target):
    if target.pk == request.user.pk:
        messages.error(request, "You can't delete your own account.")
        return
    if target.is_superuser:
        messages.error(request, "Superuser accounts can't be deleted from here.")
        return
    name = target.full_name
    target.delete()
    messages.success(request, f"{name}'s account has been deleted.")


def _handle_edit(request, target):
    email = request.POST.get("email", "").strip().lower()
    if not email:
        messages.error(request, "Email is required.")
        return
    if User.objects.exclude(pk=target.pk).filter(email=email).exists():
        messages.error(request, "Another account already uses that email address.")
        return

    role = request.POST.get("role", target.role)
    if role not in User.Role.values:
        role = target.role

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
    messages.success(request, f"{target.full_name}'s account has been updated.")


@login_required
@admin_required
def accounts(request):
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

    return render(request, "dashboards/admin/accounts.html", {
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
    send_mail(
        subject=f"Re: Your message to MSREC ({inquiry.get_reason_display()})",
        message=(
            f"Hi {inquiry.name},\n\n{reply_message}\n\n"
            "— MSREC Secretariat\n\n"
            "---\n"
            f"Your original message ({inquiry.created_at:%d %b %Y}):\n{inquiry.message}"
        ),
        from_email=None,
        recipient_list=[inquiry.email],
        fail_silently=True,
    )
    messages.success(request, f"Reply sent to {inquiry.name} ({inquiry.email}).")


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

    return render(request, "dashboards/admin.html", {
        "application_counts": application_counts,
        "recent_applications": recent_applications,
        "user_counts": user_counts,
        "oldest_pending": oldest_pending,
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

    return render(request, "dashboards/admin/applications.html", {
        "all_applications": all_applications,
        "counts": counts,
        "active_tab": active_tab,
    })


@login_required
@admin_required
def application_detail(request, pk):
    application = get_object_or_404(oversight.staff_queryset(), pk=pk)

    if request.method == "POST":
        ok, note = oversight.apply_transition(application, request.POST.get("action"))
        (messages.success if ok else messages.error)(request, note)
        return redirect("admin_dashboard:application_detail", pk=application.pk)

    application.tab = oversight.STATUS_TO_TAB.get(application.status, "all")

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
