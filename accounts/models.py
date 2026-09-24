import secrets
from datetime import timedelta

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


def generate_membership_ethics_id(user):
    """MSREC/ETH/<user.pk, zero-padded>: the MSREC Ethics ID issued to every
    approved Reviewer and Committee member, shown on their dashboard and on
    their Membership Certificate. Keyed off the account's own
    primary key rather than a separate counter -- pk is already unique and
    already assigned by the time approve_role() calls this (the account
    exists; only its committee_status is changing), so there's no
    "reserve the next number" race to guard against with a lock/transaction.
    The tradeoff: gaps where a pk belongs to a non-member account are
    expected and fine -- this is an identifier, not a membership headcount."""
    return f"MSREC/ETH/{user.pk:05d}"


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

    # Notification Preferences (dashboards/applicant/notifications.html
    # side panel). Independent of notify_new_signin above (that one's
    # specifically the Profile & Security "new sign-in" alert).
    notify_email_alerts = models.BooleanField(default=True)
    notify_sms_alerts = models.BooleanField(default=False)
    notify_weekly_digest = models.BooleanField(default=True)

    # Read marker for the applicant notification feed (derived from this
    # user's own Application activity -- see applicant_dashboard.notifications).
    # Everything with an activity timestamp after this is "unread"; NULL
    # means nothing has ever been marked read.
    notifications_last_read_at = models.DateTimeField(null=True, blank=True)

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

    # Set once, the moment a Committee request is first approved (see
    # approve_role below) -- never reassigned afterwards, even if the seat
    # later lapses/is renewed, so a certificate issued today stays valid
    # proof of who held that ID. null (not "") so the "one row per unique
    # value" unique index doesn't choke on multiple unissued members --
    # see migration 0xxx_membership_certificate.
    membership_ethics_id = models.CharField(max_length=40, unique=True, null=True, blank=True)
    membership_confirmed_at = models.DateTimeField(null=True, blank=True)

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
        """Which dashboard namespace this account should land on after login.

        Committee/Reviewer are checked by *_status alone, not `role` --
        same reasoning as reviewer_dashboard.views.is_reviewer and
        committee_dashboard.views.is_committee: `role` only ever reflects
        whichever dashboard was primary the last time something promoted
        it (approve_role, or an admin editing the account directly), and
        can end up out of step with an approval status that's still
        APPROVED. An applicant-primary account whose Committee request
        was approved must still land on the Committee dashboard, not be
        sent back to Applicant because `role` never got promoted (or was
        later changed back).
        """
        if self.is_superuser or self.role == self.Role.ADMIN:
            return "admin_dashboard:home"
        if self.role == self.Role.SECRETARIAT:
            return "secretariat_dashboard:home"
        if self.role == self.Role.CHAIR:
            return "chair_dashboard:home"
        if self.committee_status == self.RequestStatus.APPROVED:
            return "committee_dashboard:home"
        if self.reviewer_status == self.RequestStatus.APPROVED:
            return "reviewer_dashboard:home"
        if self.awaiting_role_only:
            return "pages:role_status"
        return "applicant_dashboard:home"

    def approve_role(self, role, *, promote=True):
        """Approve a pending reviewer/committee request. Optionally makes
        it the account's primary (login-redirect) role.

        Approving either role is what makes someone an MSREC *member*: the
        first approval issues a permanent membership_ethics_id (see
        generate_membership_ethics_id) -- it never changes afterwards, even
        when a Reviewer later joins the Committee -- and stamps
        membership_confirmed_at. That date is re-stamped on a Committee
        approval, because the Membership Certificate is re-issued then with
        the higher role (accounts/membership.py).

        Approving a Committee request also unconditionally grants Reviewer
        access: every Committee member is a reviewer too (MSREC's Full
        Committee Review pathway is committee members reviewing protocols),
        so committee_status APPROVED always brings reviewer_status along
        with it, regardless of whether Reviewer was ever separately
        requested/rejected. `role` stays "committee" (their primary,
        post-login dashboard -- see dashboard_url_name) rather than being
        overwritten to "reviewer"; reviewer_dashboard.views.is_reviewer
        checks reviewer_status directly rather than `role`, precisely so a
        Committee-primary account still gets in."""
        update_fields = ["reviewer_status", "committee_status", "role", "wants_reviewer"]
        if role == self.Role.REVIEWER:
            self.reviewer_status = self.RequestStatus.APPROVED
        elif role == self.Role.COMMITTEE:
            self.committee_status = self.RequestStatus.APPROVED
            self.reviewer_status = self.RequestStatus.APPROVED
            self.wants_reviewer = True
        else:
            raise ValueError("Only reviewer/committee requests go through approval.")
        if not self.membership_ethics_id:
            self.membership_ethics_id = generate_membership_ethics_id(self)
            self.membership_confirmed_at = timezone.now()
            update_fields += ["membership_ethics_id", "membership_confirmed_at"]
        elif role == self.Role.COMMITTEE:
            self.membership_confirmed_at = timezone.now()
            update_fields.append("membership_confirmed_at")
        if promote:
            self.role = role
        self.save(update_fields=update_fields)

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


class AuditLog(models.Model):
    """General-purpose activity trail: who did what, to what, and when --
    across the whole platform, not just role decisions (RoleApprovalLog
    above stays as its own narrower table; this doesn't replace it, it
    covers everything else an ethics board needs to be able to answer
    "who changed this and when" about -- application status changes,
    account suspensions/deletions, reviewer assignments, logins).

    `target_type`/`target_id`/`target_label` are a loose pointer rather
    than a real FK -- the target's row can be deleted (a user account,
    an application) while the log entry itself must still read
    sensibly, so this deliberately never cascades.
    """

    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_logs"
    )
    # Dotted, namespaced action strings (e.g. "user.suspended",
    # "application.approved") rather than a TextChoices enum -- new
    # action types get added at call sites across several apps as the
    # platform grows, and a fixed choices list would need a migration
    # every time one does.
    action = models.CharField(max_length=64)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    target_label = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} · {self.target_label or self.target_type} · {self.created_at:%Y-%m-%d %H:%M}"

    @classmethod
    def record(cls, actor, action, *, target=None, description=""):
        """Logs one event. `target` is any model instance with a sensible
        __str__ (or None for account-less events like a failed login) --
        callers don't need to know this table's column names, just pass
        the object the action was performed on."""
        target_type = target.__class__.__name__ if target is not None else ""
        target_id = str(target.pk) if target is not None else ""
        target_label = str(target) if target is not None else ""
        return cls.objects.create(
            actor=actor if (actor is not None and getattr(actor, "is_authenticated", True)) else None,
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_label=target_label,
            description=description,
        )


class PasswordResetCode(models.Model):
    """A 6-digit code emailed to a user for the Forgot Password flow
    (accounts.views.forgot_password / reset_password). One row per code
    issued -- never reused, never edited in place -- so there's always an
    audit trail of every reset attempt against an account, the same
    "one row per attempt" idea as RoleApprovalLog above.

    Deliberately code-in-the-body rather than a tokenised reset link:
    matches how this project's other one-time-use flows (COI/2FA-style
    confirmations) already read as forms a person types into, not links
    they click, and it means the code can be read off an email on a
    second device (e.g. checking phone email while resetting on a
    laptop) without needing to copy a long URL.
    """

    TTL = timedelta(minutes=15)
    RESEND_COOLDOWN = timedelta(seconds=60)
    MAX_ATTEMPTS = 5

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_codes")
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "password_reset_codes"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} · {self.code} · {'used' if self.used_at else 'active'}"

    @property
    def is_valid(self):
        return self.used_at is None and timezone.now() < self.expires_at

    @classmethod
    def issue_for(cls, user):
        """Creates and returns a new code, without emailing it -- callers
        send the email themselves (see accounts.views._send_reset_code),
        keeping "generate a code" and "notify the user" separate concerns."""
        code = "".join(secrets.choice("0123456789") for _ in range(6))
        return cls.objects.create(user=user, code=code, expires_at=timezone.now() + cls.TTL)
