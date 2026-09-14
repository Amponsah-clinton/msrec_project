"""The MSREC review-fee schedule.

Live and admin-editable (see admin_dashboard's Finance page) -- every
function here reads payments.models.FeeSetting fresh from the database, so
a price change takes effect immediately for both what a new checkout
actually charges (payments/services.py) and what the application form
shows an applicant while they're filling it in
(applicant_dashboard/views.py). Nothing here is a hardcoded constant
except the one-time defaults a migration seeds FeeSetting with -- see
payments/migrations/0003_seed_fee_settings.py.

Keyed by the application form's `requestedReview` radio value
(templates/dashboards/applicant/application-form.html).
"""
from decimal import Decimal

REVIEW_TYPE_LABELS = {
    "exemption": "Ethics Determination / Exemption Assessment",
    "expedited": "Expedited Review",
    "full": "Full Committee Review",
    "not-sure": "Not Sure — MSREC to Determine",
}

# Seed values only -- payments/migrations/0003_seed_fee_settings.py writes
# these into FeeSetting once; after that, the database (editable from the
# admin Finance page) is the only source of truth. Also used as the
# in-memory fallback if a review_type somehow has no FeeSetting row yet
# (e.g. mid-migration) so the payment gate never silently lets someone
# through for free.
DEFAULT_FEES = {
    "exemption": Decimal("0"),
    "expedited": Decimal("300"),
    "full": Decimal("500"),
    "not-sure": Decimal("300"),
}

CURRENCY = "GHS"


def _all_settings():
    from .models import FeeSetting
    return {row.review_type: row for row in FeeSetting.objects.all()}


def schedule():
    """Every review type's current FeeSetting, keyed by review_type --
    what both the admin Finance page's editor and the application form's
    live fee note render from."""
    existing = _all_settings()
    return {
        review_type: existing.get(review_type)
        for review_type in REVIEW_TYPE_LABELS
    }


def fee_for(review_type):
    row = _all_settings().get(review_type)
    if row is not None:
        return row.amount
    # Unknown/blank review_type, or a row genuinely missing -- fall back to
    # the "not-sure" tier's default rather than defaulting to free, so a
    # gap in configuration can never be exploited to skip payment.
    return DEFAULT_FEES.get(review_type, DEFAULT_FEES["not-sure"])


def label_for(review_type):
    return REVIEW_TYPE_LABELS.get(review_type, review_type or "Not specified")


def requires_payment(review_type):
    return fee_for(review_type) > 0
