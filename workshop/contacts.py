"""The workshop contact list: one WorkshopContact per person who has ever
registered for any workshop, kept in step with WorkshopRegistration.

`record_registration` runs from the registration's post_save signal, so a
person lands on the list the moment they submit the form -- and their row
is refreshed again when they pay. It never raises: a contact-list hiccup
must not break someone's registration.

One person, one row. Registrations are matched to a contact by any of:
  * the same email (case ignored),
  * the same phone number (last nine digits, so 024..., +233 24... and
    233 24... are one number),
  * the same name with the words in any order ("Miracle Atianashie" ==
    "Atianashie Miracle"), for names of two or more words.
When a registration matches two existing contacts, they are merged. Every
email and phone a person used stays in their history, so nothing is lost.
"""
import logging
import re

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import WorkshopContact, WorkshopRegistration

logger = logging.getLogger(__name__)

_NON_DIGITS = re.compile(r"\D+")
_NAME_WORDS = re.compile(r"[^\w]+", re.UNICODE)
_TITLES = {"dr", "prof", "rev", "mr", "mrs", "ms", "miss", "hon", "sir", "madam"}


def _iso(dt):
    return dt.isoformat() if dt else ""


# ---- pure helpers (also used by migrations: plain values only) --------

def entry_for(reg, workshop_title, workshop_start):
    """One registration as a history entry, carrying the details given."""
    return {
        "reg": reg.pk,
        "workshop_id": reg.workshop_id,
        "title": workshop_title,
        "date": _iso(workshop_start),
        "registered": _iso(reg.created_at),
        "paid": reg.payment_status == "success",
        "name": (reg.name or "").strip()[:200],
        "email": (reg.email or "").strip().lower(),
        "phone": (reg.phone or "").strip()[:40],
        "institution": (reg.institution or "").strip()[:200],
    }


def phone_key(phone):
    digits = _NON_DIGITS.sub("", phone or "")
    return digits[-9:] if len(digits) >= 9 else ""


def name_key(name):
    """Lower-cased words, sorted, honorifics (Dr, Prof, Rev ...) dropped."""
    words = [w for w in _NAME_WORDS.split((name or "").lower()) if w and w not in _TITLES]
    return " ".join(sorted(words)) if len(words) >= 2 else ""


def keys_for(entry):
    keys = set()
    if entry.get("email"):
        keys.add("e:" + entry["email"])
    if phone_key(entry.get("phone")):
        keys.add("p:" + phone_key(entry["phone"]))
    if name_key(entry.get("name")):
        keys.add("n:" + name_key(entry["name"]))
    return keys


def history_keys(history):
    keys = set()
    for e in history or []:
        keys |= keys_for(e)
    return keys


def summarize(history):
    """The contact's fields, derived from its history: newest details win,
    and the workshop count is of distinct workshops (registering twice for
    the same one doesn't make it two)."""
    history = sorted(history, key=lambda e: e.get("registered", ""))
    latest_first = list(reversed(history))

    def newest(field):
        return next((e.get(field) for e in latest_first if e.get(field)), "")

    workshops = {e.get("workshop_id") or e.get("title") for e in history}
    from django.utils.dateparse import parse_datetime
    stamps = [parse_datetime(e["registered"]) for e in history if e.get("registered")]
    return {
        "history": history,
        "email": newest("email"),
        "name": newest("name") or newest("email"),
        "phone": newest("phone"),
        "institution": newest("institution"),
        "registration_count": len(workshops),
        "has_paid": any(e.get("paid") for e in history),
        "first_registered_at": min(stamps) if stamps else None,
        "last_registered_at": max(stamps) if stamps else None,
    }


def merge_entry(history, entry):
    return [e for e in (history or []) if e.get("reg") != entry["reg"]] + [entry]


# ---- live sync --------------------------------------------------------

def record_registration(reg):
    ws = reg.workshop
    entry = entry_for(reg, ws.title if ws else "Workshop", ws.starts_at if ws else None)
    keys = keys_for(entry)
    if not entry["email"] or not keys:
        return None
    try:
        with transaction.atomic():
            matches = [c for c in WorkshopContact.objects.select_for_update()
                       if c.pk and (keys & contact_keys(c))]
            # Oldest contact survives; any others it now joins fold into it.
            matches.sort(key=lambda c: c.pk)
            contact = matches[0] if matches else WorkshopContact()
            history = list(contact.history or [])
            for other in matches[1:]:
                history += other.history or []
                if other.last_messaged_at and (not contact.last_messaged_at or other.last_messaged_at > contact.last_messaged_at):
                    contact.last_messaged_at = other.last_messaged_at
                other.delete()
            for field, value in summarize(merge_entry(history, entry)).items():
                setattr(contact, field, value)
            contact.save()
        return contact
    except Exception:
        logger.exception("Couldn't update the workshop contact list for registration %s", reg.pk)
        return None


def contact_keys(contact):
    keys = history_keys(contact.history)
    # Rows from before history carried details: fall back to the contact's own.
    keys |= keys_for({"email": contact.email, "phone": contact.phone, "name": contact.name})
    return keys


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
