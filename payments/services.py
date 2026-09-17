"""Business logic for payments -- kept out of views.py so both the
applicant-facing checkout flow and the staff-facing Finance pages
(secretariat_dashboard, admin_dashboard) call the same functions, the same
way applicant_dashboard/oversight.py is shared between those two dashboards
for applications.
"""
import csv
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db.models import Q, Sum
from django.http import HttpResponse
from django.utils import timezone

from . import fees, paystack
from .models import FeeSetting, Payment

# Display order for the Fee Schedule editor -- review pathway chips, then
# the application-category tiers (in the order they appear on the
# application form), then the post-approval items. Not alphabetical.
FEE_SCHEDULE_ORDER = [
    "exemption", "expedited", "full",
    "ug_diploma", "masters_mphil", "phd",
    "gh_independent", "gh_institutional", "gh_consultancy",
    "intl_student", "intl_funded", "clinical_trial",
    "minor_amendment", "major_amendment", "continuing_review",
    "closure", "corrected_resubmission",
]


def start_checkout(application, review_type, applicant_category=""):
    """Creates the Payment row a checkout page/Paystack transaction will be
    reconciled against. Always a fresh row (not reused across attempts) --
    an abandoned/failed attempt just stays PENDING/FAILED in the ledger
    rather than being silently overwritten.

    The amount charged comes from fee_for_application(), not review_type
    alone -- see its docstring for why (category, not just pathway,
    decides the price outside the Exemption pathway)."""
    label = fees.label_for("exemption") if review_type == "exemption" else fees.label_for(applicant_category or review_type)
    return Payment.objects.create(
        application=application,
        applicant=application.applicant,
        purpose=f"{label} fee",
        review_type=review_type,
        reference=f"MSREC-{uuid.uuid4().hex[:20]}",
        amount=fees.fee_for_application(review_type, applicant_category),
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


def parse_filter_date(value):
    """Parses a Finance page date-range input ("YYYY-MM-DD", what an
    <input type="date"> submits) into a date, or None for blank/invalid
    input -- invalid input is treated as "no filter" rather than an error,
    since this only ever narrows a report, it never blocks anything."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def filter_payments(qs, *, query="", date_from=None, date_to=None):
    """Applies the Finance page's optional search + timeframe filters on
    top of a payments queryset (usually all_payments()). `query` matches
    the reference, applicant name/email, application reference number or
    purpose, case-insensitively. `date_from`/`date_to` are inclusive dates
    filtering on created_at. Shared by the on-screen list, its summary
    counts and the CSV export, so all three always agree on which rows are
    "in view"."""
    query = (query or "").strip()
    if query:
        qs = qs.filter(
            Q(reference__icontains=query)
            | Q(purpose__icontains=query)
            | Q(applicant__first_name__icontains=query)
            | Q(applicant__last_name__icontains=query)
            | Q(applicant__email__icontains=query)
            | Q(application__reference_no__icontains=query)
        )
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    return qs


def export_payments_csv(qs):
    """Streams the given payments queryset out as a CSV download -- same
    rows the Finance page is currently showing (see filter_payments), so
    exporting always matches what's on screen."""
    response = HttpResponse(content_type="text/csv")
    filename = f"msrec-payments-{timezone.localdate().isoformat()}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        "Reference", "Applicant", "Email", "Application Ref", "Purpose",
        "Review Type", "Amount", "Currency", "Status", "Created At", "Paid At",
    ])
    for payment in qs.select_related("applicant", "application"):
        writer.writerow([
            payment.reference,
            payment.applicant.full_name,
            payment.applicant.email,
            payment.application.reference_no if payment.application else "",
            payment.purpose,
            payment.review_type,
            payment.amount,
            payment.currency,
            payment.get_status_display(),
            payment.created_at.strftime("%Y-%m-%d %H:%M"),
            payment.paid_at.strftime("%Y-%m-%d %H:%M") if payment.paid_at else "",
        ])
    return response


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
