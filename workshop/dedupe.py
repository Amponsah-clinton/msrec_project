"""One registration per person per workshop.

Nobody may register twice for the same workshop, but registering for a
different workshop is always fine -- so every rule here is scoped to one
Workshop and never looks across them.

Two signals identify "the same person":

  * email -- unambiguous. The same address is the same person, so this is
    also enforced in the database (see WorkshopRegistration.Meta's
    unique_active_email_per_workshop constraint). Case and surrounding
    whitespace are ignored.

  * name -- checked here but deliberately *not* a database constraint.
    Namesakes are genuinely common, so the name rule turns someone away
    with an explanation rather than making an irreversible claim that two
    rows are one person. A real double-submit shares the email anyway, and
    that path is airtight.

Why this matters beyond tidiness: the live data showed people registering
three times in four minutes, paying only on the last attempt. They were
re-registering because they had no way back to an unpaid registration. So
find_existing() hands the clashing row back to the caller, which can then
send them to *that* registration's checkout instead of a dead end.
"""
import re

from django.db.models.functions import Lower, Trim

_WHITESPACE = re.compile(r"\s+")


def normalize_email(value):
    return (value or "").strip().lower()


def normalize_name(value):
    """Casefolded, whitespace-collapsed name for comparison only -- never
    stored, so what a registrant typed is kept exactly as they typed it.

    "  Ama   MENSAH " and "ama mensah" are the same person here.
    """
    return _WHITESPACE.sub(" ", (value or "").strip()).casefold()


# What matched, for the message shown to the registrant.
EMAIL = "email"
NAME = "name"


def find_existing(workshop, *, email, name, exclude_pk=None):
    """The registration already on file for this person on this workshop,
    as (registration, matched_on), or (None, None).

    An email match wins over a name match: it is the certain one, and it is
    the only one safe to act on (see register() -- a name match must never
    hand someone another person's payment link).

    Rows already marked as duplicates are ignored, so clearing a duplicate
    frees that person to register again.
    """
    if workshop is None:
        return None, None

    candidates = workshop.registrations.filter(is_duplicate=False)
    if exclude_pk is not None:
        candidates = candidates.exclude(pk=exclude_pk)

    email_key = normalize_email(email)
    if email_key:
        # Lower(Trim(...)) rather than __iexact so this asks exactly what
        # the database constraint enforces. Both functions are portable, so
        # Postgres and SQLite agree.
        hit = candidates.annotate(key=Lower(Trim("email"))).filter(key=email_key).first()
        if hit is not None:
            return hit, EMAIL

    name_key = normalize_name(name)
    if name_key:
        # Collapsing runs of whitespace needs regexp_replace, which SQLite
        # doesn't have, so the comparison happens in Python. Only two small
        # columns are pulled -- never whole rows -- and it is scoped to one
        # workshop's registrations.
        for pk, stored in candidates.values_list("pk", "name"):
            if normalize_name(stored) == name_key:
                return candidates.filter(pk=pk).first(), NAME

    return None, None
