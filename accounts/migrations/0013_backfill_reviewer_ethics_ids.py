"""Every approved Reviewer now gets an MSREC Ethics ID (previously only
Committee members did -- see User.approve_role). Issue one to approved
reviewers who were approved before that change, dated to their approval
where the audit log records it."""
from django.db import migrations
from django.utils import timezone


def backfill(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    RoleApprovalLog = apps.get_model("accounts", "RoleApprovalLog")
    for user in User.objects.filter(membership_ethics_id__isnull=True, reviewer_status="approved"):
        approved = (
            RoleApprovalLog.objects.filter(user=user, action="approved").order_by("created_at").first()
        )
        user.membership_ethics_id = f"MSREC/ETH/{user.pk:05d}"
        user.membership_confirmed_at = approved.created_at if approved else timezone.now()
        user.save(update_fields=["membership_ethics_id", "membership_confirmed_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0012_backfill_committee_reviewer_status"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
