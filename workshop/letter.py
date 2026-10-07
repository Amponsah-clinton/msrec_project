"""The "Confirmation of Participation" letter for a workshop participant.

Rendered on the same A4 letter engine as the platform's Appointment and
Suspension letters (accounts.letters) -- so it carries the MSREC letterhead,
the addressee block, the Chair's signature and the running footer, and fits
itself onto one page. Only the wording is workshop-specific.
"""
from types import SimpleNamespace

from django.utils import timezone


def render_confirmation_letter_pdf(reg, workshop=None):
    """PDF bytes of the Confirmation of Participation letter for `reg`."""
    from accounts import letters as letter_engine

    ws_obj = workshop or reg.workshop

    # A blank letterhead/signatory template -> the engine falls back to the
    # built-in text letterhead and the Chair's signature (Site Settings ->
    # Certificates), exactly like every other MSREC letter.
    tpl = SimpleNamespace(header_path="", footer_path="", sign_name="", sign_title="", sign_path="")
    recipient = SimpleNamespace(
        full_name=reg.name, position="", institution=reg.institution or "", email=reg.email,
    )

    issued = reg.approved_at or timezone.now()
    workshop = ws_obj.title
    details = (ws_obj.description or "").strip()

    body = [
        ("text",
         f"We write to confirm that {reg.name} participated in the {workshop}, organised by the "
         f"Metascholar Research Ethics Committee (MSREC)."),
    ]
    if details:
        body.append(("text",
                     f"About the workshop: {details}"))
    body.append(("text",
                 f"This confirms the above-named's attendance and engagement in the workshop. "
                 f"This letter is issued at their request as evidence of participation and carries "
                 f"the reference {reg.participation_ref}."))
    if reg.is_paid:
        body.append(("text",
                     "A certificate of participation has been issued separately and accompanies this letter."))

    content = {
        "ethics_id": "",  # not an ethics approval -- keeps the meta line blank
        "date": issued,
        "flag": "",
        "title": "LETTER OF PARTICIPATION",
        "salutation": f"Dear {reg.name},",
        "subject": f"RE: CONFIRMATION OF PARTICIPATION IN {workshop.upper()}",
        "body": body,
        "closing": [
            "We thank you for taking part and for your commitment to strengthening research ethics. "
            "Please contact the Secretariat if you require anything further.",
        ],
        "sign_off": "Yours sincerely,",
        "signatory": letter_engine.signatory(tpl),
        "doc_label": "Confirmation of Participation",
    }

    pdf, _pages, _scale = letter_engine.render(recipient, content, tpl)
    return pdf
