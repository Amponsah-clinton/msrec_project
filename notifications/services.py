"""Read/write helpers for notifications.models. Kept separate from views.py
so other apps (applicant_dashboard, when an application is submitted) can
call `notify()` without importing view-layer code.

Notifications are broadcast to a role (see Notification), so everything a
person does to them -- reading, deleting -- is recorded per user
(NotificationRead / NotificationDismissal) and never touches the shared row.
"""
from django.db.models import Exists, OuterRef
from django.utils import timezone

from .models import Notification, NotificationDismissal, NotificationRead

# The Administrator oversees the whole platform, so their inbox is their own
# audience *plus* everything the Secretariat is sent (new applications,
# reviewer assessments, resubmissions...). Every other role sees only its own.
AUDIENCE_SCOPE = {
    Notification.Audience.ADMIN: (Notification.Audience.ADMIN, Notification.Audience.SECRETARIAT),
}


def scope(audience):
    """The audiences whose notifications appear in `audience`'s inbox."""
    return tuple(AUDIENCE_SCOPE.get(audience, (audience,)))


def notify(audience, message, *, icon=Notification.Icon.INFO, link_url_name="", link_kwargs=None):
    return Notification.objects.create(
        audience=audience,
        icon=icon,
        message=message,
        link_url_name=link_url_name,
        link_kwargs=link_kwargs or {},
    )


def visible(user, audience):
    """Every notification in this inbox that `user` hasn't deleted, newest first."""
    return (
        Notification.objects.filter(audience__in=scope(audience))
        .exclude(dismissals__user=user)
        .order_by("-created_at", "-pk")
    )


def with_read_state(user, queryset):
    """Annotates each notification with `.is_read` for this user."""
    return queryset.annotate(
        is_read=Exists(NotificationRead.objects.filter(notification=OuterRef("pk"), user=user))
    )


def for_user(user, audience, *, limit=20):
    """The newest `limit` notifications in this inbox, newest first, each
    annotated with `.is_read` for this specific user."""
    return list(with_read_state(user, visible(user, audience))[:limit])


def history(user, audience, *, state="all", query=""):
    """The full inbox (no cap), optionally narrowed to unread/read and/or a
    text search. Returns a queryset annotated with `.is_read`."""
    qs = with_read_state(user, visible(user, audience))
    if state == "unread":
        qs = qs.filter(is_read=False)
    elif state == "read":
        qs = qs.filter(is_read=True)
    query = (query or "").strip()
    if query:
        qs = qs.filter(message__icontains=query)
    return qs


def counts(user, audience):
    """{'all', 'unread', 'read'} for this user's inbox."""
    total = visible(user, audience).count()
    unread = unread_count(user, audience)
    return {"all": total, "unread": unread, "read": total - unread}


def unread_count(user, audience):
    return (
        visible(user, audience)
        .exclude(pk__in=NotificationRead.objects.filter(user=user).values("notification_id"))
        .count()
    )


def _in_inbox(user, audience, ids):
    """Only ids that are actually in this user's inbox (ignores anything
    else, so a crafted request can't touch another audience's notifications)."""
    clean = [int(i) for i in ids if str(i).isdigit()]
    return list(visible(user, audience).filter(pk__in=clean).values_list("pk", flat=True))


def mark_all_read(user, audience):
    unread = visible(user, audience).exclude(
        pk__in=NotificationRead.objects.filter(user=user).values("notification_id")
    )
    NotificationRead.objects.bulk_create(
        [NotificationRead(notification=n, user=user) for n in unread],
        ignore_conflicts=True,
    )


def mark_read(user, notification_id):
    NotificationRead.objects.get_or_create(user=user, notification_id=notification_id, defaults={"read_at": timezone.now()})


def mark_read_many(user, audience, ids):
    pks = _in_inbox(user, audience, ids)
    NotificationRead.objects.bulk_create(
        [NotificationRead(notification_id=pk, user=user) for pk in pks], ignore_conflicts=True
    )
    return len(pks)


def mark_unread_many(user, audience, ids):
    pks = _in_inbox(user, audience, ids)
    NotificationRead.objects.filter(user=user, notification_id__in=pks).delete()
    return len(pks)


def dismiss_many(user, audience, ids):
    """Delete these notifications from `user`'s inbox (only theirs)."""
    pks = _in_inbox(user, audience, ids)
    NotificationDismissal.objects.bulk_create(
        [NotificationDismissal(notification_id=pk, user=user) for pk in pks], ignore_conflicts=True
    )
    return len(pks)


def dismiss_read(user, audience):
    """Delete every notification the user has already read."""
    pks = history(user, audience, state="read").values_list("pk", flat=True)
    return dismiss_many(user, audience, list(pks))


def dismiss_all(user, audience):
    return dismiss_many(user, audience, list(visible(user, audience).values_list("pk", flat=True)))
