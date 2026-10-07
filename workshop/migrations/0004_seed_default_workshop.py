"""Migrate the old single-workshop singletons into the first Workshop row and
link every existing registration to it, so the move to multi-workshop keeps
all current data."""
from django.db import migrations


def forwards(apps, schema_editor):
    Workshop = apps.get_model("workshop", "Workshop")
    WorkshopRegistration = apps.get_model("workshop", "WorkshopRegistration")
    WorkshopSettings = apps.get_model("workshop", "WorkshopSettings")
    WorkshopCertificateTemplate = apps.get_model("workshop", "WorkshopCertificateTemplate")

    if Workshop.objects.exists():
        workshop = Workshop.objects.order_by("pk").first()
    else:
        s = WorkshopSettings.objects.order_by("pk").first()
        t = WorkshopCertificateTemplate.objects.order_by("pk").first()
        from django.utils.text import slugify

        title = (s.workshop_title if s else "") or "MSREC Research Ethics Workshop"
        workshop = Workshop(
            title=title,
            slug=slugify(title)[:220] or "workshop",
            tagline=(s.workshop_tagline if s else "") or "",
            description=(s.workshop_description if s else "") or "",
            banner_image_path=(s.banner_image_path if s else "") or "",
            banner_image_link=(s.banner_image_link if s else "") or "",
            certificate_fee=(s.certificate_fee if s else 100),
            fee_currency=(s.fee_currency if s else "GHS") or "GHS",
            meeting_link=(s.meeting_link if s else "") or "",
            materials_file_path=(s.materials_file_path if s else "") or "",
            materials_link=(s.materials_link if s else "") or "",
            is_published=True,
            registration_closed=not (s.registration_open if s else True),
        )
        if t:
            workshop.cert_title_tail = t.title_tail or "of Participation"
            workshop.cert_intro = t.intro or "This is to certify that"
            workshop.cert_body = t.body or workshop.cert_body
            workshop.cert_seal_caption = t.seal_caption or "WORKSHOP"
            workshop.cert_sig1_name = t.signatory1_name or ""
            workshop.cert_sig1_title = t.signatory1_title or "Workshop Coordinator"
            workshop.cert_sig1_signature_path = t.signatory1_signature_path or ""
            workshop.cert_sig2_name = t.signatory2_name or ""
            workshop.cert_sig2_title = t.signatory2_title or "Workshop Coordinator"
            workshop.cert_sig2_signature_path = t.signatory2_signature_path or ""
        workshop.save()

    WorkshopRegistration.objects.filter(workshop__isnull=True).update(workshop=workshop)


def backwards(apps, schema_editor):
    # Unlink registrations; the Workshop rows are left in place.
    WorkshopRegistration = apps.get_model("workshop", "WorkshopRegistration")
    WorkshopRegistration.objects.update(workshop=None)


class Migration(migrations.Migration):
    dependencies = [
        ("workshop", "0003_workshop_workshopregistration_workshop"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
