"""Institution naming and list upkeep.

Every form that offers the admin-managed Institution dropdown (sign-up,
workshop registration, the Committee Members forms on the admin and
secretariat dashboards) also offers an "Other (not listed)" option with a
companion free-text box, so a member whose institution isn't on the list
can still register. This module is the one place that handles what happens
to such a typed-in name:

  * `title_case` puts it in Title Case, so the list can't fill up with
    "university of ghana" / "UNIVERSITY OF GHANA" variants of one name;
  * `canonical_name` folds it onto an institution already on the list when
    one matches case-insensitively, so the member's own record and the list
    always spell it the same way;
  * `register` adds what's left to the list, so the next person signing up
    simply picks it from the dropdown.
"""

import logging
import re

logger = logging.getLogger(__name__)

# The value the Institution <select>s post when "Other (not listed)" --
# which every one of them offers first, ahead of the list itself -- is
# picked. The companion free-text field carries the actual name.
OTHER_VALUE = "__other__"

# Institution.name's max_length; every name is clipped to it before storage.
MAX_NAME_LENGTH = 200

# An all-capitals word of no more than this many letters is read as an
# acronym the member means literally (KNUST, UCC, UHAS, KATH, GIMPA) and
# left untouched; a longer one is just caps-lock ("TEACHING") and is
# title-cased with the rest.
_ACRONYM_MAX_LETTERS = 6

# A run of letters, with no reliance on \w (which would swallow digits and
# underscores). The JS half of this rule uses \p{L}+ for the same reason.
_LETTER_RUN = re.compile(r"[^\W\d_]+", re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def _has_lower(text):
    return any(ch.islower() for ch in text)


def _has_upper(text):
    return any(ch.isupper() for ch in text)


def _letter_count(text):
    return sum(1 for ch in text if ch.isalpha())


def _is_acronym(word):
    return (
        _has_upper(word)
        and not _has_lower(word)
        and _letter_count(word) <= _ACRONYM_MAX_LETTERS
    )


def _capitalize_word(word):
    """Capitalizes the first letter of each letter-run in one word, so
    hyphenated and Irish-style names read correctly -- "kwame-nkrumah" ->
    "Kwame-Nkrumah", "o'brien" -> "O'Brien" -- while a possessive stays
    lowercase: "mary's" -> "Mary's", never "Mary'S"."""

    def replace(match):
        run = match.group(0)
        start = match.start()
        # Only an O'-style prefix (a single letter, then the apostrophe, at
        # the very start of the word) capitalizes what follows the quote.
        if start > 0 and word[start - 1] == "'" and start != 2:
            return run.lower()
        return run[:1].upper() + run[1:].lower()

    return _LETTER_RUN.sub(replace, word)


def title_case(value):
    """Capitalizes each word of an institution name, collapsing runs of
    whitespace. Acronyms survive: a name typed with any lowercase in it
    its acronyms and its mixed-case words ("University of Ghana, KNUST" ->
    "University Of Ghana, KNUST", "McDonald clinic" -> "McDonald Clinic"),
    while a word shouted in full is not an acronym ("korle bu TEACHING
    hospital" -> "Korle Bu Teaching Hospital"). A name typed entirely in
    capitals is
    treated as caps-lock and title-cased ("UNIVERSITY OF GHANA" ->
    "University Of Ghana") unless it is a single short token (KNUST)."""
    name = _WHITESPACE.sub(" ", (value or "").strip())
    if not name:
        return ""

    words = name.split(" ")
    if not _has_lower(name):
        if len(words) == 1 and _is_acronym(name):
            return name
        return " ".join(_capitalize_word(word) for word in words)

    return " ".join(
        word if _is_acronym(word) or _has_upper(word) and _has_lower(word)
        else _capitalize_word(word)
        for word in words
    )


def active():
    """The institutions offered in the dropdowns, in their admin-set order."""
    from pages.models import Institution

    return list(Institution.objects.filter(is_active=True))


def canonical_name(value):
    """The name to store for one submitted institution.

    An institution already on the list (however it was cased or spaced on
    the way in, and whether it was picked from the dropdown or typed into
    the "Other" box) comes back spelled exactly as the list spells it;
    anything new comes back in Title Case, ready for `register`.
    """
    from pages.models import Institution

    name = _WHITESPACE.sub(" ", (value or "").strip())
    if not name:
        return ""

    existing = Institution.objects.filter(name__iexact=name).values_list("name", flat=True).first()
    if existing:
        return existing
    return title_case(name)[:MAX_NAME_LENGTH]


def resolve_choice(select_value, other_value):
    """Folds one Institution dropdown and its companion "Other" text box
    into the single name to store. Handles the case where the page's own
    script already promoted a typed-in name into the dropdown (so the
    select, not the text box, carries it)."""
    selected = (select_value or "").strip()
    if selected == OTHER_VALUE:
        selected = (other_value or "").strip()
    return canonical_name(selected)


def register(names):
    """Adds institutions to the admin-managed list so the next person
    signing up can pick them from the dropdown. Matching is
    case-insensitive, so a differently-cased duplicate is never created,
    and a name picked straight from the list is a no-op. Each insert is
    isolated and best effort -- it must never block (or roll back) the
    registration that produced it."""
    from django.db import transaction

    from pages.models import Institution

    for raw in names:
        name = canonical_name(raw)
        if not name:
            continue
        try:
            with transaction.atomic():
                if not Institution.objects.filter(name__iexact=name).exists():
                    Institution.objects.create(name=name[:MAX_NAME_LENGTH], is_active=True)
        except Exception:
            # A race on the unique name, or any storage hiccup -- the
            # member's own record already holds the institution, so this
            # is non-fatal.
            logger.exception("Could not auto-add institution %r to the list", name)
