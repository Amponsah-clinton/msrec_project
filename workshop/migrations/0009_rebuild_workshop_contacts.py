from django.db import migrations


def rebuild(apps, schema_editor):
    """Rebuilds the contact list from every registration so the same person
    is one row even when they registered with a second email, phone or with
    their names in a different order (see workshop/contacts.py). Keeps each
    person's last-messaged date."""
    from workshop.contacts import entry_for, keys_for, summarize

    Registration = apps.get_model("workshop", "WorkshopRegistration")
    Contact = apps.get_model("workshop", "WorkshopContact")

    messaged = {}
    for c in Contact.objects.exclude(last_messaged_at=None):
        messaged[c.email] = c.last_messaged_at

    groups = []  # each: {"keys": set, "history": list}
    for reg in Registration.objects.select_related("workshop").order_by("created_at"):
        if not (reg.email or "").strip():
            continue
        ws = reg.workshop
        entry = entry_for(reg, ws.title if ws else "Workshop", ws.starts_at if ws else None)
        keys = keys_for(entry)
        hits = [g for g in groups if g["keys"] & keys]
        group = hits[0] if hits else {"keys": set(), "history": []}
        for other in hits[1:]:
            group["keys"] |= other["keys"]
            group["history"] += other["history"]
            groups.remove(other)
        group["keys"] |= keys
        group["history"].append(entry)
        if not hits:
            groups.append(group)

    Contact.objects.all().delete()
    rows = []
    for g in groups:
        fields = summarize(g["history"])
        emails = {e["email"] for e in g["history"]}
        stamps = [messaged[e] for e in emails if e in messaged]
        rows.append(Contact(last_messaged_at=max(stamps) if stamps else None, **fields))
    Contact.objects.bulk_create(rows, batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ("workshop", "0008_workshop_contacts"),
    ]

    operations = [
        migrations.RunPython(rebuild, migrations.RunPython.noop),
    ]
