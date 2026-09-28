"""The Appointment Letter every approved Reviewer and Committee member
receives -- attached, with the Membership Certificate, to the approval email
(admin_dashboard.views._send_role_approved_email) and downloadable from
their dashboard (accounts.views.appointment_letter).

The wording (one version for Reviewers, one for Committee members), the
letterhead artwork and the signatory come from
pages.models.AppointmentLetterTemplate (Site Settings > Appointment
Letter), with {placeholders} filled from the member. Rendered on demand,
never stored, so an edited template or new signature applies to every
later download too. Layout and the fit-to-one-A4-page logic are shared with
the Suspension Letter (accounts/letters.py).
"""
from types import SimpleNamespace

from django.utils import timezone

from applicant_dashboard.approval_documents import COMMITTEE_NAME, fill, paragraphs

from . import letters, membership

KINDS = ("reviewer", "committee")

# Shown as click-to-insert chips on the settings page, in this order.
PLACEHOLDERS = [
    ("recipient_name", "The member's full name"),
    ("first_name", "The member's first name"),
    ("role", "Ethics Reviewer, or the Committee position (e.g. Committee Member, Vice Chair)"),
    ("a_role", "The role with “a” / “an” in front, e.g. “an Ethics Reviewer”"),
    ("role_caps", "The role in capitals, for the subject line"),
    ("ethics_id", "MSREC Ethics ID"),
    ("effective_date", "Date the appointment was approved"),
    ("institution", "The member's institution"),
    ("email", "The member's email address"),
    ("committee_name", COMMITTEE_NAME),
    ("signatory_name", "Who signs the letter"),
    ("signatory_title", "The signatory's position"),
    ("today", "Today's date"),
]
PLACEHOLDER_KEYS = {key for key, _ in PLACEHOLDERS}


def unknown_placeholders(*texts):
    return letters.unknown_placeholders(PLACEHOLDER_KEYS, *texts)


def _template(template=None):
    if template is not None:
        return template
    from pages.models import AppointmentLetterTemplate
    return AppointmentLetterTemplate.get_solo()


def values(user, *, sign, effective_at):
    _kind, role = membership.membership_role(user)
    article = "an" if role[:1].lower() in "aeiou" else "a"
    return {
        "recipient_name": user.full_name,
        "first_name": user.first_name or user.full_name,
        "role": role,
        "a_role": f"{article} {role}",
        "role_caps": role.upper(),
        "ethics_id": getattr(user, "membership_ethics_id", None) or "",
        "effective_date": letters.date_text(timezone.localtime(effective_at)),
        "institution": getattr(user, "institution", "") or "",
        "email": user.email,
        "committee_name": COMMITTEE_NAME,
        "signatory_name": sign["name"],
        "signatory_title": sign["title"],
        "today": letters.date_text(timezone.localtime()),
    }


def letter_content(user, template=None, *, kind=None):
    t = _template(template)
    kind = kind or membership.membership_role(user)[0]
    effective_at = getattr(user, "membership_confirmed_at", None) or timezone.now()
    sign = letters.signatory(t)
    v = values(user, sign=sign, effective_at=effective_at)
    committee = kind == "committee"
    return {
        "values": v,
        "doc_label": "Appointment Letter",
        "ethics_id": v["ethics_id"],
        "date": effective_at,
        "flag": "",
        "subject": fill(t.committee_subject if committee else t.reviewer_subject, v),
        "salutation": fill(t.salutation, v),
        "body": [("text", fill(p, v)) for p in paragraphs(t.committee_body if committee else t.reviewer_body)],
        "closing": [fill(p, v) for p in paragraphs(t.closing)],
        "sign_off": fill(t.sign_off, v),
        "signatory": sign,
    }


def render_letter(user, template=None, *, kind=None):
    """(pdf_bytes, page_count, scale) -- see letters.render."""
    t = _template(template)
    return letters.render(user, letter_content(user, t, kind=kind), t)


def render_letter_pdf(user, template=None, *, kind=None):
    return render_letter(user, template, kind=kind)[0]


def letter_filename(user):
    return f"MSREC-Appointment-Letter-{(user.membership_ethics_id or str(user.pk)).replace('/', '-')}.pdf"


def sample_user(kind="reviewer"):
    """A realistic stand-in for the settings-page preview."""
    now = timezone.now()
    committee = kind == "committee"
    return SimpleNamespace(
        pk=0, full_name="Prof. Efua Adjoa Mensah", first_name="Efua", email="e.mensah@example.com",
        position="Associate Professor", institution="University of Cape Coast",
        role="committee" if committee else "reviewer",
        membership_ethics_id=f"MSREC/{'CM' if committee else 'ER'}/{now.year}/0024",
        membership_confirmed_at=now,
        committee_status="approved" if committee else "not_requested",
        committee_profile={"committeePosition": "Committee Member"} if committee else {},
    )
