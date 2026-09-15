from django.conf import settings
from django.db import models
from django.utils import timezone


class ReviewAssignment(models.Model):
    """One application handed to one reviewer for review.

    Nothing in this project creates these yet (the Secretariat's "Assign
    Reviewer" flow, and the "Assign to Committee" side, are still the
    unbuilt stub links in secretariat_dashboard's sidebar) -- this is the
    real, empty-until-populated data store the Reviewer dashboard's "My
    Reviews" page (New / Accepted / Due & Overdue / Completed) reads from
    and live-polls counts against, the same honest-empty-state approach
    as secretariat_dashboard's Reviewer Directory / Assignment History.
    """

    class Status(models.TextChoices):
        NEW = "new", "New"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        COMPLETED = "completed", "Completed"

    class Recommendation(models.TextChoices):
        APPROVE = "approve", "Approve"
        MINOR_REVISIONS = "minor_revisions", "Minor Revisions"
        MAJOR_REVISIONS = "major_revisions", "Major Revisions"
        REJECT = "reject", "Reject"

    application = models.ForeignKey(
        "applicant_dashboard.Application", on_delete=models.CASCADE, related_name="review_assignments"
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="review_assignments"
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="review_assignments_made",
    )

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    due_date = models.DateField(null=True, blank=True)

    assigned_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    recommendation = models.CharField(max_length=30, choices=Recommendation.choices, blank=True)
    review_notes = models.TextField(blank=True)

    # Whether the reviewer has submitted their conflict-of-interest
    # declaration for this assignment. Drives the dashboard's "Pending COI
    # Declarations" stat -- there's no separate COI model yet (the
    # Conflict of Interest nav links are still stubs), so this is the
    # simplest honest source of truth until that flow gets built out.
    coi_declared = models.BooleanField(default=False)

    class Meta:
        db_table = "review_assignments"
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.reviewer.email} · {self.application_id} · {self.status}"

    @property
    def tab(self):
        """Which of the Reviewer dashboard's four tabs this assignment
        belongs to -- same single-canonical-bucket idea as
        applicant_dashboard.oversight.STATUS_TO_TAB. An Accepted
        assignment moves itself into "due_overdue" once its due date
        arrives, without needing a separate status/cron job to flip it."""
        if self.status == self.Status.COMPLETED:
            return "completed"
        if self.status == self.Status.ACCEPTED:
            if self.due_date and self.due_date <= timezone.localdate():
                return "due_overdue"
            return "accepted"
        return "new"
