"""Emails to workshop registrants: the registration confirmation (with the
meeting link), the meeting link on its own, the certificate, and the
materials. Each reads the registration's own workshop.
"""
import logging

from django.utils import timezone

from notifications.emails import send_branded_email

logger = logging.getLogger(__name__)


def _ws(reg, workshop):
    return workshop or reg.workshop


def send_registration_received_email(reg, workshop=None):
    """Sent when someone submits the form (for a free registration) or once
    their certificate fee is paid -- a "we've got you" confirmation that also
    carries the meeting link when one is set."""
    ws = _ws(reg, workshop)
    paragraphs = [
        f"Hi {reg.name},",
        f"Thank you for registering for {ws.title}. Your registration has been received.",
    ]
    if reg.wants_certificate and reg.is_paid:
        paragraphs.append(
            f"Your certificate fee of {reg.currency} {reg.amount} has been received — your certificate "
            "will be emailed to you after the workshop."
        )
    elif reg.wants_certificate:
        paragraphs.append(
            "A certificate of participation is included for this workshop — it will be emailed "
            "to you once the workshop is complete."
        )
    if ws.meeting_link:
        paragraphs.append("Use the button below to join the workshop when it begins. Please join a few minutes early.")
    else:
        paragraphs.append("We'll email you the meeting link and any materials ahead of the workshop.")

    try:
        ok = send_branded_email(
            subject=f"Registration received — {ws.title}",
            to=reg.email,
            heading="Your registration has been received",
            paragraphs=paragraphs,
            cta_text="Join the workshop" if ws.meeting_link else None,
            cta_url=ws.meeting_link or None,
            preheader=f"You're registered for {ws.title}.",
        )
    except Exception:
        logger.exception("Workshop registration email failed for %s", reg.email)
        return False
    if ok and ws.meeting_link:
        reg.meeting_link_sent_at = timezone.now()
        reg.save(update_fields=["meeting_link_sent_at"])
    return ok


def send_meeting_link_email(reg, workshop=None):
    ws = _ws(reg, workshop)
    if not ws.meeting_link:
        return False, "No meeting link is set for this workshop yet."
    ok = send_branded_email(
        subject=f"Your link for {ws.title}",
        to=reg.email,
        heading="Your workshop meeting link",
        paragraphs=[
            f"Hi {reg.name},",
            f"Thank you for registering for {ws.title}. Use the link below to join.",
            "Please join a few minutes early. We look forward to seeing you there.",
        ],
        cta_text="Join the workshop",
        cta_url=ws.meeting_link,
        preheader=f"Your link for {ws.title}.",
    )
    if ok:
        reg.meeting_link_sent_at = timezone.now()
        reg.save(update_fields=["meeting_link_sent_at"])
    return ok, "Meeting link sent." if ok else "The email couldn't be sent — check email settings."


def send_certificate_email(reg, workshop=None):
    ws = _ws(reg, workshop)
    if not reg.certificate_ready:
        if reg.payment_outstanding:
            return False, "This person's certificate fee hasn't been paid yet."
        return False, "This person isn't down for a certificate."
    from .certificate import render_workshop_certificate_pdf

    try:
        pdf = render_workshop_certificate_pdf(reg, workshop=ws)
    except Exception:
        logger.exception("Workshop certificate render failed for %s", reg.pk)
        return False, "The certificate could not be generated."

    reg.save(update_fields=["certificate_ref"])

    filename = f"{reg.name.replace(' ', '_')}_certificate.pdf"
    ok = send_branded_email(
        subject=f"Your certificate — {ws.title}",
        to=reg.email,
        heading="Your workshop certificate",
        paragraphs=[
            f"Hi {reg.name},",
            f"Congratulations on completing {ws.title}. Your certificate of participation is attached.",
            "You're welcome to share it or add it to your professional profile.",
        ],
        preheader=f"Your certificate for {ws.title} is attached.",
        attachments=[(filename, pdf, "application/pdf")],
    )
    if ok:
        reg.certificate_sent_at = timezone.now()
        reg.save(update_fields=["certificate_sent_at"])
    return ok, "Certificate sent." if ok else "The email couldn't be sent — check email settings."


def send_payment_required_email(reg, workshop=None):
    """Sends someone a link to settle an outstanding certificate fee. Used
    when a workshop's certificate is made compulsory after people have
    already registered, and to chase anyone who never finished checkout."""
    ws = _ws(reg, workshop)
    if not reg.payment_outstanding:
        return False, "This person has nothing outstanding to pay."

    from django.conf import settings
    from django.urls import reverse

    pay_url = settings.SITE_URL.rstrip("/") + reverse("workshop:pay", kwargs={"pk": reg.pk})
    compulsory = reg.certificate_required_at_signup or ws.certificate_required
    paragraphs = [f"Hi {reg.name},"]
    if compulsory:
        paragraphs.append(
            f"A certificate of participation is part of {ws.title}, and a one-time fee of "
            f"{reg.currency} {reg.amount} applies to every participant."
        )
        paragraphs.append("Your place is held, but your registration is only complete once the fee is paid.")
    else:
        paragraphs.append(
            f"You asked for a certificate for {ws.title}. The one-time fee of "
            f"{reg.currency} {reg.amount} is still outstanding."
        )
    paragraphs.append("Use the button below to pay securely and we'll do the rest.")

    ok = send_branded_email(
        subject=f"Certificate fee outstanding — {ws.title}",
        to=reg.email,
        heading="Complete your certificate payment",
        paragraphs=paragraphs,
        cta_text="Pay certificate fee",
        cta_url=pay_url,
        preheader=f"{reg.currency} {reg.amount} outstanding for {ws.title}.",
    )
    if ok:
        try:
            from notifications import sms
            sms.send_sms(
                [reg.phone],
                f"MSREC: {ws.title} certificate fee of {reg.currency} {reg.amount} is outstanding. Pay: {pay_url}",
            )
        except Exception:
            logger.exception("Workshop payment-link SMS failed for %s", reg.phone)
    return ok, "Payment link sent." if ok else "The email couldn't be sent — check email settings."


MESSAGE_PLACEHOLDERS = ("{name}", "{first_name}", "{workshop}", "{amount}", "{pay_link}")


def pay_url_for(reg):
    """The public checkout link for this registrant, or "" when they owe
    nothing (so a {pay_link} in a message to a paid person stays empty)."""
    if not reg.payment_outstanding:
        return ""
    from django.conf import settings
    from django.urls import reverse

    return settings.SITE_URL.rstrip("/") + reverse("workshop:pay", kwargs={"pk": reg.pk})


def fill_placeholders(text, reg, workshop=None):
    """Swaps the {name}-style placeholders the composer offers for this
    registrant's details. Plain replace, not str.format, so a stray brace
    in a staff message can't raise."""
    ws = _ws(reg, workshop)
    owed = f"{reg.currency} {reg.amount}" if reg.payment_outstanding else ""
    values = {
        "{name}": reg.name,
        "{first_name}": (reg.name.split() or [reg.name])[0],
        "{workshop}": ws.title,
        "{amount}": owed,
        "{pay_link}": pay_url_for(reg),
    }
    for key, value in values.items():
        text = text.replace(key, value)
    return text


def send_custom_email(reg, workshop=None, *, subject, body, button=""):
    """A message staff write themselves in the Registrations tab's composer.
    Each line of `body` becomes a paragraph; `button` optionally adds the
    workshop's meeting link, materials or (for those who owe) the payment
    link as a button under it."""
    ws = _ws(reg, workshop)
    paragraphs = [line.strip() for line in fill_placeholders(body, reg, ws).splitlines() if line.strip()]
    cta_text = cta_url = None
    if button == "meeting" and ws.meeting_link:
        cta_text, cta_url = "Join the workshop", ws.meeting_link
    elif button == "materials" and ws.materials_download_url:
        cta_text, cta_url = "Open materials", ws.materials_download_url
    elif button == "pay" and reg.payment_outstanding:
        cta_text, cta_url = "Pay certificate fee", pay_url_for(reg)

    subject = fill_placeholders(subject, reg, ws)
    return send_branded_email(
        subject=subject,
        to=reg.email,
        heading=subject,
        paragraphs=paragraphs,
        cta_text=cta_text,
        cta_url=cta_url,
        preheader=f"A message about {ws.title}.",
    )


def send_materials_email(reg, workshop=None):
    ws = _ws(reg, workshop)
    from . import storage

    attachments = None
    has_link = bool(ws.materials_link)
    if ws.materials_file_path:
        data = storage.download_object(ws.materials_file_path)
        if data:
            fname = ws.materials_file_path.rsplit("/", 1)[-1] or "workshop-materials"
            attachments = [(fname, data, "application/octet-stream")]
    if not attachments and not has_link:
        return False, "No materials have been uploaded or linked for this workshop yet."

    paragraphs = [f"Hi {reg.name},", f"Here are the materials for {ws.title}."]
    if has_link:
        paragraphs.append("You can also access them online using the button below.")

    ok = send_branded_email(
        subject=f"Workshop materials — {ws.title}",
        to=reg.email,
        heading="Your workshop materials",
        paragraphs=paragraphs,
        cta_text="Open materials" if has_link else None,
        cta_url=ws.materials_link or None,
        preheader=f"Materials for {ws.title}.",
        attachments=attachments,
    )
    if ok:
        reg.materials_sent_at = timezone.now()
        reg.save(update_fields=["materials_sent_at"])
    return ok, "Materials sent." if ok else "The email couldn't be sent — check email settings."
