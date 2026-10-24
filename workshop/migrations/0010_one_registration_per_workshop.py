"""One live registration per email per workshop.

The table already held repeat registrations when this rule arrived -- people
re-registering because they had no way back to an unpaid registration, some
of them having paid on the second or third attempt. So the order here
matters: add the flag, mark the repeats, and only then add the constraint,
which would otherwise fail on the existing rows.

Nothing is deleted. Every row is kept and the flag is reversible, so an
admin can review any decision this migration made (and its reverse clears
the flags again).
"""
from django.db import migrations, models
from django.db.models.functions import Lower, Trim


def flag_repeat_registrations(apps, schema_editor):
    """Keep one registration per (workshop, email); flag the rest.

    Which one is kept, in order of preference:

      1. a paid registration  -- never flag away someone's money
      2. an approved one      -- documents have already been issued
      3. one that got furthest -- a payment reference means they reached checkout
      4. the earliest         -- their original registration

    Rule 1 is the important one: in the live data two of the six duplicate
    groups had paid on their *last* attempt, so "keep the earliest" alone
    would have flagged the paid row.
    """
    Registration = apps.get_model("workshop", "WorkshopRegistration")

    def sort_key(reg):
        return (
            reg.payment_status != "success",          # paid first
            reg.approved_at is None,                  # then approved
            not reg.payment_reference,                # then furthest along
            reg.created_at or reg.id,                 # then earliest
            reg.id,
        )

    groups = {}
    for reg in Registration.objects.all():
        key = (reg.workshop_id, (reg.email or "").strip().lower())
        if not key[1]:
            continue
        groups.setdefault(key, []).append(reg)

    flagged = []
    for (workshop_id, email), regs in groups.items():
        if len(regs) < 2:
            continue
        regs.sort(key=sort_key)
        for loser in regs[1:]:
            loser.is_duplicate = True
            flagged.append(loser)

    if flagged:
        Registration.objects.bulk_update(flagged, ["is_duplicate"])


def unflag_all(apps, schema_editor):
    Registration = apps.get_model("workshop", "WorkshopRegistration")
    Registration.objects.filter(is_duplicate=True).update(is_duplicate=False)


class Migration(migrations.Migration):

    dependencies = [
        ("workshop", "0009_rebuild_workshop_contacts"),
    ]

    operations = [
        migrations.AddField(
            model_name="workshopregistration",
            name="is_duplicate",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(flag_repeat_registrations, unflag_all),
        migrations.AddConstraint(
            model_name="workshopregistration",
            constraint=models.UniqueConstraint(
                "workshop",
                Lower(Trim("email")),
                condition=models.Q(is_duplicate=False),
                name="unique_active_email_per_workshop",
            ),
        ),
    ]
