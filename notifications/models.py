from django.conf import settings
from django.db import models


class Notification(models.Model):
    """A staff-facing notice, broadcast to everyone in one role rather than
    written to a named recipient -- same reasoning as messaging.access.is_staff_side:
    who's actually staffing a role changes over time, and a notification
    written for "the Secretariat" should reach whoever that is today, not
    just whoever held the role when it was created.
    """

    class Audience(models.TextChoices):
        SECRETARIAT = "secretariat", "Secretariat"

    class Icon(models.TextChoices):
        INFO = "info", "Info"
        SUCCESS = "success", "Success"
        WARN = "warn", "Warning"

    audience = models.CharField(max_length=20, choices=Audience.choices)
    icon = models.CharField(max_length=10, choices=Icon.choices, default=Icon.INFO)
    message = models.CharField(max_length=255)

    # Optional deep link -- a named URL to send the viewer to when they
    # click the notification (e.g. straight to the application that
    # triggered it). Blank means "informational only, nowhere to go."
    link_url_name = models.CharField(max_length=100, blank=True)
    link_kwargs = models.JSONField(blank=True, default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.audience}] {self.message}"

    def get_absolute_url(self):
        if not self.link_url_name:
            return None
        from django.urls import reverse
        return reverse(self.link_url_name, kwargs=self.link_kwargs)


class NotificationRead(models.Model):
    """Per-user read marker -- one row per (notification, user), the same
    shape as messaging.models.ConversationRead and for the same reason:
    O(1) "is this read" per viewer without a fan-out row at creation time."""

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="read_marks")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_reads")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification_reads"
        constraints = [
            models.UniqueConstraint(fields=["notification", "user"], name="unique_notification_read_per_user")
        ]
