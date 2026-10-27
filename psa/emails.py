"""The PSA emails. Each returns True/False so the person who triggered it is
told the truth about delivery."""
import logging

logger = logging.getLogger(__name__)

# Always told when a client signs, whoever prepared the agreement.
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


def send_to_client(a, *, reminder=False):
    """The link the client completes and signs the agreement through."""
    title = a.service_title or "your project"
    return _send(
        subject=(
            f"{'Reminder: ' if reminder else ''}Professional Service Agreement {a.reference} "
            "from Metascholar Limited"
        ),
        to=a.client_email,
        heading="Your service agreement is ready to sign" if not reminder
        else "Your service agreement is still waiting for you",
        paragraphs=[
            f"Dear {a.client_name},",
            f"Metascholar Limited has prepared a Professional Service Agreement for “{title}”. "
            "It sets out the services, timelines, fees and responsibilities agreed between us.",
            "Please review it, confirm your details and sign online. You can sign by drawing your "
            "signature or by typing your name. It takes about two minutes.",
            "If anything in it doesn't match what we discussed, just reply to this email before signing.",
        ],
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
    to = [SIGNED_NOTIFY_EMAIL]
    preparer = getattr(a.created_by, "email", "") or getattr(a.company_signed_by, "email", "")
    if preparer and preparer.lower() != SIGNED_NOTIFY_EMAIL:
        to.append(preparer)
    return _send(
        subject=f"Client signed PSA {a.reference} — {a.client_name}",
        to=to,
        heading="A client has signed their service agreement",
        paragraphs=[
            f"{a.client_name} has reviewed and signed {a.reference} ({a.service_title}).",
            f"Agreed fee: {_money(a)} · Deposit: {a.currency} {a.deposit:,.2f}",
        ],
        cta_text="Open the agreement",
        cta_url=a.staff_url(),
        preheader=f"{a.client_name} signed {a.reference}.",
    )
