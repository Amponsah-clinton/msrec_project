from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """MSREC platform account.

    Everyone who signs up gets base applicant access immediately -- the
    MSREC signup form frames "Applicant" as a role you opt into, but in
    practice every account can open an application, so it never needs
    admin approval. Reviewer and Committee are the two roles that do:
    requesting either sets its *_status to PENDING, and only an admin
    flipping it to APPROVED unlocks that dashboard (see approve_role /
    reject_role below and admin_dashboard's Accounts page).
    """

    class Role(models.TextChoices):
        APPLICANT = "applicant", "Applicant"
        REVIEWER = "reviewer", "Reviewer"
        COMMITTEE = "committee", "Committee Member"
        CHAIR = "chair", "Chair"
        SECRETARIAT = "secretariat", "Secretariat"
        ADMIN = "admin", "Administrator"

    class RequestStatus(models.TextChoices):
        NOT_REQUESTED = "not_requested", "Not Requested"
        PENDING = "pending", "Pending Approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class Availability(models.TextChoices):
        AVAILABLE = "available", "Available"
        LIMITED = "limited", "Limited Availability"
        UNAVAILABLE = "unavailable", "Unavailable"

    email = models.EmailField(unique=True)

    first_name = models.CharField(max_length=150)
    middle_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150)
    title = models.CharField(max_length=20, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    country_residence = models.CharField(max_length=120, blank=True)
    highest_qualification = models.CharField(max_length=150, blank=True)

    institution = models.CharField(max_length=200, blank=True)
    department = models.CharField(max_length=200, blank=True)
    position = models.CharField(max_length=150, blank=True)
    institution_country = models.CharField(max_length=120, blank=True)
    institution_address = models.CharField(max_length=255, blank=True)
    profile_url = models.URLField(blank=True)
    no_institution = models.BooleanField(default=False)
    orcid = models.CharField(max_length=40, blank=True)

    # Institution / Affiliation page (dashboards/applicant/institution-
    # affiliation.html) -- everything above this point is captured at
    # signup; these are the extra fields that page lets an applicant fill
    # in/edit afterwards, once they know more detail than they did when
    # they first registered.
    faculty = models.CharField(max_length=200, blank=True)
    staff_student_id = models.CharField(max_length=100, blank=True)
    hod_name = models.CharField(max_length=200, blank=True)
    hod_email = models.EmailField(blank=True)
    irb_name = models.CharField(max_length=200, blank=True)
    irb_reference_no = models.CharField(max_length=100, blank=True)

    # Profile & Security page toggles (dashboards/applicant/profile-security.html).
    # These persist the switch state; there is no OTP/SMS provider wired up
    # yet, so they record the applicant's preference without (currently)
    # being enforced as an extra step at login.
    two_factor_app = models.BooleanField(default=False)
    two_factor_sms = models.BooleanField(default=False)
    notify_new_signin = models.BooleanField(default=True)

    # Object path inside the Supabase Storage "signup" bucket (see
    # accounts/storage.py) -- not a public URL, since that bucket is
    # private. Resolve to a viewable link with storage.create_signed_url().
    profile_photo_path = models.CharField(max_length=500, blank=True)

    # Primary role: which dashboard this account lands on after login.
    # Starts (and stays, unless an admin approves an elevated role) at
    # "applicant" -- see promote_after_approval().
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.APPLICANT)

    wants_reviewer = models.BooleanField(default=False)
    reviewer_status = models.CharField(
        max_length=20, choices=RequestStatus.choices, default=RequestStatus.NOT_REQUESTED
    )
    reviewer_profile = models.JSONField(blank=True, default=dict)
    # Two places can change this: the reviewer's own "Available for new
    # assignments" toggle on Profile & Expertise (reviewer_dashboard.views
    # -- only ever flips between AVAILABLE and UNAVAILABLE, the two
    # extremes a reviewer can self-report), and the Secretariat's Reviewer
    # Directory, which can additionally set LIMITED as an operational
    # override the Secretariat controls for finer capacity management.
    # Starts "available" since that's the accurate default for a
    # brand-new reviewer.
    reviewer_availability = models.CharField(
        max_length=20, choices=Availability.choices, default=Availability.AVAILABLE
    )

    wants_committee = models.BooleanField(default=False)
    committee_status = models.CharField(
        max_length=20, choices=RequestStatus.choices, default=RequestStatus.NOT_REQUESTED
    )
    committee_profile = models.JSONField(blank=True, default=dict)

    # Whether this account actually ticked "Applicant / Researcher" at
    # signup -- Applicant access was previously granted to EVERY account
    # regardless of what was selected, which is exactly what put a
    # Reviewer-only signup on the Applicant dashboard being told "you
    # have full Applicant access" while their Reviewer request was still
    # pending. Defaults True so every account created before this field
    # existed keeps behaving exactly as before (see migration); only
    # newly created accounts that skip the Applicant checkbox get False.
    # See dashboard_url_name() below for where this actually matters.
    wants_applicant = models.BooleanField(default=True)
    applicant_profile = models.JSONField(blank=True, default=dict)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "users"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        parts = [self.title, self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p).strip()

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.first_name

    @property
    def initials(self):
        chars = (self.first_name[:1] + self.last_name[:1]).upper()
        return chars or self.email[:2].upper()

    @property
    def reviewer_expertise_tags(self):
        raw = (self.reviewer_profile or {}).get("reviewerExpertise", "")
        return [tag.strip() for tag in raw.split(",") if tag.strip()]

    @property
    def reviewer_research_area_tags(self):
        raw = (self.reviewer_profile or {}).get("reviewerResearchAreas", "")
        return [tag.strip() for tag in raw.split(",") if tag.strip()]

    @property
    def requested_roles(self):
        roles = []
        if self.wants_reviewer:
            roles.append(self.Role.REVIEWER)
        if self.wants_committee:
            roles.append(self.Role.COMMITTEE)
        return roles

    @property
    def has_pending_requests(self):
        return self.reviewer_status == self.RequestStatus.PENDING or \
            self.committee_status == self.RequestStatus.PENDING

    @property
    def pending_role_labels(self):
        """Human labels for whichever role request(s) are still awaiting
        an admin's decision -- what the Applicant dashboard's pending-
        request banner shows, so landing there after requesting Reviewer/
        Committee never reads as the request having gone nowhere."""
        labels = []
        if self.reviewer_status == self.RequestStatus.PENDING:
            labels.append(self.Role.REVIEWER.label)
        if self.committee_status == self.RequestStatus.PENDING:
            labels.append(self.Role.COMMITTEE.label)
        return labels

    @property
    def rejected_role_labels(self):
        labels = []
        if self.reviewer_status == self.RequestStatus.REJECTED:
            labels.append(self.Role.REVIEWER.label)
        if self.committee_status == self.RequestStatus.REJECTED:
            labels.append(self.Role.COMMITTEE.label)
        return labels

    @property
    def awaiting_role_only(self):
        """True for an account that requested Reviewer and/or Committee
        but deliberately did NOT tick Applicant at signup, and hasn't
        been promoted to either yet -- see wants_applicant. This is the
        one case dashboard_url_name() must never fall through to the
        Applicant dashboard for: nothing about their signup asked for
        Applicant access, so they shouldn't be told they have it, or be
        handed applicant-only features (starting an application) they
        never opted into."""
        return self.role == self.Role.APPLICANT and not self.wants_applicant

    def dashboard_url_name(self):
        """Which dashboard namespace this account should land on after login."""
        if self.is_superuser or self.role == self.Role.ADMIN:
            return "admin_dashboard:home"
        if self.role == self.Role.SECRETARIAT:
            return "secretariat_dashboard:home"
        if self.role == self.Role.CHAIR:
            return "chair_dashboard:home"
        if self.role == self.Role.COMMITTEE and self.committee_status == self.RequestStatus.APPROVED:
            return "committee_dashboard:home"
        if self.role == self.Role.REVIEWER and self.reviewer_status == self.RequestStatus.APPROVED:
            return "reviewer_dashboard:home"
        if self.awaiting_role_only:
            return "pages:role_status"
        return "applicant_dashboard:home"

    def approve_role(self, role, *, promote=True):
        """Approve a pending reviewer/committee request. Optionally makes
        it the account's primary (login-redirect) role."""
        if role == self.Role.REVIEWER:
            self.reviewer_status = self.RequestStatus.APPROVED
        elif role == self.Role.COMMITTEE:
            self.committee_status = self.RequestStatus.APPROVED
        else:
            raise ValueError("Only reviewer/committee requests go through approval.")
        if promote:
            self.role = role
        self.save(update_fields=["reviewer_status", "committee_status", "role"])

    def reject_role(self, role):
        if role == self.Role.REVIEWER:
            self.reviewer_status = self.RequestStatus.REJECTED
        elif role == self.Role.COMMITTEE:
            self.committee_status = self.RequestStatus.REJECTED
        else:
            raise ValueError("Only reviewer/committee requests go through approval.")
        self.save(update_fields=["reviewer_status", "committee_status"])


class RoleApprovalLog(models.Model):
    """Audit trail for admin decisions on reviewer/committee role requests."""

    class Action(models.TextChoices):
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_logs")
    role = models.CharField(max_length=20, choices=User.Role.choices)
    action = models.CharField(max_length=20, choices=Action.choices)
    acted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="role_actions_taken"
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "role_approval_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} · {self.role} · {self.action}"
