from decimal import Decimal

from django.db import migrations

# Matches DEFAULT_FEES / REVIEW_TYPE_LABELS in payments/fees.py and the
# schedule already published on payments-fees.html -- a one-time seed.
# From here on the admin Finance page's Fee Schedule editor is the only
# way these change.
SEED = [
    ("exemption", "Ethics Determination / Exemption Assessment", Decimal("0")),
    ("expedited", "Expedited Review", Decimal("300")),
    ("full", "Full Committee Review", Decimal("500")),
    ("not-sure", "Not Sure — MSREC to Determine", Decimal("300")),
]


def seed_fee_settings(apps, schema_editor):
    FeeSetting = apps.get_model("payments", "FeeSetting")
    for review_type, label, amount in SEED:
        FeeSetting.objects.get_or_create(
            review_type=review_type,
            defaults={"label": label, "amount": amount, "currency": "GHS"},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0002_feesetting"),
    ]

    operations = [
        migrations.RunPython(seed_fee_settings, noop),
    ]
