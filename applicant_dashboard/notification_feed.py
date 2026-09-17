"""The applicant notification feed -- what drives the topbar bell dropdown
(_notif_bell.html) and the full Notifications page (notifications.html).

There's no per-notification table for this (unlike notifications.models.
Notification, which is a Secretariat-only broadcast -- see that module's
docstring). An applicant's notifications are inherently about *their own*
applications and payments, so they're derived straight from the real
timestamps already on Application/Payment rather than written out
separately at the moment each thing happens -- one less thing that could
drift out of sync with what actually occurred. "Unread" is whatever
happened after `request.user.notifications_last_read_at` (see
mark_all_read below); NULL means nothing has ever been marked read.
"""
from dataclasses import dataclass
from datetime import datetime

from django.urls import reverse
from django.utils import timezone

from applicant_dashboard.models import Application
from payments.models import Payment


@dataclass
class NotificationItem:
    icon: str          # info | success | warn | pay | cal
    category: str       # review | approval | payment | system
    title: str
    message: str
    at: datetime
    url: str = ""
    unread: bool = False

    @property
    def notice_class(self):
        """.notice-icon (topbar bell dropdown) only has info/warn/success/cal
        color variants -- map this item's icon onto the nearest one."""
        return "info" if self.icon == "pay" else self.icon


def _application_events(user):
    items = []
    for app in Application.objects.filter(applicant=user).exclude(status=Application.Status.DRAFT):
        url = reverse("applicant_dashboard:application_detail", args=[app.pk])
        ref = app.reference_no or f"#{app.pk}"

        if app.submitted_at:
            items.append(NotificationItem(
                icon="info", category="review", title="Application submitted",
                message=f"{ref} — {app.title} was submitted and is awaiting screening.",
                at=app.submitted_at, url=url,
            ))
        if app.revision_requested_at:
            items.append(NotificationItem(
                icon="warn", category="review", title="Revisions requested",
                message=f"MSREC requested changes on {ref} — {app.title}.",
                at=app.revision_requested_at, url=url,
            ))
        if app.resubmitted_at:
            items.append(NotificationItem(
                icon="info", category="review", title="Resubmission received",
                message=f"Your revised {ref} — {app.title} was resubmitted for review.",
                at=app.resubmitted_at, url=url,
            ))
        if app.decided_at and app.status == Application.Status.APPROVED:
            items.append(NotificationItem(
                icon="success", category="approval", title="Application approved",
                message=f"{ref} — {app.title} has been approved.",
                at=app.decided_at, url=url,
            ))
        elif app.decided_at and app.status == Application.Status.NOT_APPROVED:
            items.append(NotificationItem(
                icon="warn", category="approval", title="Application not approved",
                message=f"{ref} — {app.title} was not approved.",
                at=app.decided_at, url=url,
            ))
    return items


def _payment_events(user):
    items = []
    payments_url = reverse("applicant_dashboard:payments_history")
    for payment in Payment.objects.filter(applicant=user, status=Payment.Status.SUCCESS, paid_at__isnull=False):
        items.append(NotificationItem(
            icon="pay", category="payment", title="Payment received",
            message=f"We've received your payment of {payment.currency} {payment.amount} for {payment.purpose or 'your review fee'}.",
            at=payment.paid_at, url=payments_url,
        ))
    return items


def feed_for(user, *, limit=None):
    items = _application_events(user) + _payment_events(user)
    items.sort(key=lambda item: item.at, reverse=True)

    last_read = user.notifications_last_read_at
    for item in items:
        item.unread = last_read is None or item.at > last_read

    if limit:
        items = items[:limit]
    return items


def unread_count(user):
    return sum(1 for item in feed_for(user) if item.unread)


def mark_all_read(user):
    user.notifications_last_read_at = timezone.now()
    user.save(update_fields=["notifications_last_read_at"])
