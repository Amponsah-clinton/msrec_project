"""Backfills membership_ethics_id/membership_confirmed_at for accounts that
were already approved as Committee members before this feature existed --
without this, User.approve_role() (which only runs at approval time) would
never retroactively issue them a certificate/ID, since they're never
re-approved. See accounts/models.py's approve_role/generate_membership_ethics_id
and committee_dashboard/certificate.py.
"""
from django.db import migrations
from django.utils import timezone


def backfill(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(role="committee", committee_status="approved", membership_ethics_id__isnull=True):
        user.membership_ethics_id = f"MSREC/ETH/{user.pk:05d}"
        user.membership_confirmed_at = user.membership_confirmed_at or timezone.now()
        user.save(update_fields=["membership_ethics_id", "membership_confirmed_at"])


def noop_reverse(apps, schema_editor):
    """Not reversed -- a certificate already issued/downloaded shouldn't
    silently stop being valid just because someone reverses this migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_user_membership_confirmed_at_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
