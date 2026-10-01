import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


class InstitutionSecretary(models.Model):
    """The invite / activation record behind one Institutional Secretary.

    An administrator creates these from Admin Dashboard > Institutional
    Secretaries with just a name, email and institution. The underlying
    login account (a User with role=inst_secretary and the chosen
    institution) is created at the same moment, but with an *unusable*
    password, so it can't be signed into yet. A personalized activation
    link carrying `invite_token` is emailed to them; following it lets
    them set their own password (see institution_dashboard.views.activate),
    which is what actually turns the account on.

    The name/email/institution all live on the linked User -- this row is
    purely the activation tracker, mirroring the "one active token per row,
    reissued on resend" shape of accounts.models.PasswordResetCode and
    applicant_dashboard.models.TeamMember.invite_token.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="institution_secretary"
    )

    # NULL (not "") once activated/cleared -- a unique constraint treats
    # every "" as equal, and Postgres allows any number of NULLs (same
    # reasoning as applicant_dashboard.models.TeamMember.invite_token).
    invite_token = models.CharField(max_length=64, unique=True, blank=True, null=True, default=None)
    invited_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)

    # Who created the invite -- shown in the admin list; SET_NULL so
    # removing an admin account never cascades away the secretary.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="institution_secretaries_created",
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "institution_secretaries"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Institutional Secretary: {self.user_id}"

    @property
    def is_activated(self):
        return self.activated_at is not None

    def issue_invite_token(self):
        """(Re)issues the activation link -- called once when first invited,
        and again on every "Resend" click, so a stale link from an earlier
        email can never be used after a resend."""
        self.invite_token = secrets.token_urlsafe(32)
        self.invited_at = timezone.now()
        self.save(update_fields=["invite_token", "invited_at", "updated_at"])
