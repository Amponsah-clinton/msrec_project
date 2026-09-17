import secrets
from datetime import timedelta

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

    # An approved study's ethical clearance is treated as valid for this
    # long before it's due for a Continuing Review / needs renewing --
    # matches the "Valid until" window shown on approval letters and
    # certificates. Not something MSREC has published a different figure
    # for anywhere in this codebase, so 2 years is this feature's own
    # reasonable default, kept in one place so it's easy to change later.
    APPROVAL_VALIDITY_DAYS = 730

    @property
    def approval_expires_at(self):
        if self.status != self.Status.APPROVED or not self.decided_at:
            return None
        return self.decided_at + timedelta(days=self.APPROVAL_VALIDITY_DAYS)


class PostApprovalSubmission(models.Model):
    """One post-approval item an applicant files against an approved (or
    approval-track) study: an amendment, a continuing-review renewal, an
    annual/progress report, an adverse-event report, a protocol deviation,
    or a study-closure request. Six different real-world forms that all
    share the same shape -- who filed it, against which application, a
    free-form set of type-specific answers, and a status the Secretariat
    moves along -- so one table (keyed by `type`) backs all six
    Post-Approval pages, the same reasoning as Application.form_data
    collapsing ~90 form fields into one jsonb column instead of a table
    each.

    No dedicated Secretariat/Committee review screen exists yet for these
    (that's the natural next build) -- for now they're actioned from
    /admin/ (see applicant_dashboard/admin.py), same as any other admin-
    managed row. The Secretariat is still notified the moment one is filed
    (see applicant_dashboard.views.postapproval_new), so nothing here goes
    unseen in the meantime.
    """

    class Type(models.TextChoices):
        AMENDMENT = "amendment", "Amendment"
        CONTINUING_REVIEW = "continuing_review", "Continuing Review"
        PROGRESS_REPORT = "progress_report", "Progress Report"
        ADVERSE_EVENT = "adverse_event", "Adverse Event"
        DEVIATION = "deviation", "Deviation"
        CLOSURE = "closure", "Closure"

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under Review"
        ACTION_REQUIRED = "action_required", "Action Required"
        APPROVED = "approved", "Approved"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"

    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name="postapproval_submissions"
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="postapproval_submissions"
    )

    type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)

    # Type-specific answers, keyed exactly like POSTAPPROVAL_FIELDS[type]
    # below -- e.g. an adverse_event row has event_type/date_onset/
    # severity/relatedness/outcome/description; a deviation row has
    # deviation_type/date_occurred/description/corrective_action.
    form_data = models.JSONField(blank=True, default=dict)

    secretariat_note = models.TextField(blank=True)

    submitted_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "postapproval_submissions"
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.get_type_display()} — {self.application.reference_no or self.application_id}"

    @property
    def is_serious(self):
        """Adverse events only: whether this was filed as serious/unexpected
        (the severity answer starts with "Serious" -- see POSTAPPROVAL_FIELDS).
        Drives the red vs neutral card treatment on the Adverse Events page,
        since a template can't do a substring test on its own."""
        return (self.form_data or {}).get("severity", "").startswith("Serious")


# Drives both the generic Post-Approval submission form (one template,
# templates/dashboards/applicant/postapproval-new.html) and, where useful,
# how a type's own list page reads its form_data back out. Order here is
# the order fields render in.
#
# Every entry is a 4-tuple (key, label, widget, choices) -- uniform arity
# even where `choices` is empty, because the template unpacks all four in
# one `{% for %}` and Django raises rather than padding a short row.
POSTAPPROVAL_FIELDS = {
    PostApprovalSubmission.Type.AMENDMENT: [
        ("amendment_type", "Amendment Type", "select", [
            "Protocol / Methodology", "Personnel Change", "Consent Form Update", "Other",
        ]),
        ("description", "Description of Change", "textarea", []),
        ("rationale", "Rationale", "textarea", []),
    ],
    PostApprovalSubmission.Type.CONTINUING_REVIEW: [
        ("summary", "Current Study Status", "textarea", []),
        ("continued_justification", "Justification for Continuation", "textarea", []),
    ],
    PostApprovalSubmission.Type.PROGRESS_REPORT: [
        ("period", "Reporting Period", "text", []),
        ("recruitment_status", "Recruitment Status", "textarea", []),
        ("summary", "Progress Summary", "textarea", []),
        ("changes", "Any Changes Since Last Report", "textarea", []),
    ],
    PostApprovalSubmission.Type.ADVERSE_EVENT: [
        ("event_type", "Event Type", "text", []),
        ("date_onset", "Date of Onset", "date", []),
        ("severity", "Severity", "select", ["Minor & Expected", "Serious & Unexpected"]),
        ("relatedness", "Relatedness", "select", [
            "Unrelated", "Possibly Related", "Probably Related", "Definitely Related", "Anticipated Reaction",
        ]),
        ("outcome", "Outcome", "text", []),
        ("description", "Full Report", "textarea", []),
    ],
    PostApprovalSubmission.Type.DEVIATION: [
        ("deviation_type", "Deviation Type", "select", [
            "Consent Process", "Eligibility Criteria", "Visit Schedule", "Other",
        ]),
        ("date_occurred", "Date Occurred", "date", []),
        ("description", "What Happened", "textarea", []),
        ("corrective_action", "Corrective Action Taken", "textarea", []),
    ],
    PostApprovalSubmission.Type.CLOSURE: [
        ("completion_date", "Study Completion Date", "date", []),
        ("final_sample_size", "Final Sample Size", "text", []),
        ("outstanding_events", "Outstanding Adverse Events / Issues", "textarea", []),
        ("data_status", "Data Storage / Disposal Status", "textarea", []),
    ],
}

POSTAPPROVAL_TITLES = {
    PostApprovalSubmission.Type.AMENDMENT: "Amendment Request",
    PostApprovalSubmission.Type.CONTINUING_REVIEW: "Continuing Review",
    PostApprovalSubmission.Type.PROGRESS_REPORT: "Progress Report",
    PostApprovalSubmission.Type.ADVERSE_EVENT: "Adverse Event Report",
    PostApprovalSubmission.Type.CLOSURE: "Closure Request",
    PostApprovalSubmission.Type.DEVIATION: "Deviation Report",
}

# What the list page each type belongs to is actually called in the
# sidebar -- naively pluralising POSTAPPROVAL_TITLES gives "Back to
# Adverse Event Reports" for a page titled "Adverse Events".
POSTAPPROVAL_LIST_LABELS = {
    PostApprovalSubmission.Type.AMENDMENT: "Amendments",
    PostApprovalSubmission.Type.CONTINUING_REVIEW: "Continuing Reviews",
    PostApprovalSubmission.Type.PROGRESS_REPORT: "Progress Reports",
    PostApprovalSubmission.Type.ADVERSE_EVENT: "Adverse Events",
    PostApprovalSubmission.Type.DEVIATION: "Deviations",
    PostApprovalSubmission.Type.CLOSURE: "Study Closure",
}


class TeamMember(models.Model):
    """One person on an applicant's research team (Research Team page).

    Owned by the applicant who added/invited them (`applicant`) -- this is
    the applicant's own address book of collaborators, not tied to any one
    Application. Adding someone here always sends them an email invite
    (see applicant_dashboard.views._send_team_invite_email); `status` just
    tracks whether they've followed that link yet. There's no real login
    account behind a team member -- accepting an invite only flips
    status/accepted_at (see team_invite_accept()), it doesn't create a
    User, since a collaborator being *listed* on the team is independent
    of them ever having their own MSREC account.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Invite"
        ACTIVE = "active", "Active"

    class Role(models.TextChoices):
        CO_INVESTIGATOR = "co_investigator", "Co-Investigator"
        RESEARCH_ASSISTANT = "research_assistant", "Research Assistant"
        STATISTICIAN = "statistician", "Statistician"
        OTHER = "other", "Other"

    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="research_team_members"
    )

    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    role = models.CharField(max_length=30, choices=Role.choices, default=Role.CO_INVESTIGATOR)
    institution = models.CharField(max_length=200, blank=True)

    # Object path inside Supabase Storage's "team_member" bucket (see
    # applicant_dashboard/team_storage.py) -- blank means no photo yet,
    # the template falls back to an initials avatar.
    photo_path = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Same "one active token per row, reissued on resend" shape as
    # accounts.models.PasswordResetCode, but a clickable link rather than a
    # typed code -- the invitee is opening this on whatever device the
    # email landed on, not necessarily the one they'd sign in from. NULL
    # (not "") once accepted/cleared -- a unique constraint treats every ""
    # as equal, and Postgres allows any number of NULLs (same reasoning as
    # Application.reference_no above).
    invite_token = models.CharField(max_length=64, unique=True, blank=True, null=True, default=None)
    invited_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "research_team_members"
        ordering = ["-created_at"]

    def __str__(self):
        return self.full_name

    @property
    def initials(self):
        parts = self.full_name.split()
        return ("".join(p[0] for p in parts[:2]) or "?").upper()

    def issue_invite_token(self):
        """(Re)issues this member's accept-invite link -- called once when
        first invited, and again on every "Resend" click, so a stale link
        from an earlier email can never be used after a resend."""
        self.invite_token = secrets.token_urlsafe(32)
        self.invited_at = timezone.now()
        self.save(update_fields=["invite_token", "invited_at"])
