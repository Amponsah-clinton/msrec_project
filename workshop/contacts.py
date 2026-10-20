"""The workshop contact list: one WorkshopContact per person who has ever
registered for any workshop, kept in step with WorkshopRegistration.

`record_registration` runs from the registration's post_save signal, so a
person lands on the list the moment they submit the form -- and their row
is refreshed again when they pay. It never raises: a contact-list hiccup
must not break someone's registration.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import WorkshopContact, WorkshopRegistration

logger = logging.getLogger(__name__)


def _iso(dt):
    return dt.isoformat() if dt else ""


def apply_registration(contact, reg, workshop_title, workshop_start):
    """Folds one registration into a contact (unsaved). Also used by the
    0008 backfill migration, so it must only read plain field values."""
    entry = {
        "reg": reg.pk,
        "workshop_id": reg.workshop_id,
        "title": workshop_title,
        "date": _iso(workshop_start),
        "registered": _iso(reg.created_at),
        "paid": reg.payment_status == WorkshopRegistration.PaymentStatus.SUCCESS,
    }
    history = [e for e in (contact.history or []) if e.get("reg") != reg.pk]
    history.append(entry)
    history.sort(key=lambda e: e.get("registered", ""))
    contact.history = history
    contact.registration_count = len(history)
    contact.has_paid = any(e.get("paid") for e in history)

    when = reg.created_at
    if when and (not contact.first_registered_at or when < contact.first_registered_at):
        contact.first_registered_at = when
    is_latest = not contact.last_registered_at or (when and when >= contact.last_registered_at)
    if when and is_latest:
        contact.last_registered_at = when
    # The newest registration's details win; an older one only fills gaps.
    for field in ("name", "phone", "institution"):
        value = (getattr(reg, field, "") or "").strip()
        if value and (is_latest or not getattr(contact, field)):
            setattr(contact, field, value[:200] if field != "phone" else value[:40])
    return contact


def record_registration(reg):
    email = (reg.email or "").strip().lower()
    if not email:
        return None
    ws = reg.workshop
    try:
        with transaction.atomic():
            contact = WorkshopContact.objects.select_for_update().filter(email=email).first()
            if contact is None:
                contact = WorkshopContact(email=email, name=(reg.name or "")[:200] or email)
            apply_registration(contact, reg, ws.title if ws else "Workshop", ws.starts_at if ws else None)
            contact.save()
        return contact
    except Exception:
        logger.exception("Couldn't update the workshop contact list for registration %s", reg.pk)
        return None


@receiver(post_save, sender=WorkshopRegistration, dispatch_uid="workshop_contact_sync")
def _sync_contact(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw:  # loaddata
        return
    # Saves that only stamp "meeting link sent" and the like change nothing
    # the contact list shows -- skip them, so bulk sends stay cheap.
    if update_fields is not None and not set(update_fields) & _CONTACT_FIELDS:
        return
    record_registration(instance)


_CONTACT_FIELDS = {"name", "email", "phone", "institution", "workshop", "payment_status"}


# ---------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------

def fill(text, contact):
    """{name} / {first_name} for one contact. Plain replace, so a stray
    brace in a staff message can't raise."""
    return text.replace("{name}", contact.name).replace("{first_name}", contact.first_name)


def send_email(contact, *, subject, body):
    from notifications.emails import send_branded_email

    subject = fill(subject, contact)
    paragraphs = [line.strip() for line in fill(body, contact).splitlines() if line.strip()]
    return send_branded_email(
        subject=subject,
        to=contact.email,
        heading=subject,
        paragraphs=paragraphs,
        preheader="A message from MSREC workshops.",
    )
