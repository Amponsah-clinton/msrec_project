"""Emails the admin sends to workshop registrants from /admins/workshop/:
the meeting link, the certificate (PDF attached) and the materials.
"""
import logging

from django.utils import timezone

from notifications.emails import send_branded_email

logger = logging.getLogger(__name__)


def send_registration_received_email(reg, ws):
    """Sent to the registrant the moment they submit the /workshop form -- a
    "we've got you" confirmation that also carries the meeting link when one
    is set, so they have it straight away without waiting for the admin to
    send it."""
    paragraphs = [
        f"Hi {reg.name},",
        f"Thank you for registering for {ws.workshop_title}. Your registration has been received.",
    ]
    if reg.wants_certificate and not reg.is_paid:
        paragraphs.append(
            "You asked for a certificate — please complete the certificate fee payment to confirm it."
        )
    if ws.meeting_link:
        paragraphs.append("Use the button below to join the workshop when it begins. Please join a few minutes early.")
    else:
        paragraphs.append("We'll email you the meeting link and any materials ahead of the workshop.")

    try:
        ok = send_branded_email(
            subject=f"Registration received — {ws.workshop_title}",
            to=reg.email,
            heading="Your registration has been received",
            paragraphs=paragraphs,
            cta_text="Join the workshop" if ws.meeting_link else None,
            cta_url=ws.meeting_link or None,
            preheader=f"You're registered for {ws.workshop_title}.",
        )
    except Exception:
        logger.exception("Workshop registration email failed for %s", reg.email)
        return False
    if ok and ws.meeting_link:
        reg.meeting_link_sent_at = timezone.now()
        reg.save(update_fields=["meeting_link_sent_at"])
    return ok


def send_meeting_link_email(reg, ws):
    if not ws.meeting_link:
        return False, "No meeting link is set yet (set it in Workshop Settings)."
    ok = send_branded_email(
        subject=f"Your link for {ws.workshop_title}",
        to=reg.email,
        heading="Your workshop meeting link",
        paragraphs=[
            f"Hi {reg.name},",
            f"Thank you for registering for {ws.workshop_title}. Use the link below to join.",
            "Please join a few minutes early. We look forward to seeing you there.",
        ],
        cta_text="Join the workshop",
        cta_url=ws.meeting_link,
        preheader=f"Your link for {ws.workshop_title}.",
    )
    if ok:
        reg.meeting_link_sent_at = timezone.now()
        reg.save(update_fields=["meeting_link_sent_at"])
    return ok, "Meeting link sent." if ok else "The email couldn't be sent — check email settings."


def send_certificate_email(reg, ws):
    if not reg.is_paid:
        return False, "This person hasn't paid for a certificate."
    from .certificate import render_workshop_certificate_pdf

    try:
        pdf = render_workshop_certificate_pdf(reg)
    except Exception:
        logger.exception("Workshop certificate render failed for %s", reg.pk)
        return False, "The certificate could not be generated."

    # Persist the reference assigned during rendering.
    reg.save(update_fields=["certificate_ref"])

    filename = f"{reg.name.replace(' ', '_')}_certificate.pdf"
    ok = send_branded_email(
        subject=f"Your certificate — {ws.workshop_title}",
        to=reg.email,
        heading="Your workshop certificate",
        paragraphs=[
            f"Hi {reg.name},",
            f"Congratulations on completing {ws.workshop_title}. Your certificate of participation "
            "is attached to this email.",
            "You're welcome to share it or add it to your professional profile.",
        ],
        preheader=f"Your certificate for {ws.workshop_title} is attached.",
        attachments=[(filename, pdf, "application/pdf")],
    )
    if ok:
        reg.certificate_sent_at = timezone.now()
        reg.save(update_fields=["certificate_sent_at"])
    return ok, "Certificate sent." if ok else "The email couldn't be sent — check email settings."


def send_materials_email(reg, ws):
    from . import storage

    attachments = None
    has_link = bool(ws.materials_link)
    if ws.materials_file_path:
        data = storage.download_object(ws.materials_file_path)
        if data:
            fname = ws.materials_file_path.rsplit("/", 1)[-1] or "workshop-materials"
            attachments = [(fname, data, "application/octet-stream")]
    if not attachments and not has_link:
        return False, "No materials have been uploaded or linked yet (set them in Workshop Settings)."

    paragraphs = [
        f"Hi {reg.name},",
        f"Here are the materials for {ws.workshop_title}.",
    ]
    if has_link:
        paragraphs.append("You can also access them online using the button below.")

    ok = send_branded_email(
        subject=f"Workshop materials — {ws.workshop_title}",
        to=reg.email,
        heading="Your workshop materials",
        paragraphs=paragraphs,
        cta_text="Open materials" if has_link else None,
        cta_url=ws.materials_link or None,
        preheader=f"Materials for {ws.workshop_title}.",
        attachments=attachments,
    )
    if ok:
        reg.materials_sent_at = timezone.now()
        reg.save(update_fields=["materials_sent_at"])
    return ok, "Materials sent." if ok else "The email couldn't be sent — check email settings."
