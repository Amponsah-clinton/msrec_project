"""The PSA emails. Each returns True/False so the person who triggered it is
told the truth about delivery."""
import logging

logger = logging.getLogger(__name__)

# Always told when a client signs or asks for changes, whoever prepared the
# agreement.
SIGNED_NOTIFY_EMAIL = "ceo@academicdigital.space"


def _money(a):
    return f"{a.currency} {a.fee:,.2f}" if a.fee is not None else ""


def _send(**kwargs):
    from notifications.emails import send_branded_email
    try:
        return bool(send_branded_email(**kwargs))
    except Exception:
        logger.exception("PSA email %r failed", kwargs.get("subject"))
        return False


def _staff_recipients(a):
    """The CEO, plus whoever prepared the agreement."""
    to = [SIGNED_NOTIFY_EMAIL]
    preparer = getattr(a.created_by, "email", "") or getattr(a.company_signed_by, "email", "")
    if preparer and preparer.lower() != SIGNED_NOTIFY_EMAIL:
        to.append(preparer)
    return to


def send_to_client(a, *, reminder=False, updated=False, note=""):
    """The link the client completes and signs the agreement through.

    updated -- it's going back after the client asked for changes; `note`
    is what staff wrote back to them, if anything."""
    title = a.service_title or "your project"
    if updated:
        subject = f"Updated: Professional Service Agreement {a.reference} from Metascholar Limited"
        heading = "Your updated agreement is ready to sign"
        paragraphs = [
            f"Dear {a.client_name},",
            f"Thank you for flagging what needed to change on the agreement for “{title}”. "
            "We've reviewed your request and the agreement is ready for you again.",
            "Please check it through. If everything is now right, sign it online; if something "
            "still isn't, you can request changes again from the same page.",
        ]
    else:
        subject = (
            f"{'Reminder: ' if reminder else ''}Professional Service Agreement {a.reference} "
            "from Metascholar Limited"
        )
        heading = ("Your service agreement is still waiting for you" if reminder
                   else "Your service agreement is ready to sign")
        paragraphs = [
            f"Dear {a.client_name},",
            f"Metascholar Limited has prepared a Professional Service Agreement for “{title}”. "
            "It sets out the services, timelines, fees and responsibilities agreed between us.",
            "Please review it, enter your details and sign online. You can sign by drawing your "
            "signature or by typing your name. It takes about two minutes.",
            "If anything in it isn't right, use “Request changes” on the same page and we'll fix it "
            "before you sign.",
        ]
    return _send(
        subject=subject,
        to=a.client_email,
        heading=heading,
        paragraphs=paragraphs,
        quote_label="Our reply to your request" if updated and note else None,
        quote_text=note if updated and note else None,
        callout_label="Agreement",
        callout_value=a.reference,
        callout_note=f"Agreed fee: {_money(a)}" if a.fee is not None else None,
        cta_text="Review & sign the agreement",
        cta_url=a.client_url(),
        preheader=f"Agreement {a.reference} for {title} is ready for your signature.",
    )


def send_client_copy(a):
    """Confirmation for the client, with the link to their signed copy."""
    return _send(
        subject=f"Signed: Professional Service Agreement {a.reference}",
        to=a.client_email,
        heading="Thank you — your agreement is signed",
        paragraphs=[
            f"Dear {a.client_name},",
            f"Thank you for signing the Professional Service Agreement for “{a.service_title}”. "
            "Both parties have now signed it.",
            "You can open, print or save your copy at any time from the link below.",
        ],
        callout_label="Agreement",
        callout_value=a.reference,
        callout_note=f"Agreed fee: {_money(a)}" if a.fee is not None else None,
        cta_text="View your signed agreement",
        cta_url=a.client_url(),
        preheader=f"Your signed agreement {a.reference}.",
    )


def send_signed_to_staff(a):
    """Tells the CEO, and whoever prepared the agreement, that the client
    has signed."""
    return _send(
        subject=f"Client signed PSA {a.reference} — {a.client_name}",
        to=_staff_recipients(a),
        heading="A client has signed their service agreement",
        paragraphs=[
            f"{a.client_name} has reviewed and signed {a.reference} ({a.service_title}).",
            f"Agreed fee: {_money(a)} · Deposit: {a.currency} {a.deposit:,.2f}",
        ],
        cta_text="Open the agreement",
        cta_url=a.staff_url(),
        preheader=f"{a.client_name} signed {a.reference}.",
    )


def send_changes_requested_to_staff(a, req):
    """The client flagged something to fix instead of signing."""
    return _send(
        subject=f"Changes requested on PSA {a.reference} — {a.client_name}",
        to=_staff_recipients(a),
        heading="A client has asked for changes before signing",
        paragraphs=[
            f"{a.client_name} reviewed {a.reference} ({a.service_title}) and flagged something "
            "that needs fixing. They can't sign until the agreement is sent back to them.",
            f"Part of the agreement: {req.get_section_display()}",
            "Open the agreement, make the change (or reply that it stands), and send it back "
            "to the client.",
        ],
        quote_label="What the client wrote",
        quote_text=req.message,
        cta_text="Open the agreement",
        cta_url=a.staff_url(),
        preheader=f"{a.client_name} asked for changes to {a.reference}.",
    )


def send_change_request_receipt(a, req):
    """The client's own record of what they asked for."""
    return _send(
        subject=f"We've received your request — Agreement {a.reference}",
        to=a.client_email,
        heading="We've received your request for changes",
        paragraphs=[
            f"Dear {a.client_name},",
            f"Thank you for reviewing the agreement for “{a.service_title}”. We've received your "
            "request and will update the agreement.",
            "We'll email you as soon as it's ready to review and sign again.",
        ],
        quote_label=f"Your request — {req.get_section_display()}",
        quote_text=req.message,
        cta_text="View the agreement",
        cta_url=a.client_url(),
        preheader=f"Your requested changes to {a.reference} are with us.",
    )
