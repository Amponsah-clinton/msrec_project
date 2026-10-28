"""The PSA emails, each with its SMS twin. Each returns True/False so the
person who triggered it is told the truth about delivery."""
import logging

logger = logging.getLogger(__name__)

# Always told when a client signs or asks for changes, whoever prepared the
# agreement.
CEO_NOTIFY_EMAIL = "ceo@academicdigital.space"

# How much of a long client name survives into a text message.
SMS_NAME_LEN = 30


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
    to = [CEO_NOTIFY_EMAIL]
    preparer = getattr(a.created_by, "email", "") or getattr(a.company_signed_by, "email", "")
    if preparer and preparer.lower() != CEO_NOTIFY_EMAIL:
        to.append(preparer)
    return to


# ---------------------------------------------------------------------
# SMS twins
# ---------------------------------------------------------------------
# Every PSA email that has a number to reach also goes out as a text, so
# news of an agreement doesn't sit unread in an inbox. Three rules shape
# the wording:
#
#   * The text is a twin, never the only copy. It is sent only after the
#     email has gone, and a text that fails is logged, never raised --
#     the same fail-silently contract as notifications.sms.
#   * One segment. A segment is 160 GSM-7 characters and costs a credit,
#     and the client's signing link alone is 97 of them, so the wording
#     around a link has about sixty characters to live in.
#     PsaSmsTests.test_every_message_is_one_gsm_segment holds the line.
#   * ASCII only. The curly quotes and em dashes these emails are written
#     with sit outside GSM-7, and one of them would drop the whole
#     message from 160 characters a segment to 70 -- so _plain() folds
#     them back to their ASCII shapes before they reach a handset.

_GSM_FOLD = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...", " ": " ",
}


def _plain(text, limit=None):
    """Collapsed whitespace, GSM-7 punctuation, clipped to `limit`."""
    out = " ".join("".join(_GSM_FOLD.get(ch, ch) for ch in str(text or "")).split())
    if limit and len(out) > limit:
        out = out[:limit].rstrip(" ,.;:-") + "..."
    return out


def _sms(numbers, message, what):
    """Text everyone in `numbers` who can be reached. Never raises, and
    never reports a failure to the person who triggered the email -- the
    email is the message of record."""
    from notifications import sms

    numbers = [n for n in numbers if n]
    if not numbers or not sms.is_configured():
        return False
    try:
        result = sms.send_sms(numbers, message)
    except Exception:
        logger.exception("PSA %s SMS failed", what)
        return False
    if not result.get("ok"):
        logger.warning("PSA %s SMS not delivered: %s", what, result.get("error"))
    return bool(result.get("ok"))


def _client_phone(a):
    """The client's mobile, or "".

    Empty on everything sent before signing: the client gives their own
    number as part of signing (psa.forms.parse_client), which is the only
    place it is ever captured. So the agreement link, the reminder and
    the change-request receipt have no one to text until that happens."""
    from notifications import sms
    return sms.clean_phone(a.client_phone)


def _staff_phones(a):
    """Mobiles for the same people _staff_recipients emails, skipping
    anyone who has turned SMS off in Profile & Security."""
    from django.contrib.auth import get_user_model
    from django.db.models import Q

    from notifications import sms

    addresses = _staff_recipients(a)
    if not addresses:
        return []
    query = Q()
    for address in addresses:
        query |= Q(email__iexact=address)
    return [u.phone for u in get_user_model().objects.filter(query) if sms.can_sms_user(u)]


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
    ok = _send(
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
    if ok:
        _sms([_client_phone(a)], sms_to_client(a, reminder=reminder, updated=updated), "agreement link")
    return ok


def sms_to_client(a, *, reminder=False, updated=False):
    """The text that carries the signing link. The link is 97 of the 160
    characters, so everything else is pared to the bone."""
    if updated:
        return f"Metascholar agreement {a.reference} is updated. Sign: {a.client_url()}"
    if reminder:
        return f"Reminder: Metascholar agreement {a.reference} is unsigned: {a.client_url()}"
    return f"Metascholar agreement {a.reference}. Review and sign: {a.client_url()}"


def signed_pdf(a):
    """(filename, bytes, mimetype) of the signed agreement for attaching, or
    None if it couldn't be built -- the email still goes without it."""
    from . import pdf
    try:
        return (pdf.filename(a), pdf.render(a), "application/pdf")
    except Exception:
        logger.exception("PSA PDF for %s couldn't be built", a.reference)
        return None


def send_client_copy(a, attachment=None):
    """The client's "thank you", with their signed copy attached (and the
    link to it, which keeps working)."""
    ok = _send(
        subject=f"Signed: Professional Service Agreement {a.reference}",
        to=a.client_email,
        heading="Thank you — your agreement is signed",
        paragraphs=[
            f"Dear {a.client_name},",
            f"Thank you for signing the Professional Service Agreement for “{a.service_title}”. "
            "Both parties have now signed it.",
            ("Your signed copy is attached to this email as a PDF. You can also open, print or download "
             "it at any time from the link below." if attachment else
             "You can open, print or download your signed copy at any time from the link below."),
            "We look forward to working with you.",
        ],
        callout_label="Agreement",
        callout_value=a.reference,
        callout_note=f"Agreed fee: {_money(a)}" if a.fee is not None else None,
        cta_text="View your signed agreement",
        cta_url=a.client_url(),
        preheader=f"Your signed agreement {a.reference}" + (" is attached." if attachment else "."),
        attachments=[attachment] if attachment else None,
    )
    if ok:
        _sms([_client_phone(a)], sms_client_copy(a), "signed copy")
    return ok


def sms_client_copy(a):
    """No link in this one: the signed PDF is attached to the email it
    follows, which leaves room to say so in a single segment."""
    return (f"Metascholar agreement {a.reference} is now signed by both parties. "
            "Your signed copy has been emailed to you. Thank you.")


def send_signed_to_staff(a, attachment=None):
    """Tells the CEO, and whoever prepared the agreement, that the client
    has signed -- with the signed PDF attached for filing."""
    ok = _send(
        subject=f"Client signed PSA {a.reference} — {a.client_name}",
        to=_staff_recipients(a),
        heading="A client has signed their service agreement",
        paragraphs=[
            f"{a.client_name} has reviewed and signed {a.reference} ({a.service_title}).",
            f"Agreed fee: {_money(a)} · Deposit: {a.currency} {a.deposit:,.2f}",
        ] + (["The signed agreement is attached."] if attachment else []),
        cta_text="Open the agreement",
        cta_url=a.staff_url(),
        preheader=f"{a.client_name} signed {a.reference}.",
        attachments=[attachment] if attachment else None,
    )
    if ok:
        _sms(_staff_phones(a), sms_signed_to_staff(a), "client signed")
    return ok


def sms_signed_to_staff(a):
    fee = f" Fee {_money(a)}." if a.fee is not None else ""
    return (f"{a.reference}: {_plain(a.client_name, SMS_NAME_LEN)} has signed."
            f"{fee} {a.staff_url()}")


def send_changes_requested_to_staff(a, req):
    """The client flagged something to fix instead of signing."""
    ok = _send(
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
    if ok:
        _sms(_staff_phones(a), sms_changes_requested_to_staff(a), "changes requested")
    return ok


def sms_changes_requested_to_staff(a):
    return (f"{a.reference}: {_plain(a.client_name, SMS_NAME_LEN)} asked for changes "
            f"before signing. {a.staff_url()}")


def send_change_request_receipt(a, req):
    """The client's own record of what they asked for."""
    ok = _send(
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
    if ok:
        _sms([_client_phone(a)], sms_change_request_receipt(a), "change request receipt")
    return ok


def sms_change_request_receipt(a):
    return (f"Metascholar: we have your change request for agreement {a.reference}. "
            "We will email you when it is ready to sign again.")


# ---------------------------------------------------------------------
# Payment links and receipts
# ---------------------------------------------------------------------

def send_payment_link(a, req, *, reminder=False):
    """The link the client pays the outstanding balance through."""
    amount = f"{req.currency} {req.amount:,.2f}"
    owing = a.amount_owing
    if reminder:
        subject = f"Reminder: payment outstanding on agreement {a.reference}"
        heading = "Your payment is still outstanding"
        opening = (f"This is a reminder that {amount} is still outstanding on the Professional "
                   f"Service Agreement for “{a.service_title or 'your project'}”.")
    else:
        subject = f"Payment request for agreement {a.reference} — {amount}"
        heading = "A payment is due on your agreement"
        opening = (f"{amount} is now due on the Professional Service Agreement for "
                   f"“{a.service_title or 'your project'}”.")

    paragraphs = [f"Dear {a.client_name},", opening]
    if req.note:
        paragraphs.append(f"This payment covers: {req.note}")
    paragraphs += [
        "Use the secure button below to pay by card or mobile money. The page shows the exact "
        "amount and nothing else can be charged through it.",
        "Your receipt is emailed to you the moment the payment goes through.",
    ]
    ok = _send(
        subject=subject,
        to=a.client_email,
        heading=heading,
        paragraphs=paragraphs,
        callout_label="Amount due",
        callout_value=amount,
        callout_note=(f"Agreement {a.reference}"
                      + (f" · {a.currency} {owing:,.2f} outstanding in total" if owing is not None
                         and owing != req.amount else "")),
        cta_text=f"Pay {amount} securely",
        cta_url=req.pay_url(),
        preheader=f"{amount} is due on agreement {a.reference}.",
    )
    if ok:
        _sms([_client_phone(a)], sms_payment_link(a, req, reminder=reminder), "payment link")
    return ok


def sms_payment_link(a, req, *, reminder=False):
    """Points at the inbox rather than carrying the payment link itself.

    A payment URL arriving cold by text is exactly the shape of the scams
    clients are told to ignore, and the email it follows has the same link
    behind Metascholar's own branding. The text's job is to say the email
    is genuine and worth opening."""
    amount = f"{req.currency} {req.amount:,.2f}"
    lead = "Reminder: payment" if reminder else "Payment"
    return (f"{lead} of {amount} is due on Metascholar agreement {a.reference}. "
            "Check your email for the secure payment link.")


def send_receipt(a, payment, attachment=None):
    """The client's receipt, the moment their payment goes through."""
    owing = a.amount_owing
    settled = owing is not None and owing <= 0
    paragraphs = [
        f"Dear {a.client_name},",
        f"Thank you — we have received {a.currency} {payment.abs_amount:,.2f} against the "
        f"Professional Service Agreement for “{a.service_title or 'your project'}”.",
        ("Your receipt is attached to this email as a PDF." if attachment else
         "Your receipt is available from the link below."),
        ("This settles the agreement in full. Thank you for your business."
         if settled else
         f"The balance still outstanding is {a.currency} {owing:,.2f}." if owing is not None else ""),
    ]
    ok = _send(
        subject=f"Receipt {payment.receipt_number} — {a.currency} {payment.abs_amount:,.2f} received",
        to=a.client_email,
        heading="Payment received — thank you",
        paragraphs=[p for p in paragraphs if p],
        callout_label="Amount received",
        callout_value=f"{a.currency} {payment.abs_amount:,.2f}",
        callout_note=f"Receipt {payment.receipt_number} · Agreement {a.reference}",
        cta_text="View your agreement",
        cta_url=a.client_url(),
        preheader=f"Receipt {payment.receipt_number} for {a.currency} {payment.abs_amount:,.2f}.",
        attachments=[attachment] if attachment else None,
    )
    if ok:
        _sms([_client_phone(a)], sms_receipt(a, payment), "receipt")
    return ok


def sms_receipt(a, payment):
    owing = a.amount_owing
    tail = ("Agreement settled in full. Thank you." if owing is not None and owing <= 0
            else f"Balance now {a.currency} {owing:,.2f}." if owing is not None else "")
    return (f"Metascholar: {a.currency} {payment.abs_amount:,.2f} received for agreement "
            f"{a.reference}. Receipt {payment.receipt_number} emailed to you. {tail}").strip()


def send_payment_to_staff(a, payment, req):
    """Tells the CEO and the preparer that money has landed."""
    owing = a.amount_owing
    ok = _send(
        subject=f"Payment received on PSA {a.reference} — {a.currency} {payment.abs_amount:,.2f}",
        to=_staff_recipients(a),
        heading="A client has paid online",
        paragraphs=[
            f"{a.client_name} has paid {a.currency} {payment.abs_amount:,.2f} against {a.reference} "
            f"({a.service_title}).",
            f"Receipt {payment.receipt_number} · Paystack reference {req.reference}",
            (f"Still outstanding: {a.currency} {owing:,.2f}" if owing is not None and owing > 0
             else "The agreement is now settled in full."),
        ],
        cta_text="Open the agreement",
        cta_url=a.staff_url(),
        preheader=f"{a.client_name} paid {a.currency} {payment.abs_amount:,.2f} on {a.reference}.",
    )
    if ok:
        _sms(_staff_phones(a), sms_payment_to_staff(a, payment), "payment received")
    return ok


def sms_payment_to_staff(a, payment):
    owing = a.amount_owing
    tail = (f"{a.currency} {owing:,.2f} still owing." if owing is not None and owing > 0
            else "Settled in full.")
    return (f"{a.reference}: {_plain(a.client_name, SMS_NAME_LEN)} paid "
            f"{a.currency} {payment.abs_amount:,.2f} online. {tail} {a.staff_url()}")
