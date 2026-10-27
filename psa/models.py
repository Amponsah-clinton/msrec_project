"""Professional Service Agreements (PSA) between Metascholar Limited and its
clients.

The life of one agreement:

  DRAFT      Admin / Secretariat fills in the services, timeline and fees.
             Nothing has gone to the client yet.
  SENT       Signed for Metascholar Limited and emailed to the client, who
             gets a private link (``token``) to complete their details and
             sign. The company's terms can still be corrected and resent.
  SIGNED     The client has accepted and signed. The agreement is locked:
             nothing on it can change after this.
  CANCELLED  Withdrawn before the client signed. The link stops working.

Both signatures are stored either as a drawn PNG (a data: URL, cropped by
pages.signature) or as a typed name rendered in a script face.
"""
import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone

PROVIDER_NAME = "METASCHOLAR LIMITED"
PROVIDER_ADDRESS = "P.O. Box SY649 Fiapre–Sunyani, Bono Region Ghana."

CURRENCIES = [("GHS", "GHS — Ghana Cedi"), ("USD", "USD — US Dollar"),
              ("GBP", "GBP — British Pound"), ("EUR", "EUR — Euro")]


def _new_token():
    return secrets.token_urlsafe(32)


class ServiceAgreement(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Awaiting client"
        SIGNED = "signed", "Signed"
        CANCELLED = "cancelled", "Cancelled"

    class Basis(models.TextChoices):
        FIXED = "fixed", "Fixed project fee"
        HOURLY = "hourly", "Hourly"
        MILESTONE = "milestone", "Milestone-based"
        OTHER = "other", "Other"

    class SignatureKind(models.TextChoices):
        DRAWN = "drawn", "Drawn"
        TYPED = "typed", "Typed name"

    # Identity. `reference` is the human-facing number (PSA-2026-0001);
    # `token` is the unguessable key in the client's link.
    # NULL (not "") until numbered just after the insert, so two agreements
    # created at the same moment never clash on the unique constraint.
    reference = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    token = models.CharField(max_length=64, unique=True, default=_new_token, editable=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)

    # 1. The parties
    agreement_date = models.DateField(default=timezone.localdate)
    provider_name = models.CharField(max_length=120, default=PROVIDER_NAME)
    provider_address = models.CharField(max_length=255, default=PROVIDER_ADDRESS)
    client_name = models.CharField(max_length=200)
    client_email = models.EmailField(max_length=254, blank=True)
    client_phone = models.CharField(max_length=40, blank=True)
    client_address = models.CharField(max_length=255, blank=True)

    # 2. Term
    start_date = models.DateField(null=True, blank=True)
    completion_date = models.DateField(null=True, blank=True)

    # 3. The service
    service_title = models.CharField(max_length=255, blank=True)
    deliverables = models.JSONField(default=list, blank=True)

    # 4. Payment
    currency = models.CharField(max_length=3, default="GHS", choices=CURRENCIES)
    fee = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    payment_basis = models.CharField(max_length=12, choices=Basis.choices, blank=True)
    payment_basis_other = models.CharField(max_length=120, blank=True)
    deposit = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    payment_schedule = models.TextField(blank=True)

    # For Metascholar Limited
    company_signatory_name = models.CharField(max_length=200, blank=True)
    company_signatory_role = models.CharField(max_length=60, blank=True)
    company_signature_kind = models.CharField(max_length=6, choices=SignatureKind.choices, blank=True)
    company_signature = models.TextField(blank=True)
    company_signed_at = models.DateTimeField(null=True, blank=True)
    company_signed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    # 5. Client review and acceptance
    client_signature_kind = models.CharField(max_length=6, choices=SignatureKind.choices, blank=True)
    client_signature = models.TextField(blank=True)
    client_signed_at = models.DateTimeField(null=True, blank=True)
    client_signed_ip = models.GenericIPAddressField(null=True, blank=True)
    client_user_agent = models.CharField(max_length=300, blank=True)

    # Tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="service_agreements",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    send_count = models.PositiveIntegerField(default=0)
    viewed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "service_agreements"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference or 'PSA (unsaved)'} — {self.client_name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.reference:
            # Numbered from the primary key, so it is unique without a
            # counter table and never reused.
            year = timezone.localtime(self.created_at).year
            self.reference = f"PSA-{year}-{self.pk:04d}"
            type(self).objects.filter(pk=self.pk).update(reference=self.reference)

    # ---- derived ------------------------------------------------------

    @property
    def balance(self):
        if self.fee is None:
            return None
        return max(self.fee - (self.deposit or Decimal("0.00")), Decimal("0.00"))

    @property
    def term_days(self):
        if self.start_date and self.completion_date:
            return (self.completion_date - self.start_date).days
        return None

    @property
    def payment_basis_label(self):
        if self.payment_basis == self.Basis.OTHER and self.payment_basis_other:
            return f"Other — {self.payment_basis_other}"
        return self.get_payment_basis_display() if self.payment_basis else ""

    def basis_options(self):
        """Every payment basis, with the chosen one marked -- the document
        shows them all as tick boxes, like the paper form."""
        return [(v, label, v == self.payment_basis) for v, label in self.Basis.choices]

    @property
    def is_editable(self):
        return self.status in (self.Status.DRAFT, self.Status.SENT)

    @property
    def is_company_signed(self):
        return bool(self.company_signature and self.company_signed_at)

    @property
    def is_client_signed(self):
        return self.status == self.Status.SIGNED

    def client_url(self):
        return settings.SITE_URL.rstrip("/") + reverse("psa:client", kwargs={"token": self.token})

    def staff_url(self):
        return settings.SITE_URL.rstrip("/") + reverse("psa_admin:psa_detail", kwargs={"pk": self.pk})

    def deliverable_list(self):
        return [d for d in (self.deliverables or []) if str(d).strip()]
