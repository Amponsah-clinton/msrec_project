"""The MSREC review-fee schedule.

Live and admin-editable (see admin_dashboard's Finance page) -- every
function here reads payments.models.FeeSetting fresh from the database, so
a price change takes effect immediately for both what a new checkout
actually charges (payments/services.py) and what the application form
shows an applicant while they're filling it in
(applicant_dashboard/views.py). Nothing here is a hardcoded constant
except the one-time defaults a migration seeds FeeSetting with -- see
payments/migrations/0003_seed_fee_settings.py and
payments/migrations/0004_seed_applicant_category_fees.py.

Three groups of keys share one FeeSetting table (it's really just a
generic "priced item" table, `review_type` is its historical column
name):

  REVIEW_TYPE_LABELS       -- the application form's `requestedReview`
                              radio value: how MSREC will review a study.
  APPLICANT_CATEGORY_LABELS -- the application form's `applicantCategory`
                              radio value: who/what kind of study is
                              applying. This is what actually prices a
                              new application -- see fee_for_application().
  POST_APPROVAL_LABELS     -- amendment/continuing-review/closure/etc.
                              prices. Published and admin-editable here,
                              but not charged anywhere yet: no payment
                              gate exists on PostApprovalSubmission (see
                              its docstring) -- listed honestly so the
                              schedule matches what's published without
                              overstating what's wired up.
"""
from decimal import Decimal

# "not-sure" was retired as a selectable pathway (removed from the
# application form and its FeeSetting row deleted -- see payments/
# migrations/0005_retire_not_sure_review_type.py) but is kept here so
# label_for()/fee_for() still resolve sensibly for any application/draft
# that already has review_type="not-sure" on file from before the change.
REVIEW_TYPE_LABELS = {
    "exemption": "Ethics Determination / Exemption Assessment",
    "expedited": "Expedited Review",
    "full": "Full Committee Review",
    "not-sure": "Not Sure — MSREC to Determine",
}

# Order matches the published Fee Schedule (and the application form's
# Application Category chips) -- student tiers, then Ghanaian, then
# international/clinical.
APPLICANT_CATEGORY_LABELS = {
    "ug_diploma": "Undergraduate / Diploma Student Research",
    "masters_mphil": "Master's / MPhil Student Research",
    "phd": "PhD / Doctoral Student Research",
    "gh_independent": "Ghanaian Independent / Self-Funded Researcher",
    "gh_institutional": "Ghanaian Institutional / Funded Research Project",
    "gh_consultancy": "Ghanaian Research Consultancy Project",
    "intl_student": "International Student Research",
    "intl_funded": "International / Externally Funded Research",
    "clinical_trial": "Clinical / Interventional Trial",
}

POST_APPROVAL_LABELS = {
    "minor_amendment": "Minor Protocol Amendment",
    "major_amendment": "Major Protocol Amendment (Substantive Re-Review)",
    "continuing_review": "Annual Continuing Review / Renewal",
    "closure": "Study Closure / Final Report",
    "corrected_resubmission": "Response to Committee Comments / Corrected Resubmission",
}

ALL_LABELS = {**REVIEW_TYPE_LABELS, **APPLICANT_CATEGORY_LABELS, **POST_APPROVAL_LABELS}

# Seed values only -- the migrations above write these into FeeSetting
# once; after that, the database (editable from the admin Finance page)
# is the only source of truth. Also used as the in-memory fallback if a
# key somehow has no FeeSetting row yet (e.g. mid-migration) so the
# payment gate never silently lets someone through for free.
#
# intl_student / intl_funded / clinical_trial are published as US$75 /
# US$200 / US$500 "or GHS equivalent" -- rather than processing a second
# currency through Paystack (and splitting every GHS-only financial
# report in this project), these are charged in GHS at a seed rate of
# ~GHS 15 per US$1. That rate moves; update these three rows from the
# Finance page to match the actual rate whenever it drifts.
DEFAULT_FEES = {
    "exemption": Decimal("150"),
    "expedited": Decimal("300"),
    "full": Decimal("500"),
    "not-sure": Decimal("300"),
    "ug_diploma": Decimal("170"),
    "masters_mphil": Decimal("400"),
    "phd": Decimal("500"),
    "gh_independent": Decimal("600"),
    "gh_institutional": Decimal("800"),
    "gh_consultancy": Decimal("1000"),
    "intl_student": Decimal("1125"),
    "intl_funded": Decimal("3000"),
    "clinical_trial": Decimal("7500"),
    "minor_amendment": Decimal("150"),
    "major_amendment": Decimal("300"),
    "continuing_review": Decimal("250"),
    "closure": Decimal("0"),
    "corrected_resubmission": Decimal("0"),
}

CURRENCY = "GHS"


def _all_settings():
    from .models import FeeSetting
    return {row.review_type: row for row in FeeSetting.objects.all()}


def schedule():
    """Every fee item's current FeeSetting, keyed by its slug -- what the
    admin/secretariat Finance pages and the application form's live fee
    notes render from."""
    existing = _all_settings()
    return {key: existing.get(key) for key in ALL_LABELS}


def fee_for(key):
    row = _all_settings().get(key)
    if row is not None:
        return row.amount
    # Unknown/blank key, or a row genuinely missing -- fall back to the
    # "not-sure" tier's default rather than defaulting to free, so a gap
    # in configuration can never be exploited to skip payment.
    return DEFAULT_FEES.get(key, DEFAULT_FEES["not-sure"])


def label_for(key):
    return ALL_LABELS.get(key, key or "Not specified")


def requires_payment(key):
    return fee_for(key) > 0


def fee_for_application(review_type, applicant_category):
    """What a new application actually owes.

    Application Category is the sole price driver -- a PhD student and a
    funded clinical trial pay very different amounts, regardless of
    anything else about the application. The applicant no longer picks a
    "review pathway" at all (that questionnaire was retired -- MSREC
    determines the actual review pathway during screening instead), so
    review_type is always blank on a new application.

    The two branches below only still matter for applications submitted
    before that questionnaire was removed: `review_type == "exemption"`
    preserves the flat concessionary fee those rows were quoted, and the
    category fallback below covers any row saved before applicant_category
    existed at all. Neither can be reached by a new submission.
    """
    if review_type == "exemption":
        return fee_for("exemption")
    if applicant_category:
        return fee_for(applicant_category)
    return fee_for(review_type)


def requires_payment_for_application(review_type, applicant_category):
    return fee_for_application(review_type, applicant_category) > 0
