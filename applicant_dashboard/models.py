from django.conf import settings
from django.db import models
from django.utils import timezone


class Application(models.Model):
    """One Universal Research Ethics Application submission.

    The form (templates/dashboards/applicant/application-form.html) has ~90
    fields across 15 sections that vary a lot by study type -- rather than
    modelling every one as a column, every field posts into `form_data`
    keyed by its `name` attribute (the research-team rows are collapsed into
    a `researchTeam` list of {name, role, institution} first). Only the
    handful of columns other views/queries actually need (status, reference
    number, review type, who/when) get their own column.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under Review"
        REVISIONS_REQUIRED = "revisions_required", "Revisions Required"
        APPROVED = "approved", "Approved"
        NOT_APPROVED = "not_approved", "Not Approved"

    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications"
    )

    # Assigned once, right after the first save (needs the auto PK) --
    # see Application.assign_reference_no(). Unset (NULL, not "") until
    # then -- a unique constraint treats every "" as equal, so as soon as a
    # second application (anyone's draft, or a fresh row pre-assignment)
    # existed with reference_no="" the next save would collide on it. NULL
    # is exempt from a unique constraint (Postgres allows any number of
    # NULLs), which is what "no reference assigned yet" actually means.
    reference_no = models.CharField(max_length=40, unique=True, blank=True, null=True, default=None)

    review_type = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    # Every named field from the form, as posted (see applicant_dashboard.views.application_form).
    form_data = models.JSONField(blank=True, default=dict)

    # Uploaded documents: [{"name", "path", "size", "content_type"}, ...].
    # `path` is the object path inside the "application" Supabase Storage
    # bucket (applicant_dashboard/storage.py) -- resolve to a URL with
    # storage.public_url() / storage.create_signed_url().
    documents = models.JSONField(blank=True, default=list)

    # Client-computed "answered fields / visible fields" heuristic from
    # apply.js's updateProgress(), sent along with every autosave and
    # persisted here so the Drafts list (and anything else) can show/sort
    # on completion without re-parsing form_data. Only meaningful while
    # status == DRAFT -- frozen (effectively 100) once submitted.
    completion_pct = models.PositiveSmallIntegerField(default=0)

    submitted_at = models.DateTimeField(null=True, blank=True)
    # Set once, when the Secretariat moves this application to approved or
    # not_approved (see secretariat_dashboard.views) -- lets Approved
    # Studies / Not Approved show a real decision date instead of reusing
    # updated_at (which also moves on every other status change).
    decided_at = models.DateTimeField(null=True, blank=True)

    # Revisions round-trip -- set by oversight.apply_transition() when the
    # Secretariat requests revisions, read by the applicant's Revisions
    # Required page/email, and by application_form when they fix and
    # resend. revision_count going from 0 -> 1+ is what "this application
    # has been through a revision cycle" means (see resubmitted_at below);
    # it stays incremented forever, even after status moves on to approved/
    # not_approved, so a later revision-history indicator has something to
    # show for a study that's since been decided.
    revision_comment = models.TextField(blank=True)
    revision_requested_at = models.DateTimeField(null=True, blank=True)
    revision_count = models.PositiveSmallIntegerField(default=0)
    # Set only when the applicant actually fixes and resends (not on the
    # original submission) -- the "revision was done on this application"
    # indicator the Secretariat sees is exactly `resubmitted_at is not None`.
    resubmitted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "applications"
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference_no or f"Application #{self.pk}"

    @property
    def title(self):
        return (self.form_data.get("studyTitle") or "").strip() or "Untitled application"

    def assign_reference_no(self):
        """MSREC/<year>/<zero-padded PK> -- called once, right after the
        row first gets a PK, so it never collides."""
        year = (self.submitted_at or self.created_at or timezone.now()).year
        self.reference_no = f"MSREC/{year}/{self.pk:04d}"
        self.save(update_fields=["reference_no"])
