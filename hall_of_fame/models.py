import secrets
from django.conf import settings
from django.db import models
from django.utils import timezone


def _generate_nomination_ref():
    year = timezone.now().year
    return f"MSREC/HOF/NOM/{year}/{secrets.token_hex(3).upper()}"


class HallOfFameNomination(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under Review"
        REVISION_REQUESTED = "revision_requested", "Revision Requested"
        RESUBMITTED = "resubmitted", "Resubmitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="hof_nominations",
    )
    reference_no = models.CharField(max_length=60, unique=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    full_name = models.CharField(max_length=200)
    professional_title = models.CharField(max_length=200, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    nationality = models.CharField(max_length=120, blank=True)
    current_location = models.CharField(max_length=200, blank=True)

    institution = models.CharField(max_length=200, blank=True)
    position = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=200, blank=True)
    years_experience = models.PositiveIntegerField(null=True, blank=True)
    areas_of_expertise = models.TextField(blank=True)

    biography = models.TextField(blank=True)
    achievements = models.TextField(blank=True)
    contribution = models.TextField(blank=True)
    reason_for_nomination = models.TextField(blank=True)

    cv_path = models.CharField(max_length=500, blank=True)
    activity_report_path = models.CharField(max_length=500, blank=True)
    supporting_evidence_path = models.CharField(max_length=500, blank=True)
    photo_path = models.CharField(max_length=500, blank=True)

    consent_accurate = models.BooleanField(default=False)
    consent_publish = models.BooleanField(default=False)
    consent_verify = models.BooleanField(default=False)

    hof_member_id = models.CharField(max_length=60, unique=True, null=True, blank=True)
    certificate_ref = models.CharField(max_length=60, unique=True, null=True, blank=True)
    letter_ref = models.CharField(max_length=60, unique=True, null=True, blank=True)
    recognition_year = models.PositiveIntegerField(null=True, blank=True)

    approved_biography = models.TextField(blank=True)

    revision_message = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="hof_reviews",
    )

    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "hof_nominations"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name} – {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.reference_no:
            self.reference_no = _generate_nomination_ref()
        super().save(*args, **kwargs)

    def generate_hof_ids(self):
        year = self.recognition_year or timezone.now().year
        seq = f"{self.pk:04d}"
        self.hof_member_id = f"MSREC-HOF-{year}-{seq}"
        self.certificate_ref = f"MSREC/HOF/CERT/{year}/{seq}"
        self.letter_ref = f"MSREC/HOF/LTR/{year}/{seq}"
        self.recognition_year = year


class HofAuditLog(models.Model):
    nomination = models.ForeignKey(
        HallOfFameNomination, on_delete=models.CASCADE, related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
    )
    action = models.CharField(max_length=60)
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "hof_audit_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} on {self.nomination_id} by {self.actor_id}"
