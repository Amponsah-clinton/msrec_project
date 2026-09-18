"""Committee member protocol-review data: each member's conflict-of-interest
declaration on a protocol, and the committee's pre-meeting deliberation
thread on it. Protocols themselves (applicant_dashboard.Application),
reviewer recommendations (reviewer_dashboard.ReviewAssignment) and meetings
(meetings.Meeting) already exist and are only read here.
"""
from django.conf import settings
from django.db import models


class ProtocolDeclaration(models.Model):
    """One member's declaration on one protocol: either "I have no conflict"
    or a described conflict, optionally with a request to recuse.

    A declared conflict is mirrored into pages.ConflictDeclaration (when the
    member has a governance seat) so it shows up on the admin/Secretariat
    Conflict Records page; `conflict_record` links the two, and a
    Secretariat ruling there (resolved / recused) flows back through
    `effective_status`.
    """

    class ConflictType(models.TextChoices):
        FINANCIAL = "financial", "Financial interest"
        PERSONAL = "personal", "Personal / family relationship"
        PROFESSIONAL = "professional", "Professional collaboration"
        INSTITUTIONAL = "institutional", "Same institution / department"
        SUPERVISORY = "supervisory", "Supervisory relationship"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        CLEAR = "clear", "No conflict"
        PENDING = "pending", "Awaiting Chair decision"
        RECUSED = "recused", "Recused"
        CLEARED = "cleared", "Cleared to participate"

    application = models.ForeignKey(
        "applicant_dashboard.Application", on_delete=models.CASCADE, related_name="member_declarations",
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="protocol_declarations")

    has_conflict = models.BooleanField(default=False)
    conflict_type = models.CharField(max_length=14, choices=ConflictType.choices, blank=True)
    description = models.TextField(blank=True)
    wants_recusal = models.BooleanField(default=False)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.CLEAR)

    conflict_record = models.ForeignKey(
        "pages.ConflictDeclaration", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="member_declarations",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "committee_protocol_declarations"
        unique_together = [("application", "user")]

    def __str__(self):
        return f"{self.user} — {self.application} — {self.get_status_display()}"

    @property
    def effective_status(self):
        if not self.has_conflict:
            return self.Status.CLEAR
        record = self.conflict_record
        if record is not None:
            if record.status == record.Status.RESOLVED:
                return self.Status.CLEARED
            if record.status == record.Status.RECUSED:
                return self.Status.RECUSED
        return self.status

    @property
    def can_participate(self):
        return self.effective_status in (self.Status.CLEAR, self.Status.CLEARED)

    @property
    def is_recused(self):
        return self.effective_status == self.Status.RECUSED


class DeliberationPost(models.Model):
    """One message in the committee's discussion of a protocol. Replies point
    at their top-level post via `parent` (one level of nesting)."""

    class Kind(models.TextChoices):
        COMMENT = "comment", "Comment"
        QUESTION = "question", "Question"
        CONCERN = "concern", "Concern"
        SUPPORT = "support", "Support"

    application = models.ForeignKey(
        "applicant_dashboard.Application", on_delete=models.CASCADE, related_name="deliberation_posts",
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="deliberation_posts")
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")

    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.COMMENT)
    body = models.TextField()
    is_deleted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "committee_deliberation_posts"
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.author} on {self.application}: {self.body[:40]}"
