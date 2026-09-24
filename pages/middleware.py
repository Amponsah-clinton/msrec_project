"""MaintenanceMiddleware: answers every request with the maintenance page
(HTTP 503 + Retry-After) while pages.maintenance says the site is locked,
except for the people and paths that must keep working -- see
pages/maintenance.py for the rules and the reasoning behind each.
"""
import logging

from django.http import JsonResponse
from django.shortcuts import render

from . import maintenance

logger = logging.getLogger(__name__)


def wants_json(request):
    accept = request.headers.get("Accept", "")
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in accept
        or request.path.startswith(("/assistant/", "/notifications/"))
    )


class MaintenanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        blocked = self._blocked_response(request)
        return blocked if blocked is not None else self.get_response(request)

    def _blocked_response(self, request):
        try:
            current = maintenance.state()
        except Exception:
            # A database hiccup must never take the whole site down with it.
            logger.exception("Couldn't read the maintenance state; letting the request through")
            return None
        if not current["active"]:
            return None
        if maintenance.is_exempt_path(request.path):
            return None
        user = getattr(request, "user", None)
        # Administrators get no free pass on the site itself -- only on the
        # few endpoints the admin area's own pages depend on.
        if maintenance.is_bypass_user(user) and maintenance.is_admin_support_path(request.path):
            return None
        if user is not None and user.is_authenticated and maintenance.PAYMENT_CONFIRMATION.match(request.path):
            return None

        retry = str(maintenance.retry_after_seconds(current))
        if wants_json(request):
            response = JsonResponse(
                {"error": "The site is under maintenance right now. Please try again shortly."}, status=503
            )
        else:
            response = render(request, "maintenance.html", maintenance_context(current), status=503)
        response["Retry-After"] = retry
        response["Cache-Control"] = "no-store"
        return response


def maintenance_context(current, *, preview=False):
    """Everything templates/maintenance.html shows."""
    from django.conf import settings
    from django.utils import timezone

    from .models import SiteSettings

    site = SiteSettings.get_solo()
    now = timezone.now()
    tz = timezone.get_current_timezone()
    return {
        "site": site,
        "state": current,
        "message": current["message"],
        "start_local": timezone.localtime(current["start"], tz) if current["start"] else None,
        "end_local": timezone.localtime(current["end"], tz) if current["end"] else None,
        "tz_name": settings.TIME_ZONE,
        # Ghana is on UTC all year, so the server's UTC clock reads as GMT.
        "tz_label": "GMT" if settings.TIME_ZONE == "UTC" else settings.TIME_ZONE,
        "now_ms": int(now.timestamp() * 1000),
        "end_ms": int(current["end"].timestamp() * 1000) if current["end"] else None,
        "start_ms": int(current["start"].timestamp() * 1000) if current["start"] else None,
        "image": maintenance.image_url(1200),
        "image_small": maintenance.image_url(700),
        "contact_email": site.contact_secretariat_email or site.footer_email,
        "preview": preview,
    }
