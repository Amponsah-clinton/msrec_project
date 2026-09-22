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
        MINOR_REVISIONS = "minor_revisions", "Approve Subject to Minor Revisions"
        MAJOR_REVISIONS = "major_revisions", "Major Revisions Required / Resubmission Required"
        REFER_COMMITTEE = "refer_committee", "Refer for Full Committee Review"
        NOT_APPROVED = "not_approved", "Not Approved"

    # The 10 rows of the Reviewer Assessment Form's "Ethical Review" table
    # (see templates/dashboards/reviewer/review-application.html) -- each
    # key is answered 'satisfactory' | 'needs_revision' | 'na' and stored
    # in `checklist` below, keyed by this list rather than one column per
    # row so the form's questions can be re-worded without a migration.
    CHECKLIST_ITEMS = [
        ("rationale", "Scientific/research rationale is clear"),
        ("risks", "Risks to participants are appropriately identified and minimized"),
        ("benefits", "Potential benefits justify the risks"),
        ("selection", "Participant selection is fair and appropriate"),
        ("consent", "Informed consent process is adequate"),
        ("privacy", "Privacy and confidentiality are adequately protected"),
        ("data_handling", "Data collection, storage, access, and disposal are appropriate"),
        ("vulnerable", "Protection of vulnerable participants is adequate"),
        ("recruitment", "Recruitment methods and materials are appropriate"),
        ("overall", "Overall ethical requirements are satisfactorily addressed"),
    ]
    CHECKLIST_CHOICES = {"satisfactory", "needs_revision", "na"}
    CHECKLIST_BADGE = {"satisfactory": "green", "needs_revision": "orange", "na": "gray"}
    CHECKLIST_LABEL = {"satisfactory": "Satisfactory", "needs_revision": "Needs Revision", "na": "N/A"}
    RECOMMENDATION_BADGE = {
        "approve": "green", "minor_revisions": "teal", "major_revisions": "orange",
        "refer_committee": "purple", "not_approved": "red",
    }

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
    # Set the first time reviewer_dashboard.reminders sends this reviewer a
    # "3 days left" nudge -- once and only once per assignment, so an
    # opportunistic check (see that module's docstring) that runs on every
    # dashboard visit can't re-send the same email all three days.
    deadline_reminder_sent_at = models.DateTimeField(null=True, blank=True)

    assigned_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    recommendation = models.CharField(max_length=30, choices=Recommendation.choices, blank=True)
    review_notes = models.TextField(blank=True)

    # Whether the reviewer has submitted their conflict-of-interest
    # declaration for this assignment. Drives the dashboard's "Pending COI
    # Declarations" stat -- set True the moment the Reviewer Assessment
    # Form (below) is submitted, since that form's Reviewer Declaration
    # section *is* the COI declaration.
    coi_declared = models.BooleanField(default=False)
    coi_has_conflict = models.BooleanField(default=False)
    coi_details = models.TextField(blank=True)
    confidentiality_confirmed = models.BooleanField(default=False)

    # {checklist_key: 'satisfactory' | 'needs_revision' | 'na', ...} for
    # every row in CHECKLIST_ITEMS -- see review_application() in views.py
    # for how a POST is validated and packed into this shape.
    checklist = models.JSONField(default=dict, blank=True)
    key_concerns = models.TextField(blank=True)
    documents_comment = models.TextField(blank=True)
    recommendation_reason = models.TextField(blank=True)

    # Set once the Secretariat/Admin clicks "Award Certificate" on a
    # completed assessment (see reviewer_dashboard.certificate and
    # secretariat_dashboard.views._handle_award_certificate). Null means
    # no certificate has been issued for this specific review yet -- a
    # reviewer's other completed assignments each get their own.
    certificate_id = models.CharField(max_length=40, blank=True)
    certificate_awarded_at = models.DateTimeField(null=True, blank=True)
    certificate_awarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="review_certificates_awarded",
    )

    class Meta:
        db_table = "review_assignments"
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.reviewer.email} · {self.application_id} · {self.status}"

    @property
    def checklist_rows(self):
        """CHECKLIST_ITEMS joined with this assignment's saved answers, for
        the Ethical Review table on both the form and its read-only
        submitted-assessment view."""
        return [
            {
                "key": key, "label": label, "value": value,
                "value_label": self.CHECKLIST_LABEL.get(value, "Not answered"),
                "badge": self.CHECKLIST_BADGE.get(value, "gray"),
            }
            for key, label in self.CHECKLIST_ITEMS
            for value in [self.checklist.get(key, "")]
        ]

    @property
    def recommendation_badge(self):
        return self.RECOMMENDATION_BADGE.get(self.recommendation, "gray")

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
