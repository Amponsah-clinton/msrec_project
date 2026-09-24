"""Maintenance mode: lock the site while an administrator works on it.

The switch, the schedule and the message live on the SiteSettings row
(Site Settings > Maintenance), so they're stored in the same Supabase
database as everything else and survive restarts and multiple servers.

State model -- `enabled` is the master switch; `start` / `end` are an
optional window inside it:

    enabled = False                          -> site is live
    enabled, start in the future             -> "scheduled": still live
    enabled, start passed (or no start), and
        end not reached (or no end)          -> LOCKED
    enabled, end has passed                  -> site is live again by itself

so a maintenance window that has an end time reopens the site
automatically; nobody has to remember to switch it off.

Who is let through (see MaintenanceMiddleware): ONLY the /admins/ area,
the login / password-reset pages and static files -- for everyone, admins
included, so an administrator signs in and lands in /admins/ to switch
maintenance off. Every other page and dashboard is locked. Two narrow
exceptions keep the admin area itself working: the file proxy and the
notification feed (for signed-in administrators only), and the
payment-confirmation callback of an applicant who has already paid.
"""
import re
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

# The illustration on the maintenance page. Cloudinary serves the best
# format the browser supports (AVIF/WebP/JPEG) at the size asked for.
IMAGE_BASE = "https://res.cloudinary.com/dmqizfpyz/image/upload"
IMAGE_TAIL = "v1790268452/12_jebeyy.avif"

DEFAULT_MESSAGE = (
    "The MSREC portal is offline for scheduled maintenance. Your applications, documents and "
    "account details are safe and nothing is lost. Please check back shortly."
)

CACHE_KEY = "pages:maintenance:v1"
CACHE_SECONDS = 5

# Exact-prefix allow-list for anyone who isn't an administrator.
EXEMPT_PREFIXES = (
    "/admins/",            # the admin area (its own views still require an admin login)
    "/login/", "/logout/", "/forgot-password/", "/reset-password/",
    "/static/", "/favicon.ico",
)
# An applicant who has already paid is sent to this URL to confirm the
# payment; blocking it would take their money without finalising the
# application, so it stays open (it still needs their own login).
PAYMENT_CONFIRMATION = re.compile(r"^/dashboard/applicant/applications/new/pay/\d+/verify/$")


def image_url(width=1200):
    return f"{IMAGE_BASE}/f_auto,q_auto,w_{width}/{IMAGE_TAIL}"


# Endpoints the admin area's own pages call (images served through the
# file proxy, the notification bell). Open to signed-in administrators only.
ADMIN_SUPPORT_PREFIXES = ("/files/", "/notifications/")


def is_bypass_user(user):
    """A signed-in administrator."""
    return bool(user and user.is_authenticated and (user.is_superuser or getattr(user, "role", "") == "admin"))


def _raw():
    """The maintenance fields, cached for a few seconds so this doesn't add
    a database query to every request."""
    raw = cache.get(CACHE_KEY)
    if raw is None:
        from .models import SiteSettings

        site = SiteSettings.get_solo()
        raw = {
            "enabled": bool(site.maintenance_enabled),
            "start": site.maintenance_start,
            "end": site.maintenance_end,
            "message": (site.maintenance_message or "").strip() or DEFAULT_MESSAGE,
        }
        cache.set(CACHE_KEY, raw, CACHE_SECONDS)
    return raw


def clear_cache(**_kwargs):
    cache.delete(CACHE_KEY)


def state(now=None, raw=None):
    """dict(enabled, active, scheduled, ended, start, end, message,
    seconds_left, progress) evaluated at `now`."""
    now = now or timezone.now()
    raw = raw or _raw()
    start, end, enabled = raw["start"], raw["end"], raw["enabled"]
    started = start is None or now >= start
    finished = end is not None and now >= end
    active = enabled and started and not finished
    scheduled = enabled and not started and not finished
    ended = enabled and finished
    seconds_left = max(0, int((end - now).total_seconds())) if (end and not finished) else None
    progress = None
    if start and end and end > start:
        progress = min(1.0, max(0.0, (now - start).total_seconds() / (end - start).total_seconds()))
    return {
        "enabled": enabled, "active": active, "scheduled": scheduled, "ended": ended,
        "start": start, "end": end, "message": raw["message"],
        "seconds_left": seconds_left, "progress": progress,
    }


def is_admin_support_path(path):
    return path.startswith(ADMIN_SUPPORT_PREFIXES)


# The same routes without their trailing slash (Django normally redirects
# those first, but never let a missing slash be what locks someone out).
EXEMPT_EXACT = ("/admins", "/login", "/logout", "/forgot-password", "/reset-password")


def is_exempt_path(path):
    return path.startswith(EXEMPT_PREFIXES) or path in EXEMPT_EXACT


def retry_after_seconds(current):
    """Seconds to tell crawlers/clients to wait: until the window ends, else an hour."""
    return current["seconds_left"] if current["seconds_left"] else 3600


def default_window():
    """A sensible starting point for the admin form: from now, for two hours."""
    now = timezone.now().replace(second=0, microsecond=0)
    return now, now + timedelta(hours=2)
