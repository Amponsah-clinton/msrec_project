from decimal import Decimal

from django.db import migrations

# Matches payments/fees.py's APPLICANT_CATEGORY_LABELS / POST_APPROVAL_LABELS
# / DEFAULT_FEES -- a one-time seed of the newly published fee schedule
# (Application Category tiers + post-approval item prices). From here on
# the admin Finance page's Fee Schedule editor is the only way these
# change, same as the original four review-type rows from 0003.
NEW_ROWS = [
    ("ug_diploma", "Undergraduate / Diploma Student Research", Decimal("170")),
    ("masters_mphil", "Master's / MPhil Student Research", Decimal("400")),
    ("phd", "PhD / Doctoral Student Research", Decimal("500")),
    ("gh_independent", "Ghanaian Independent / Self-Funded Researcher", Decimal("600")),
    ("gh_institutional", "Ghanaian Institutional / Funded Research Project", Decimal("800")),
    ("gh_consultancy", "Ghanaian Research Consultancy Project", Decimal("1000")),
    # Published as US$75 / US$200 / US$500 "or GHS equivalent" -- seeded
    # here in GHS at ~15/US$1 rather than processing a second currency
    # through Paystack. Update from the Finance page as the rate moves.
    ("intl_student", "International Student Research", Decimal("1125")),
    ("intl_funded", "International / Externally Funded Research", Decimal("3000")),
    ("clinical_trial", "Clinical / Interventional Trial", Decimal("7500")),
    ("minor_amendment", "Minor Protocol Amendment", Decimal("150")),
    ("major_amendment", "Major Protocol Amendment (Substantive Re-Review)", Decimal("300")),
    ("continuing_review", "Annual Continuing Review / Renewal", Decimal("250")),
    ("closure", "Study Closure / Final Report", Decimal("0")),
    ("corrected_resubmission", "Response to Committee Comments / Corrected Resubmission", Decimal("0")),
]

# The Determination/Exemption pathway's own published fee changed from
# free to a flat GHS 150 -- updated here rather than left for an admin to
# notice was still zero.
EXEMPTION_FEE = Decimal("150")


def seed_new_fees(apps, schema_editor):
    FeeSetting = apps.get_model("payments", "FeeSetting")
    for review_type, label, amount in NEW_ROWS:
        FeeSetting.objects.get_or_create(
            review_type=review_type,
            defaults={"label": label, "amount": amount, "currency": "GHS"},
        )
    FeeSetting.objects.filter(review_type="exemption", amount=Decimal("0")).update(amount=EXEMPTION_FEE)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0003_seed_fee_settings"),
    ]

    operations = [
        migrations.RunPython(seed_new_fees, noop),
    ]
