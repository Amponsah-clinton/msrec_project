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

    # Archiving. Putting an agreement away is about the list, not about the
    # agreement: nothing it can do changes, its link keeps working and its
    # ledger is untouched. It simply stops crowding the page once it is
    # finished with. Reversible at any time, which is why this is a date
    # and not a status -- a status would have to be unpicked to restore,
    # and would be one more thing every filter had to know about.
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

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
    def ledger_total(self):
        """The payment entries only, refunds included (they are negative
        rows). The list annotates this as ``ledger_total`` so a page of
        agreements doesn't cost a query each."""
        total = getattr(self, "_ledger_total", None)
        if total is None:
            total = self.payments.aggregate(t=Sum("amount"))["t"]
        return total or Decimal("0.00")

    @property
    def amount_paid(self):
        """Everything in: the deposit entered on the agreement form plus
        every payment recorded since.

        The deposit is the amount taken upfront, so whoever typed it has
        already had the money -- leaving it out would show the whole fee
        as owing on an agreement that was half paid before it was even
        sent. Counting it also keeps this figure equal to the document's
        "Balance After Deposit" until a payment is recorded, instead of
        contradicting it."""
        return (self.deposit or Decimal("0.00")) + self.ledger_total

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
    def deposit_paid(self):
        """The deposit from the agreement form, if one was entered."""
        return self.deposit if self.deposit and self.deposit > 0 else None

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

    @property
    def open_payment_request(self):
        """The live payment link, if one is out with the client: pending,
        pending and still collecting. There is at most one, because
        asking for a new one cancels whatever was already out."""
        return next((r for r in self.payment_requests.all()
                     if r.status == PaymentRequest.Status.PENDING), None)

    @property
    def is_archived(self):
        return self.archived_at is not None

    @property
    def entry_count_value(self):
        """How many ledger entries this agreement has. The list annotates
        `entry_count`, so a page of rows doesn't cost a query each."""
        count = getattr(self, "entry_count", None)
        return count if count is not None else self.payments.count()

    @property
    def change_request_count_value(self):
        count = getattr(self, "change_request_count", None)
        return count if count is not None else self.change_requests.count()

    @property
    def delete_impact(self):
        """What a delete would take with it, said plainly, for the
        confirmation staff see before pressing it.

        Any agreement can be deleted -- that is a deliberate choice -- so
        the one safeguard left is knowing what is about to go. A signed
        agreement takes its signatures; one with entries takes the ledger,
        which is otherwise write-once precisely because it records money
        that actually moved."""
        parts = []
        if self.status == self.Status.SIGNED:
            parts.append("both signatures")
        count = self.entry_count_value
        if count:
            parts.append(f"{count} payment entr{'y' if count == 1 else 'ies'} "
                         f"({self.currency} {self.ledger_total:,.2f})")
        if self.change_request_count_value:
            parts.append("the change requests")
        return ", ".join(parts)

    @property
    def can_request_payment(self):
        """Whether it makes sense to ask the client for money online: there
        is a fee, something is still owing, and the agreement is live."""
        owing = self.amount_owing
        return (self.status != self.Status.CANCELLED
                and owing is not None and owing > 0
                and bool(self.client_email))


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
    # Numbered on the way in, for money coming in only: a refund is given
    # a credit note by recording it, not a receipt. Numbered from the
    # primary key for the same reason the agreement reference is -- unique
    # without a counter table, and never reused.
    receipt_number = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)

    class Meta:
        db_table = "service_agreement_payments"
        ordering = ["-paid_on", "-recorded_at"]
        indexes = [
            models.Index(fields=["agreement", "-paid_on"], name="service_agr_payments_idx"),
        ]
        # No CheckConstraint for "amount <> 0": its keyword is `check` up to
        # Django 5.0 and `condition` from 5.1, with no spelling that works on
        # both, and this project runs 4.2 in production. The rule is kept
        # where it is read anyway -- psa.forms.parse_payment refuses a zero
        # amount -- and psa/supabase.sql declares the CHECK on the Postgres
        # table itself.

    def __str__(self):
        return f"{self.agreement.reference}: {self.agreement.currency} {self.amount}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError(
                "A recorded payment can't be changed. Record a correcting entry instead."
            )
        super().save(*args, **kwargs)
        if self.amount > 0 and not self.receipt_number:
            year = timezone.localtime(self.recorded_at).year
            self.receipt_number = f"MSR-{year}-{self.pk:05d}"
            # Straight to the row: save() refuses a second write.
            type(self).objects.filter(pk=self.pk).update(receipt_number=self.receipt_number)

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

    @property
    def is_online(self):
        """Paid by the client through a payment link, rather than recorded
        by hand. Those rows carry their own PaymentRequest."""
        return hasattr(self, "request")


class PaymentRequest(models.Model):
    """A link sent to a client so they can settle what is still owing on
    an agreement, and the record of what came back.

    The link is the secret: `token` is 32 random bytes, the same strength
    as the agreement's own link, so the URL cannot be guessed or walked
    (unlike a primary key in the path). It carries no personal data of its
    own -- everything the payment page shows is read from this row on the
    server, and the amount Paystack is asked to charge is read from here
    too, never from the browser.

    One request, one charge. A request is PENDING until Paystack's own
    servers confirm a payment of exactly this amount and currency against
    exactly this reference, at which point it becomes PAID, a write-once
    Payment row joins the ledger (which is what makes the amount owing on
    the list go down), and the receipt is numbered. Staff can CANCEL a
    request that was sent in error, and a request stops working once it
    expires -- a live payment URL shouldn't outlive the reason it was
    sent.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payment"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    agreement = models.ForeignKey(
        ServiceAgreement, on_delete=models.CASCADE, related_name="payment_requests",
    )
    token = models.CharField(max_length=64, unique=True, default=_new_token, editable=False)
    # Our own Paystack reference, generated before Paystack is ever
    # contacted, so there is always a row to reconcile a payment against
    # even if the client abandons checkout. Same contract as
    # payments.Payment.reference and WorkshopRegistration.payment_reference.
    reference = models.CharField(max_length=100, unique=True, editable=False)

    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="GHS")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    # What this instalment is for, in the client's words on the page and
    # on the receipt ("Balance on delivery", "Second milestone").
    note = models.CharField(max_length=200, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    send_count = models.PositiveIntegerField(default=0)
    viewed_at = models.DateTimeField(null=True, blank=True)

    paid_at = models.DateTimeField(null=True, blank=True)
    # The full verify payload, kept for audit and disputes -- channel,
    # card bin, gateway response, Paystack's own fees.
    paystack_response = models.JSONField(blank=True, default=dict)
    # The ledger entry this charge created. One per request; the ledger is
    # write-once, so this is the only link back.
    payment = models.OneToOneField(
        Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="request",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )

    class Meta:
        db_table = "service_agreement_payment_requests"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["agreement", "-created_at"], name="service_agr_payreq_idx"),
        ]

    def __str__(self):
        return f"{self.agreement.reference}: {self.currency} {self.amount} ({self.status})"

    def save(self, *args, **kwargs):
        creating = self._state.adding
        super().save(*args, **kwargs)
        if creating and not self.reference:
            # From the primary key, so it is unique without a counter
            # table and never reused -- and recognisable in Paystack's
            # dashboard as a PSA charge.
            self.reference = f"MSREC-PSA-{self.pk}-{secrets.token_hex(6)}"
            type(self).objects.filter(pk=self.pk).update(reference=self.reference)

    # ---- derived ----------------------------------------------------

    @property
    def amount_subunit(self):
        """What Paystack's API speaks in: the lowest subunit (pesewas)."""
        return int(self.amount * 100)

    @property
    def is_paid(self):
        return self.status == self.Status.PAID

    @property
    def is_payable(self):
        """Whether the link should still take money.

        The link does not expire on a clock -- it stays good until the
        debt behind it is gone or staff withdraw it. What it does follow
        is the balance: a cancelled agreement stops collecting, so does
        one already settled, and so does one whose balance has fallen
        below what the link was minted for, since money recorded by hand
        after it went out would otherwise let it overcharge by the
        difference. Staff send a fresh link for the new figure rather
        than this one quietly charging the old one."""
        if self.status != self.Status.PENDING:
            return False
        if self.agreement.status == ServiceAgreement.Status.CANCELLED:
            return False
        owing = self.agreement.amount_owing
        return owing is not None and owing >= self.amount > 0

    @property
    def state_label(self):
        return self.get_status_display()

    def pay_url(self):
        return settings.SITE_URL.rstrip("/") + reverse("psa:pay", kwargs={"token": self.token})

    def receipt_url(self):
        return settings.SITE_URL.rstrip("/") + reverse("psa:receipt", kwargs={"token": self.token})


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
