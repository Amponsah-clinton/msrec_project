from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import User
from messaging.access import is_staff_side

from . import services
from .models import Notification

PAGE_SIZE = 25

# Which audiences a given user is allowed to read/clear -- a notification
# for role X is only ever meant for whoever currently holds role X (see
# Notification's own docstring). Staff (Admin/Secretariat) can also open
# anything, the same "staff sees every inbox" rule messaging.access already
# applies to the applicant support inbox.
#
# Reviewer/Committee are checked by their approval *_status, not `role` --
# same reasoning as reviewer_dashboard.views.is_reviewer and
# committee_dashboard.views.is_committee: `role` only ever reflects
# whichever dashboard is primary, and a Committee-primary account is still
# an approved Reviewer (accounts.models.User.approve_role), so a plain
# `role == audience` check here would 403 them out of their own Reviewer
# notifications bell.
def _authorized(user, audience):
    if not user.is_authenticated:
        return False
    if is_staff_side(user):
        return True
    if audience == Notification.Audience.REVIEWER:
        return user.reviewer_status == User.RequestStatus.APPROVED
    if audience == Notification.Audience.COMMITTEE:
        return user.committee_status == User.RequestStatus.APPROVED
    return user.role == audience


def _check(request, audience):
    """404 for an audience that doesn't exist, 403 for one this user can't
    read; otherwise None."""
    if audience not in Notification.Audience.values:
        raise Http404("Unknown notification audience.")
    if not _authorized(request.user, audience):
        return HttpResponseForbidden()
    return None


def _safe_next(request, fallback):
    target = request.POST.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return fallback


# Where "Back to dashboard" on the list page (below) should point, and which
# dashboard's polling script re-fetches this audience's feed -- one entry per
# Audience that actually has a live topbar bell today.
_DASHBOARD_HOME_URL_NAME = {
    Notification.Audience.REVIEWER: "reviewer_dashboard:home",
    Notification.Audience.CHAIR: "chair_dashboard:home",
    Notification.Audience.COMMITTEE: "committee_dashboard:home",
    Notification.Audience.SECRETARIAT: "secretariat_dashboard:home",
    Notification.Audience.ADMIN: "admin_dashboard:home",
}

# The Admin inbox also carries the Secretariat's notifications, whose links
# point into the Secretariat dashboard. Where the Admin dashboard has the
# same page, send the admin there so they stay in their own dashboard.
_ADMIN_EQUIVALENT_LINKS = {
    "secretariat_dashboard:application_detail": "admin_dashboard:application_detail",
    "secretariat_dashboard:users_access": "admin_dashboard:accounts",
}


def _target_url(notification, audience):
    """Where clicking a notification goes, or None when it has no link or
    the link no longer resolves (old notifications outlive the routes they
    point at)."""
    if audience == Notification.Audience.ADMIN and notification.link_url_name in _ADMIN_EQUIVALENT_LINKS:
        try:
            return reverse(_ADMIN_EQUIVALENT_LINKS[notification.link_url_name], kwargs=notification.link_kwargs)
        except NoReverseMatch:
            pass
    return notification.safe_url()


@login_required
@require_POST
def mark_all_read(request, audience):
    denied = _check(request, audience)
    if denied:
        return denied
    services.mark_all_read(request.user, audience)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect(_safe_next(request, "/"))


@login_required
def open_notification(request, audience, pk):
    """Click-through from a notification: mark it read, then send the
    viewer wherever it points (or back to their list when it has no target
    any more)."""
    denied = _check(request, audience)
    if denied:
        return denied
    notification = services.visible(request.user, audience).filter(pk=pk).first()
    list_url = reverse("notifications:list", args=[audience])
    if notification is None:
        messages.info(request, "That notification is no longer in your list.")
        return redirect(list_url)
    services.mark_read(request.user, notification.pk)
    target = _target_url(notification, audience)
    if target:
        return redirect(target)
    referer = request.META.get("HTTP_REFERER")
    if referer and url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(referer)
    return redirect(list_url)


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
    denied = _check(request, audience)
    if denied:
        return denied
    items = services.for_user(request.user, audience, limit=8)
    return JsonResponse({
        "count": services.unread_count(request.user, audience),
        "items": [_serialize(request, n) for n in items],
    })


def _day_label(day, today):
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return f"{day.day} {day:%B %Y}"


def _group_by_day(notifications, audience):
    """[(label, [notification, ...]), ...] for one page, newest day first.
    Each notification gets `.target_url` (None when it goes nowhere)."""
    today = timezone.localdate()
    groups = []
    for n in notifications:
        n.target_url = _target_url(n, audience)
        label = _day_label(timezone.localtime(n.created_at).date(), today)
        if not groups or groups[-1][0] != label:
            groups.append((label, []))
        groups[-1][1].append(n)
    return groups


_FILTERS = ("all", "unread", "read")


@login_required
def list_page(request, audience):
    """The full notification history for this audience: everything, old and
    new, until the user deletes it. Filterable (all / unread / read),
    searchable, paginated. The Administrator's page shows the Admin and
    Secretariat notifications together (see services.AUDIENCE_SCOPE)."""
    denied = _check(request, audience)
    if denied:
        return denied

    state = request.GET.get("filter", "all")
    if state not in _FILTERS:
        state = "all"
    query = (request.GET.get("q") or "").strip()[:100]

    qs = services.history(request.user, audience, state=state, query=query)
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    groups = _group_by_day(list(page.object_list), audience)

    params = {}
    if state != "all":
        params["filter"] = state
    if query:
        params["q"] = query
    query_string = "&".join(f"{k}={v}" for k, v in params.items())

    home_url_name = _DASHBOARD_HOME_URL_NAME.get(audience, "pages:index")
    scope = services.scope(audience)
    return render(request, "notifications/list.html", {
        "audience": audience,
        "audience_label": Notification.Audience(audience).label,
        "mixed_sources": len(scope) > 1,
        "groups": groups,
        "page": page,
        "counts": services.counts(request.user, audience),
        "state": state,
        "query": query,
        "query_string": query_string,
        "here": request.get_full_path(),
        "home_url": reverse(home_url_name),
    })


@login_required
@require_POST
def bulk(request, audience):
    """Every button on the list page: mark selected read/unread, delete
    selected, delete all read, delete all. Only ever changes the current
    user's own read/deleted state, never the shared notification."""
    denied = _check(request, audience)
    if denied:
        return denied

    action = request.POST.get("action", "")
    ids = request.POST.getlist("ids")
    user = request.user
    back = _safe_next(request, reverse("notifications:list", args=[audience]))

    def plural(n):
        return f"{n} notification{'s' if n != 1 else ''}"

    if action in ("mark_read", "mark_unread", "delete_selected") and not ids:
        messages.info(request, "Select at least one notification first.")
        return redirect(back)

    if action == "mark_read":
        n = services.mark_read_many(user, audience, ids)
        messages.success(request, f"{plural(n)} marked as read.")
    elif action == "mark_unread":
        n = services.mark_unread_many(user, audience, ids)
        messages.success(request, f"{plural(n)} marked as unread.")
    elif action == "delete_selected":
        n = services.dismiss_many(user, audience, ids)
        messages.success(request, f"{plural(n)} deleted.")
    elif action == "delete_read":
        n = services.dismiss_read(user, audience)
        messages.success(request, f"{plural(n)} deleted." if n else "There were no read notifications to delete.")
    elif action == "delete_all":
        n = services.dismiss_all(user, audience)
        messages.success(request, f"{plural(n)} deleted." if n else "There was nothing to delete.")
    else:
        messages.error(request, "That request could not be processed.")

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"ok": True})
    return redirect(back)
