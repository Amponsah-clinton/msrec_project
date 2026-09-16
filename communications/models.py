from django.conf import settings
from django.db import models


class AudienceChoices(models.TextChoices):
    """Who a broadcast (an Announcement or a Reminder) is written for.
    Deliberately the same values as accounts.models.User.Role and
    notifications.models.Notification.Audience -- 'reviewer' means the
    same thing everywhere in this project, so a Reminder can hand its
    audience straight to notifications.services.notify() or to a
    User.objects.filter(role=...) lookup without translating anything.
    ALL is the one value that doesn't map to a Role -- "everyone", not a
    role at all.
    """

    ALL = "all", "Everyone"
    APPLICANT = "applicant", "Applicants"
    REVIEWER = "reviewer", "Reviewers"
    COMMITTEE = "committee", "Committee Members"
    CHAIR = "chair", "Chair"
    SECRETARIAT = "secretariat", "Secretariat"
    ADMIN = "admin", "Administrators"


class EmailTemplate(models.Model):
    """A reusable, editable email -- so sending "the same decision letter
    nudge" or "the same welcome note" doesn't mean retyping it (or
    copy-pasting from an old email) every time. Rendered through the same
    branded shell as every other outbound email (notifications.emails),
    so a template preview looks exactly like what actually lands in an
    inbox.

    `body` uses simple {{ variable }} placeholders (see PLACEHOLDERS)
    rather than a templating engine -- the set of things worth
    substituting here (a name, a reference number, a study title) is
    small and fixed, and running arbitrary Django template syntax over
    secretariat-authored text is more power (and more risk) than this
    needs.
    """

    class Category(models.TextChoices):
        GENERAL = "general", "General"
        WELCOME = "welcome", "Welcome / Onboarding"
        DECISION = "decision", "Decision & Review Outcome"
        REMINDER = "reminder", "Reminder / Follow-up"
        PAYMENT = "payment", "Payment & Fees"

    # Placeholders a template author can drop into subject/body -- shown
    # as a cheat-sheet next to the editor and substituted verbatim (blank
    # if the caller doesn't supply a value) when a template is rendered.
    PLACEHOLDERS = [
        ("full_name", "Recipient's full name"),
        ("first_name", "Recipient's first name"),
        ("reference_no", "Application reference number"),
        ("study_title", "Study / application title"),
        ("status", "Current application status"),
        ("deadline", "Relevant deadline, if any"),
    ]

    name = models.CharField(max_length=150)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.GENERAL)
    subject = models.CharField(max_length=200)
    body = models.TextField(help_text="Plain text. Use {{ first_name }}, {{ reference_no }}, etc.")
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="email_templates"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "email_templates"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def render(self, **context):
        """Substitute {{ placeholder }} tokens in subject/body with values
        from `context` (missing ones fall back to an em dash, never a
        raw unfilled token in something a secretariat member is about to
        send). Returns (subject, body)."""
        subject, body = self.subject, self.body
        for key, _label in self.PLACEHOLDERS:
            value = context.get(key) or "—"
            token = "{{ %s }}" % key
            subject = subject.replace(token, value)
            body = body.replace(token, value)
        return subject, body


class Announcement(models.Model):
    """A broadcast notice pinned for a whole audience -- distinct from
    notifications.models.Notification (a small per-role bell item tied
    to one event) in that an Announcement is authored prose meant to sit
    visibly on a dashboard for a stretch of time (a policy change, a
    portal maintenance window, a call for reviewers), not a one-line
    "something happened" ping.
    """

    audience = models.CharField(max_length=20, choices=AudienceChoices.choices, default=AudienceChoices.ALL)
    title = models.CharField(max_length=200)
    body = models.TextField()
    is_pinned = models.BooleanField(
        default=False, help_text="Pinned announcements stay at the top regardless of date."
    )
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True, help_text="Leave blank to publish immediately.")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Leave blank to never expire.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="announcements"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "announcements"
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return self.title

    def is_live(self, *, now):
        if not self.is_active:
            return False
        if self.starts_at and self.starts_at > now:
            return False
        if self.expires_at and self.expires_at < now:
            return False
        return True


class Reminder(models.Model):
    """A message the Secretariat schedules now to go out later -- a
    payment nudge, a missing-document chase, a meeting prep note. Firing
    a Reminder means creating a Notification for its audience and, if
    `send_email` is set, emailing every user currently in that role
    (or, for a single-application reminder, that application's
    applicant) -- the same "who counts as this audience today" lookup
    notifications.services already uses, never a frozen recipient list.

    There's no task queue in this project, so nothing fires a Reminder
    on a timer by itself -- communications.services.dispatch_due_reminders()
    is called opportunistically wherever the Secretariat is likely to be
    looking (the Reminders page, the dashboard home) and sends anything
    whose remind_at has arrived. A few minutes' delay if nobody's looking
    is an acceptable trade for not needing Celery/cron in this stack.
    """

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        SENT = "sent", "Sent"
        CANCELLED = "cancelled", "Cancelled"

    title = models.CharField(max_length=200)
    message = models.TextField()
    audience = models.CharField(max_length=20, choices=AudienceChoices.choices, default=AudienceChoices.APPLICANT)

    # Optional: tie the reminder to one application, both for the deep
    # link on its Notification and so the applicant-facing copy can be
    # about a specific submission rather than a generic broadcast.
    application = models.ForeignKey(
        "applicant_dashboard.Application", on_delete=models.CASCADE,
        null=True, blank=True, related_name="reminders",
    )

    remind_at = models.DateTimeField()
    send_email = models.BooleanField(default=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="reminders_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "reminders"
        ordering = ["remind_at"]

    def __str__(self):
        return f"{self.title} @ {self.remind_at:%Y-%m-%d %H:%M}"

    def is_due(self, *, now):
        return self.status == self.Status.SCHEDULED and self.remind_at <= now
