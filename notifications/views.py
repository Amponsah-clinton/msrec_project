from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import redirect
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
