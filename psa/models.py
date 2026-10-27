"""Professional Service Agreements (PSA) between Metascholar Limited and its
clients.

The life of one agreement:

  DRAFT      Admin / Secretariat fills in the services, timeline and fees.
             Nothing has gone to the client yet.
  SENT       Signed for Metascholar Limited and emailed to the client, who
             gets a private link (``token``) to complete their details and
             sign. The company's terms can still be corrected and resent.
  CHANGES    The client flagged something that needs fixing instead of
             signing (a ChangeRequest). Signing is locked until staff fix it
             -- or reply that it stands -- and send it back, which returns
             it to SENT. This can go round as many times as needed.
  SIGNED     The client has accepted and signed. The agreement is locked:
             nothing on it can change after this.
  CANCELLED  Withdrawn before the client signed. The link stops working.

Both signatures are stored either as a drawn PNG (a data: URL, cropped by
pages.signature) or as a typed name rendered in a script face.

Money received against an agreement is kept separately, as Payment rows
(the ledger). What is still owing is the agreed fee less everything
recorded, so it follows from the ledger rather than being a figure anyone
types over. Each row is written once and never changed afterwards.
"""
import secrets
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
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
        CHANGES = "changes", "Changes requested"
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
    def amount_paid(self):
        """Everything recorded as received, refunds included (they are
        negative rows). The list annotates this as ``paid_total`` so a page
        of agreements doesn't cost a query each."""
        total = getattr(self, "paid_total", None)
        if total is None:
            total = self.payments.aggregate(t=Sum("amount"))["t"]
        return total or Decimal("0.00")

    @property
    def amount_owing(self):
        """The agreed fee less what has come in. None while there is no
        fee to owe against; negative if the client has overpaid."""
        if self.fee is None:
            return None
        return self.fee - self.amount_paid

    @property
    def overpaid_by(self):
        owing = self.amount_owing
        return -owing if owing is not None and owing < 0 else None

    @property
    def payment_state(self):
        """How the money stands: used for the list's wording and colour.

        no_fee    no fee agreed yet, so nothing to owe
        unpaid    nothing received
        part      some received, more to come
        settled   paid in full
        over      more received than the fee
        """
        if self.fee is None:
            return "no_fee"
        paid, owing = self.amount_paid, self.amount_owing
        if owing < 0:
            return "over"
        if owing == 0:
            return "settled"
        return "part" if paid > 0 else "unpaid"

    PAYMENT_STATE_LABELS = {
        "no_fee": "No fee set", "unpaid": "Nothing paid", "part": "Part paid",
        "settled": "Paid in full", "over": "Overpaid",
    }

    @property
    def payment_state_label(self):
        return self.PAYMENT_STATE_LABELS[self.payment_state]

    @property
    def can_record_payment(self):
        """Anything with a fee can take a payment, whatever its status: a
        deposit can arrive before the paperwork goes out, and one taken
        before an agreement was withdrawn is still part of the record.
        Without a fee there is nothing to owe against."""
        return self.fee is not None

    @property
    def client_initials(self):
        """"Kwame Mensah" -> "KM"; one word -> its first letter."""
        words = [w for w in (self.client_name or "").split() if w[:1].isalnum()]
        return "".join(w[0] for w in (words[:1] + words[1:][-1:])).upper() or "?"

    # Inside this many days the deadline is worth flagging on the list.
    DEADLINE_SOON_DAYS = 7

    @property
    def days_to_deadline(self):
        """Whole days from today to the expected completion date, counting
        down: 0 on the day, negative once it has passed, None when no
        completion date has been set."""
        if not self.completion_date:
            return None
        return (self.completion_date - timezone.localdate()).days

    @property
    def deadline_state(self):
        """How the deadline stands, for the list's wording and colour.

        none      no completion date set
        closed    withdrawn, so nothing is due
        overdue   the date has passed
        today     due today
        soon      within DEADLINE_SOON_DAYS
        ok        further off
        """
        if self.status == self.Status.CANCELLED:
            return "closed"
        days = self.days_to_deadline
        if days is None:
            return "none"
        if days < 0:
            return "overdue"
        if days == 0:
            return "today"
        return "soon" if days <= self.DEADLINE_SOON_DAYS else "ok"

    @property
    def deadline_countdown(self):
        """"In 12 days", "Tomorrow", "Due today", "3 days overdue" -- how
        long there is left to deliver the work."""
        days = self.days_to_deadline
        if days is None or self.status == self.Status.CANCELLED:
            return ""
        if days < 0:
            late = -days
            return "1 day overdue" if late == 1 else f"{late} days overdue"
        if days == 0:
            return "Due today"
        if days == 1:
            return "Due tomorrow"
        if days < 14:
            return f"In {days} days"
        if days < 60:
            weeks = round(days / 7)
            return f"In {weeks} weeks"
        return f"In {round(days / 30)} months"

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
        return self.status in (self.Status.DRAFT, self.Status.SENT, self.Status.CHANGES)

    @property
    def open_change_request(self):
        """The client's request that hasn't been answered yet, if any."""
        return self.change_requests.filter(resolved_at__isnull=True).order_by("-created_at").first()

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


class ChangeRequest(models.Model):
    """The client flagging something on the agreement that needs fixing,
    instead of signing it -- and how Metascholar answered."""

    class Section(models.TextChoices):
        PARTIES = "parties", "1. The Parties"
        TERM = "term", "2. Term"
        SERVICE = "service", "3. The Service"
        PAYMENT = "payment", "4. Payment"
        OTHER = "other", "Something else"

    agreement = models.ForeignKey(ServiceAgreement, on_delete=models.CASCADE, related_name="change_requests")
    section = models.CharField(max_length=12, choices=Section.choices, default=Section.OTHER)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    client_ip = models.GenericIPAddressField(null=True, blank=True)

    # Filled in when staff send the agreement back to the client.
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    response = models.TextField(blank=True)

    class Meta:
        db_table = "service_agreement_change_requests"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.agreement.reference}: {self.get_section_display()}"



class Payment(models.Model):
    """One amount received against an agreement -- or given back, as a
    negative row.

    The ledger is write-once. A saved entry is the record of money that
    actually moved on a day, so nothing edits or removes it afterwards:
    ``save`` refuses a second write and ``delete`` refuses outright. A
    mistake is put right by recording a correction of its own, which
    leaves both the error and the fix visible. (Deleting the agreement
    still takes its ledger with it -- that cascade doesn't go through
    these methods.)
    """

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank transfer"
        MOMO = "momo", "Mobile money"
        CHEQUE = "cheque", "Cheque"
        CARD = "card", "Card"
        OTHER = "other", "Other"

    agreement = models.ForeignKey(ServiceAgreement, on_delete=models.CASCADE, related_name="payments")
    # Negative for a refund or for correcting an earlier entry.
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    paid_on = models.DateField(default=timezone.localdate)
    method = models.CharField(max_length=10, choices=Method.choices, default=Method.BANK)
    # Teller number, momo transaction id, cheque number -- or why a
    # correction was needed.
    note = models.CharField(max_length=200, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "service_agreement_payments"
        ordering = ["-paid_on", "-recorded_at"]
        indexes = [
            models.Index(fields=["agreement", "-paid_on"], name="service_agr_payments_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=~models.Q(amount=0), name="service_agreement_payments_amount_nonzero"),
        ]

    def __str__(self):
        return f"{self.agreement.reference}: {self.agreement.currency} {self.amount}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError(
                "A recorded payment can't be changed. Record a correcting entry instead."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(
            "A recorded payment can't be deleted. Record a correcting entry instead."
        )

    @property
    def is_refund(self):
        return self.amount < 0

    @property
    def abs_amount(self):
        return abs(self.amount)


class PsaSettings(models.Model):
    """Singleton (pk=1, via get_solo): the letterhead artwork printed on
    every page of an agreement PDF (psa/pdf.py).

    The images are cleaned up on upload by pages.letter_images (blank
    margins trimmed, at most 2480 px wide = 300 dpi across A4) and kept
    here in the database rather than Storage: they're small, they print
    the moment they're saved, and they work wherever the app does."""

    header_image = models.BinaryField(null=True, blank=True)
    header_type = models.CharField(max_length=20, blank=True)     # image/png | image/jpeg
    header_width = models.PositiveIntegerField(default=0)
    header_height = models.PositiveIntegerField(default=0)
    footer_image = models.BinaryField(null=True, blank=True)
    footer_type = models.CharField(max_length=20, blank=True)
    footer_width = models.PositiveIntegerField(default=0)
    footer_height = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        db_table = "service_agreement_settings"

    def __str__(self):
        return "PSA letterhead"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def image(self, kind):
        """Raw bytes of the header or footer artwork, or None."""
        data = getattr(self, f"{kind}_image")
        return bytes(data) if data else None
