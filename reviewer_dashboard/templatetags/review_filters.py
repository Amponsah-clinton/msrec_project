"""Presentation-only helpers for the "Full Submitted Text" dump on the
Ethical Review Assessment page (dashboards/reviewer/review-application.html).

Application.form_data is keyed by the application form's raw `name`
attributes (camelCase, e.g. "piName", "fundedYn") and stores checkbox
groups as Python lists (e.g. ["clinical-trial", "community-based"]) --
exactly right for the applicant's own form to repopulate itself from, but
unreadable shown to a reviewer verbatim ("fundedYn: no", "studyType:
['clinical-trial', 'community-based']"). These two filters turn that back
into what a human wrote, without touching form_data itself.
"""
import re

from django import template

register = template.Library()

# Short, well-known acronyms that would otherwise Title Case into "Pi" /
# "Coi" -- everything else falls back to a plain capitalized word.
_ACRONYMS = {"pi": "PI", "id": "ID", "url": "URL", "coi": "COI", "ai": "AI"}

# Splits "piName" -> ["pi", "Name"], "allInvolvedYn" -> ["all", "Involved", "Yn"].
_WORD_RE = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?=[A-Z]|$)")


@register.filter
def humanize_key(key):
    """"fundedYn" -> "Funded?", "piInstitution" -> "PI Institution"."""
    words = _WORD_RE.findall(key or "")
    if not words:
        return key

    suffix = ""
    if words[-1].lower() == "yn":
        words = words[:-1]
        suffix = "?"

    labeled = [_ACRONYMS.get(w.lower(), w.capitalize()) for w in words]
    return (" ".join(labeled) + suffix) if labeled else key


@register.filter
def pretty_value(value):
    """Renders a form_data value the way the applicant actually meant it:
    a checkbox-group list becomes a comma-separated, Title Cased phrase
    instead of a Python list literal; a plain yes/no or True/False answer
    becomes "Yes"/"No"; everything else is left as the string it already is
    (dates, free text, single-choice answers already read fine as-is)."""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return ", ".join(_title_option(v) for v in value) if value else "None selected"
    if isinstance(value, str) and value.strip().lower() in ("yes", "no"):
        return value.strip().capitalize()
    return value


def _title_option(value):
    return str(value).replace("-", " ").replace("_", " ").strip().title()
