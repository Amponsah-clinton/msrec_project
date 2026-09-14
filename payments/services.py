"""Business logic for payments -- kept out of views.py so both the
applicant-facing checkout flow and the staff-facing Finance pages
(secretariat_dashboard, admin_dashboard) call the same functions, the same
way applicant_dashboard/oversight.py is shared between those two dashboards
for applications.
"""
import uuid
from decimal import Decimal, InvalidOperation

from django.db.models import Sum
from django.utils import timezone

from . import fees, paystack
from .models import FeeSetting, Payment

# Display order for the Fee Schedule editor -- matches the order the
# review-type chips appear in on the application form, not alphabetical.
FEE_SCHEDULE_ORDER = ["exemption", "expedited", "full", "not-sure"]


def start_checkout(application, review_type):
    """Creates the Payment row a checkout page/Paystack transaction will be
    reconciled against. Always a fresh row (not reused across attempts) --
    an abandoned/failed attempt just stays PENDING/FAILED in the ledger
    rather than being silently overwritten."""
    return Payment.objects.create(
        application=application,
        applicant=application.applicant,
        purpose=f"{fees.label_for(review_type)} fee",
        review_type=review_type,
        reference=f"MSREC-{uuid.uuid4().hex[:20]}",
        amount=fees.fee_for(review_type),
        currency=fees.CURRENCY,
        status=Payment.Status.PENDING,
    )


def current_pending_payment(application):
    return (
        Payment.objects.filter(application=application, status=Payment.Status.PENDING)
        .order_by("-created_at")
        .first()
    )


def verify_and_finalize(payment, *, on_success):
    """Calls Paystack's verify API for `payment.reference` and only ever
    trusts *that* response -- never whatever the browser's Paystack popup
    callback claimed. Marks the Payment success/failed accordingly.

    On genuine success (Paystack says success, and the amount/currency it
    actually processed match what this Payment expected to charge),
    `on_success(payment.application)` is called exactly once and (True,
    None) is returned. Calling this again for an already-SUCCESS payment is
    a safe no-op (returns (True, None) without re-running on_success or
    re-verifying) -- covers a retried/duplicate verify request.

    On any mismatch or a Paystack-reported failure, the payment is marked
    FAILED and (False, reason) is returned.
    """
    if payment.status == Payment.Status.SUCCESS:
        return True, None

    try:
        data = paystack.verify_transaction(payment.reference)
    except paystack.PaystackError as exc:
        return False, str(exc)

    payment.paystack_response = data

    paystack_status = data.get("status")
    amount_ok = int(data.get("amount") or 0) == payment.amount_subunit
    currency_ok = (data.get("currency") or "").upper() == payment.currency.upper()

    if paystack_status == "success" and amount_ok and currency_ok:
        payment.status = Payment.Status.SUCCESS
        payment.paid_at = timezone.now()
        payment.save(update_fields=["status", "paid_at", "paystack_response"])
        if payment.application is not None:
            on_success(payment.application)
        return True, None

    payment.status = Payment.Status.FAILED
    payment.save(update_fields=["status", "paystack_response"])
    if paystack_status == "success" and (not amount_ok or not currency_ok):
        reason = "The amount received didn't match the expected fee. No charge was applied to your application — please contact the Secretariat."
    else:
        reason = data.get("gateway_response") or "Payment was not successful. Please try again."
    return False, reason


def all_payments():
    return Payment.objects.select_related("applicant", "application").order_by("-created_at")


def status_counts(qs=None):
    qs = all_payments() if qs is None else qs
    return {
        "all": qs.count(),
        "success": qs.filter(status=Payment.Status.SUCCESS).count(),
        "pending": qs.filter(status=Payment.Status.PENDING).count(),
        "failed": qs.filter(status=Payment.Status.FAILED).count(),
    }


def total_collected(qs=None):
    qs = all_payments() if qs is None else qs
    return qs.filter(status=Payment.Status.SUCCESS).aggregate(total=Sum("amount"))["total"] or 0


def fee_schedule_rows():
    """Every FeeSetting row, in application-form order -- what both the
    admin Finance page's editor and (read-only) the Secretariat's Finance
    page render."""
    by_type = {row.review_type: row for row in FeeSetting.objects.all()}
    return [by_type[review_type] for review_type in FEE_SCHEDULE_ORDER if review_type in by_type]


def update_fee(review_type, raw_amount, *, updated_by):
    """Applied the moment an admin saves the Fee Schedule editor -- the
    very next fees.fee_for()/requires_payment() call (a new checkout, or
    the application form re-rendering) reads it straight from the
    database, so a price change takes effect immediately, not after a
    deploy or a cache expiry. Returns (ok, message)."""
    try:
        row = FeeSetting.objects.get(review_type=review_type)
    except FeeSetting.DoesNotExist:
        return False, "Unknown review type."

    try:
        amount = Decimal(raw_amount)
    except (InvalidOperation, TypeError, ValueError):
        return False, "Enter a valid amount."
    if amount < 0:
        return False, "Amount can't be negative."

    row.amount = amount.quantize(Decimal("0.01"))
    row.updated_by = updated_by
    row.save(update_fields=["amount", "updated_by", "updated_at"])
    return True, f"{row.label} fee updated to {row.currency} {row.amount}."
