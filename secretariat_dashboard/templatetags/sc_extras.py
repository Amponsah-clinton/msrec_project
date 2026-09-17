import re

from django.template import Library

register = Library()

# Application.form_data is keyed by the raw `name` attribute of each field
# on the applicant's form (piName, studyPurpose, irbReferenceNo, ...), so
# the Secretariat's "All submitted answers" dump was printing camelCase
# identifiers as its labels. These are the fragments that shouldn't come
# out of that as "Pi", "Irb" or "Orcid".
ACRONYMS = {
    "pi": "PI",
    "irb": "IRB",
    "rec": "REC",
    "orcid": "ORCID",
    "hod": "HOD",
    "cv": "CV",
    "id": "ID",
    "no": "No.",
    "url": "URL",
    "dob": "DOB",
    "sop": "SOP",
    "coi": "COI",
}

_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|[_\-\s]+")


@register.filter
def humanize_key(value):
    """'piName' -> 'PI Name', 'irbReferenceNo' -> 'IRB Reference No.'

    Only ever used for display of keys we don't control; anything that
    doesn't split cleanly is returned close to as-is rather than mangled.
    """
    text = str(value).strip()
    if not text:
        return ""
    words = [w for w in _BOUNDARY.split(text) if w]
    return " ".join(ACRONYMS.get(w.lower(), w[:1].upper() + w[1:]) for w in words)
