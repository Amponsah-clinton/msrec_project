"""Read/write helpers for notifications.models. Kept separate from views.py
so other apps (applicant_dashboard, when an application is submitted) can
call `notify()` without importing view-layer code."""
from django.utils import timezone

from .models import Notification, NotificationRead


def notify(audience, message, *, icon=Notification.Icon.INFO, link_url_name="", link_kwargs=None):
    return Notification.objects.create(
        audience=audience,
        icon=icon,
        message=message,
        link_url_name=link_url_name,
        link_kwargs=link_kwargs or {},
    )


def for_user(user, audience, *, limit=20):
    """Notifications for `audience`, newest first, each annotated with
    `.is_read` for this specific user."""
    notifications = list(Notification.objects.filter(audience=audience)[:limit])
    if not notifications:
        return notifications
    read_ids = set(
        NotificationRead.objects.filter(
            user=user, notification_id__in=[n.pk for n in notifications]
        ).values_list("notification_id", flat=True)
    )
    for n in notifications:
        n.is_read = n.pk in read_ids
    return notifications


def unread_count(user, audience):
    read_ids = NotificationRead.objects.filter(user=user, notification__audience=audience).values_list(
        "notification_id", flat=True
    )
    return Notification.objects.filter(audience=audience).exclude(pk__in=read_ids).count()


def mark_all_read(user, audience):
    unread = Notification.objects.filter(audience=audience).exclude(
        pk__in=NotificationRead.objects.filter(user=user, notification__audience=audience).values_list(
            "notification_id", flat=True
        )
    )
    NotificationRead.objects.bulk_create(
        [NotificationRead(notification=n, user=user) for n in unread],
        ignore_conflicts=True,
    )


def mark_read(user, notification_id):
    NotificationRead.objects.get_or_create(user=user, notification_id=notification_id, defaults={"read_at": timezone.now()})
