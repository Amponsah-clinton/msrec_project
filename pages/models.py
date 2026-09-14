from django.conf import settings
from django.db import models


class Inquiry(models.Model):
    """One submission of the public Contact page
    (templates/pages/contact.html). Saved straight to Supabase Postgres via
    Django's ORM (no Storage involved -- there's nothing to upload here).
    admin_dashboard's Inquiries page is where the Secretariat reads and
    replies to these.
    """

    class Reason(models.TextChoices):
        SECRETARIAT = "secretariat", "Secretariat / General Enquiry"
        APPLICATION_SUPPORT = "application-support", "Application Support"
        COMPLAINTS = "complaints", "Complaints"
        ETHICS_CONCERNS = "ethics-concerns", "Ethics Concerns"
        TECHNICAL_SUPPORT = "technical-support", "Technical Support"

    class Status(models.TextChoices):
        NEW = "new", "New"
        RESOLVED = "resolved", "Resolved"

    name = models.CharField(max_length=150)
    email = models.EmailField()
    reason = models.CharField(max_length=30, choices=Reason.choices, default=Reason.SECRETARIAT)
    message = models.TextField()

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)

    # Set together when a Secretariat/admin user sends a reply from
    # dashboards/admin/inquiries.html (also emailed to `email` -- see
    # admin_dashboard.views.inquiries).
    reply_message = models.TextField(blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    replied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="inquiry_replies",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "inquiries"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}> - {self.get_reason_display()}"
