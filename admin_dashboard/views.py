from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render

from accounts import storage
from accounts.models import RoleApprovalLog, User

TABS = {"all", "pending", "applicants", "reviewers", "committee", "admins"}


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


@login_required
@admin_required
def accounts(request):
    if request.method == "POST":
        target = get_object_or_404(User, pk=request.POST.get("user_id"))
        role = request.POST.get("role")
        action = request.POST.get("action")

        if role not in (User.Role.REVIEWER, User.Role.COMMITTEE) or action not in ("approve", "reject"):
            messages.error(request, "That request could not be processed.")
            return redirect("admin_dashboard:accounts")

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
        return redirect(f"{request.path}?tab={request.POST.get('tab', 'pending')}")

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
