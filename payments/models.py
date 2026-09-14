from decimal import Decimal

from django.conf import settings
from django.db import models


class FeeSetting(models.Model):
    """The live, admin-editable review-fee schedule -- one row per
    application-form `requestedReview` value. payments.fees reads this
    (never a hardcoded constant) so a price change from the admin Finance
    page takes effect immediately, both for what a new checkout actually
    charges and for what the application form displays while an applicant
    is filling it in. Seeded once via a data migration with the amounts
    already published on payments-fees.html; admin can change them freely
    from there on.
    """

    review_type = models.CharField(max_length=40, unique=True)
    label = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=8, default="GHS")

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="fee_settings_updated",
    )

    class Meta:
        db_table = "fee_settings"
        ordering = ["review_type"]

    def __str__(self):
        return f"{self.label}: {self.currency} {self.amount}"

    @property
    def requires_payment(self):
        return self.amount > 0


class Payment(models.Model):
    """One Paystack transaction attempt for an application's review fee.

    Created (status=PENDING) the moment an applicant is sent to checkout,
    *before* Paystack is ever contacted -- `reference` is generated here so
    there is always a row to reconcile a Paystack callback/verify against,
    even if the applicant abandons checkout or Paystack never calls back.
    Only server-side verification (payments.paystack.verify_transaction,
    called with the secret key) is allowed to flip a row to SUCCESS -- see
    payments/services.py. Never trust a client-supplied "it worked".
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    application = models.ForeignKey(
        "applicant_dashboard.Application", on_delete=models.CASCADE,
        related_name="payments", null=True, blank=True,
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payments"
    )

    purpose = models.CharField(max_length=150)
    review_type = models.CharField(max_length=40, blank=True)

    # Our own reference, generated before Paystack is ever contacted (see
    # payments.services.start_checkout) -- not Paystack's, so a Payment row
    # to reconcile against always exists even if Paystack is never reached.
    reference = models.CharField(max_length=100, unique=True)

    # Major currency unit (e.g. 300.00 GHS) -- converted to the lowest
    # subunit (pesewas) only at the Paystack API boundary (payments/paystack.py).
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=8, default="GHS")

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    # Full verify-transaction payload from Paystack, kept for audit/dispute
    # purposes -- e.g. channel, card bin, gateway response, fees charged.
    paystack_response = models.JSONField(blank=True, default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} — {self.currency} {self.amount} ({self.status})"

    @property
    def amount_subunit(self):
        """Amount in the lowest currency subunit (pesewas for GHS) --
        what Paystack's API actually speaks in."""
        return int(self.amount * 100)
