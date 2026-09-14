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

    wants_committee = models.BooleanField(default=False)
    committee_status = models.CharField(
        max_length=20, choices=RequestStatus.choices, default=RequestStatus.NOT_REQUESTED
    )
    committee_profile = models.JSONField(blank=True, default=dict)

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
