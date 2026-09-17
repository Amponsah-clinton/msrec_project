from decimal import Decimal

from django.db import migrations

# "Not Sure -- MSREC to Determine" was removed as a selectable review
# type on the application form (applicants now pick their best guess and
# the Secretariat reclassifies during screening if needed) -- this drops
# its now-unused FeeSetting row so it stops appearing on the Fee Schedule
# page and the admin/secretariat Finance editors. payments/fees.py keeps
# the "not-sure" label/fallback-price entries so any application/draft
# that already has review_type="not-sure" on file still resolves to a
# sensible label and amount.


def retire_not_sure(apps, schema_editor):
    FeeSetting = apps.get_model("payments", "FeeSetting")
    FeeSetting.objects.filter(review_type="not-sure").delete()
    # Restores the published GHS 150 exemption fee if it's still sitting
    # at a stale GHS 6 test value -- only touches the row if it's still
    # exactly that value, so a deliberate later price change from the
    # Finance page is never overwritten.
    FeeSetting.objects.filter(review_type="exemption", amount=Decimal("6")).update(amount=Decimal("150"))


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0004_seed_applicant_category_fees"),
    ]

    operations = [
        migrations.RunPython(retire_not_sure, noop),
    ]
