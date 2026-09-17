from . import notification_feed


def notif_bell(request):
    """Feeds the topbar bell dropdown on every applicant-dashboard page
    (see templates/dashboards/applicant/_notif_bell.html). Every one of
    those templates used to hardcode the same three fake notifications --
    this replaces all of them with one real, shared feed. Scoped to
    role == applicant so it's a no-op (and does no extra queries) on every
    other dashboard, even though it's registered globally in settings.py.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.role != user.Role.APPLICANT:
        return {}

    return {
        "notif_bell_items": notification_feed.feed_for(user, limit=6),
        "notif_unread_count": notification_feed.unread_count(user),
    }
