from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from messaging.access import is_staff_side

from . import services
from .models import Notification

# Which audiences a given user is allowed to read/clear -- a notification
# for role X is only ever meant for whoever currently holds role X (see
# Notification's own docstring), so this just re-checks request.user.role
# rather than any fixed recipient list. Staff (Admin/Secretariat) can also
# open anything, the same "staff sees every inbox" rule messaging.access
# already applies to the applicant support inbox.
def _authorized(user, audience):
    if not user.is_authenticated:
        return False
    if is_staff_side(user):
        return True
    return user.role == audience


@login_required
@require_POST
def mark_all_read(request, audience):
    if not _authorized(request.user, audience):
        return HttpResponseForbidden()
    services.mark_all_read(request.user, audience)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect(request.POST.get("next") or "/")


@login_required
def open_notification(request, audience, pk):
    """Click-through from a notification: mark it read, then send the
    viewer wherever it points (or back to the referring page)."""
    if not _authorized(request.user, audience):
        return HttpResponseForbidden()
    services.mark_read(request.user, pk)
    notification = Notification.objects.filter(pk=pk, audience=audience).first()
    target = notification.get_absolute_url() if notification else None
    return redirect(target or request.META.get("HTTP_REFERER") or "/")


# Where "Back to dashboard" on the generic list page (below) should point,
# and which dashboard's polling script re-fetches this audience's feed --
# one entry per Audience that actually has a live topbar bell today.
_DASHBOARD_HOME_URL_NAME = {
    Notification.Audience.REVIEWER: "reviewer_dashboard:home",
    Notification.Audience.CHAIR: "chair_dashboard:home",
    Notification.Audience.COMMITTEE: "committee_dashboard:home",
    Notification.Audience.SECRETARIAT: "secretariat_dashboard:home",
}


def _serialize(request, notification):
    return {
        "id": notification.pk,
        "icon": notification.icon,
        "message": notification.message,
        "url": reverse("notifications:open", args=[notification.audience, notification.pk]),
        "created_at": notification.created_at.isoformat(),
        "is_read": notification.is_read,
    }


@login_required
def feed(request, audience):
    """Polled by static/dashboard/js/notif-bell.js so a role's topbar bell
    reflects new Notification rows within one poll interval instead of
    only on the next full page load."""
    if not _authorized(request.user, audience):
        return HttpResponseForbidden()
    items = services.for_user(request.user, audience, limit=8)
    return JsonResponse({
        "count": services.unread_count(request.user, audience),
        "items": [_serialize(request, n) for n in items],
    })


@login_required
def list_page(request, audience):
    """A minimal "view all" page for roles that don't already have one of
    their own (Secretariat has a fuller composer/list at
    secretariat_dashboard:notifications_page; Applicant has its own
    derived-feed page) -- just the full history for this audience, newest
    first, inside the same dashboard chrome."""
    if not _authorized(request.user, audience):
        return HttpResponseForbidden()
    home_url_name = _DASHBOARD_HOME_URL_NAME.get(audience, "pages:index")
    return render(request, "notifications/list.html", {
        "audience": audience,
        "notifications": services.for_user(request.user, audience, limit=100),
        "home_url": reverse(home_url_name),
    })
