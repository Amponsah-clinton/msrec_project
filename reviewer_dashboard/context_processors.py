from notifications import services as notification_services
from notifications.models import Notification

from .views import is_reviewer


def notif_bell(request):
    """Feeds the topbar bell on every Reviewer page (see
    templates/dashboards/reviewer/_notif_bell.html), the same way
    applicant_dashboard.context_processors.notif_bell feeds the applicant
    one. Only reviewer.html's dashboard_home view used to pass
    `notifications`/`unread_count` itself, which is why every other
    Reviewer page either had no bell or a hardcoded fake one -- a global
    context processor means every page gets the real, live count for
    free, no per-view plumbing required.

    Scoped to is_reviewer (status-based, not `role` -- see that
    function's own comment) so it's a no-op, and does no extra query, on
    every other dashboard even though it's registered globally in
    settings.py.
    """
    user = getattr(request, "user", None)
    if not user or not is_reviewer(user):
        return {}

    return {
        "notifications": notification_services.for_user(user, Notification.Audience.REVIEWER, limit=6),
        "unread_count": notification_services.unread_count(user, Notification.Audience.REVIEWER),
    }
