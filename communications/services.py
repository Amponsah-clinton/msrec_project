"""Dispatch logic for Reminder -- turning a scheduled row into an actual
notification (and, optionally, emails) once its remind_at has arrived.
Kept separate from views.py so it can be called opportunistically from
more than one page without either importing the other's view functions.
"""
from django.utils import timezone

from accounts.models import User
from notifications import services as notification_services
from notifications.emails import send_branded_email
from notifications.models import Notification

from .models import AudienceChoices, Reminder

# A Reminder's audience is a superset of Notification's (it also allows
# "all"), so only the role-shaped values translate directly into a bell
# notification -- "all" still emails everyone (see _recipients) but has
# nowhere to go as a single-audience Notification row.
_NOTIFIABLE_AUDIENCES = {
    AudienceChoices.APPLICANT: Notification.Audience.APPLICANT,
    AudienceChoices.REVIEWER: Notification.Audience.REVIEWER,
    AudienceChoices.COMMITTEE: Notification.Audience.COMMITTEE,
    AudienceChoices.CHAIR: Notification.Audience.CHAIR,
    AudienceChoices.SECRETARIAT: Notification.Audience.SECRETARIAT,
    AudienceChoices.ADMIN: Notification.Audience.ADMIN,
}


def _recipients(reminder):
    if reminder.application_id and reminder.application.applicant_id:
        return [reminder.application.applicant]
    if reminder.audience == AudienceChoices.ALL:
        return list(User.objects.filter(is_active=True))
    return list(User.objects.filter(role=reminder.audience, is_active=True))


def dispatch_reminder(reminder):
    """Fires one reminder right now, regardless of remind_at -- used both
    by the due-reminders sweep and by the Secretariat's manual "Send Now"
    button."""
    recipients = _recipients(reminder)

    notify_audience = _NOTIFIABLE_AUDIENCES.get(reminder.audience)
    if notify_audience and not reminder.application_id:
        link_kwargs = {}
        notification_services.notify(
            notify_audience, reminder.title,
            icon=Notification.Icon.WARN,
            link_url_name="", link_kwargs=link_kwargs,
        )

    if reminder.send_email:
        for user in recipients:
            if not user.email:
                continue
            send_branded_email(
                subject=reminder.title,
                to=user.email,
                heading=reminder.title,
                paragraphs=[f"Hi {user.first_name},", reminder.message],
                preheader=reminder.title,
            )

    reminder.status = Reminder.Status.SENT
    reminder.sent_at = timezone.now()
    reminder.save(update_fields=["status", "sent_at"])
    return reminder


def dispatch_due_reminders():
    """Fires every scheduled reminder whose time has come. Safe to call
    on every page load that touches Reminders -- a Reminder can only be
    dispatched once (status flips away from SCHEDULED immediately)."""
    now = timezone.now()
    due = Reminder.objects.filter(status=Reminder.Status.SCHEDULED, remind_at__lte=now)
    for reminder in due:
        dispatch_reminder(reminder)
