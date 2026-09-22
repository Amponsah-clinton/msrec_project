"""Backfills reviewer_status=APPROVED/wants_reviewer=True for accounts that
were already approved as Committee members before every Committee member
became a Reviewer too (see accounts/models.py's approve_role) -- without
this, only NEWLY approved committee members would get reviewer access;
existing ones would stay locked out of reviewer_dashboard and invisible to
the Secretariat's reviewer-assignment pool until re-approved (which never
happens automatically). See accounts/migrations/0011_backfill_membership_ethics_id.py
for the same "backfill what a behavior change missed" pattern.
"""
from django.db import migrations


def backfill(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(
        role="committee", committee_status="approved",
    ).exclude(reviewer_status="approved").update(reviewer_status="approved", wants_reviewer=True)


def noop_reverse(apps, schema_editor):
    """Not reversed -- a committee member who has already been using
    reviewer access (accepted assignments, etc.) shouldn't be silently
    locked out again just because someone reverses this migration."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_backfill_membership_ethics_id"),
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
