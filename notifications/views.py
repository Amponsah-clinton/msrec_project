from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from messaging.access import is_staff_side

from . import services
from .models import Notification

# Which audiences a given user is allowed to read/clear. Only one exists
# today (Secretariat), gated the same way messaging's support inbox is --
# any admin/secretariat account, not a fixed list.
_AUDIENCE_CHECKS = {
    Notification.Audience.SECRETARIAT: is_staff_side,
}


def _authorized(user, audience):
    check = _AUDIENCE_CHECKS.get(audience)
    return bool(check and check(user))


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
