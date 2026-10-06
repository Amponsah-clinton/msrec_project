"""Approving a participant after the workshop: issue their documents (the
Confirmation of Participation letter, and the Certificate for paid
participants), email them as attachments, and text a unique download link.
"""
import logging

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from notifications.emails import send_branded_email

logger = logging.getLogger(__name__)


def _slug(name):
    out = "".join(c if c.isalnum() else "_" for c in (name or "participant")).strip("_")
    return out or "participant"


def _documents_for(reg, ws):
    """[(filename, bytes, mimetype), ...] -- the letter always, plus the
    certificate when the participant paid for one."""
    from .letter import render_confirmation_letter_pdf

    docs = [(
        f"{_slug(reg.name)}_Confirmation_of_Participation.pdf",
        render_confirmation_letter_pdf(reg, ws),
        "application/pdf",
    )]
    if reg.is_paid:
        from .certificate import render_workshop_certificate_pdf
        cert = render_workshop_certificate_pdf(reg)
        reg.save(update_fields=["certificate_ref"])  # ref assigned during render
        docs.append((f"{_slug(reg.name)}_Certificate.pdf", cert, "application/pdf"))
    return docs


def download_url(reg):
    return settings.SITE_URL.rstrip("/") + reverse(
        "workshop:documents", kwargs={"token": reg.download_token}
    )


def approve_and_send(reg, ws):
    """Approve `reg` and deliver their documents by email + SMS. Returns
    (ok, message). Best-effort on delivery; never raises."""
    from .models import WorkshopRegistration

    if reg.is_paid:
        reg.ensure_certificate_ref()
    reg.ensure_download_token()
    if reg.approved_at is None:
        reg.approved_at = timezone.now()
    reg.save(update_fields=["certificate_ref", "download_token", "approved_at"])

    try:
        docs = _documents_for(reg, ws)
    except Exception:
        logger.exception("Workshop document render failed for %s", reg.pk)
        return False, "The documents could not be generated."

    url = download_url(reg)
    what = (
        "your Certificate and your Confirmation of Participation letter"
        if reg.is_paid else "your Confirmation of Participation letter"
    )

    emailed = False
    try:
        emailed = send_branded_email(
            subject=f"Your documents — {ws.workshop_title}",
            to=reg.email,
            heading="Your workshop documents are ready",
            paragraphs=[
                f"Hi {reg.name},",
                f"Thank you for taking part in {ws.workshop_title}. Attached to this email you'll find {what}.",
                "You can also download them at any time using your secure link below.",
            ],
            cta_text="Download my documents",
            cta_url=url,
            preheader=f"Your documents for {ws.workshop_title} are ready.",
            attachments=docs,
        )
    except Exception:
        logger.exception("Workshop documents email failed for %s", reg.email)

    # Text the unique download link.
    try:
        from notifications import sms
        sms.send_sms([reg.phone], f"MSREC: Your {ws.workshop_title} documents are ready. Download: {url}")
    except Exception:
        logger.exception("Workshop documents SMS failed for %s", reg.phone)

    now = timezone.now()
    reg.documents_sent_at = now
    fields = ["documents_sent_at"]
    if reg.is_paid and not reg.certificate_sent_at:
        reg.certificate_sent_at = now
        fields.append("certificate_sent_at")
    reg.save(update_fields=fields)

    if emailed:
        return True, "Documents sent."
    return False, "Documents prepared, but the email couldn't be sent — check email settings."
