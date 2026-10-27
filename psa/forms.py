"""Reading and checking the two PSA forms: the staff form that prepares an
agreement, and the client's completion form. Plain functions over
request.POST, like the rest of the project's hand-built forms, because both
pages are laid out as the agreement itself rather than as a field list.
"""
import base64
import binascii
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import CURRENCIES, ChangeRequest, ServiceAgreement

MAX_DELIVERABLES = 30
MAX_SIGNATURE_UPLOAD = 2 * 1024 * 1024  # the drawn PNG, before cropping
MAX_FEE = Decimal("999999999999.99")

Basis = ServiceAgreement.Basis
Kind = ServiceAgreement.SignatureKind


def _date(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return False


def _money(value):
    value = (value or "").replace(",", "").strip()
    if not value:
        return None
    try:
        amount = Decimal(value).quantize(Decimal("0.01"))
    except InvalidOperation:
        return False
    if amount < 0 or amount > MAX_FEE:
        return False
    return amount


def phone_ok(phone):
    return 7 <= sum(c.isdigit() for c in phone) <= 15


def email_ok(email):
    try:
        validate_email(email)
    except ValidationError:
        return False
    return True


def deliverables_from(post):
    """Rows are added in the browser as the last one is typed into, so
    blank rows are expected and simply dropped."""
    rows = [" ".join(d.split())[:500] for d in post.getlist("deliverables")]
    return [d for d in rows if d][:MAX_DELIVERABLES]


def parse_agreement(post, *, sending):
    """The staff form. A draft only needs a client name, so work can be
    saved part-way; sending needs everything the client will be asked to
    accept. Returns (cleaned, errors) -- cleaned always holds what was
    typed, so the form can be shown again with it."""
    errors = {}
    c = {
        "client_name": " ".join(post.get("client_name", "").split())[:200],
        "client_email": post.get("client_email", "").strip().lower()[:254],
        "client_phone": post.get("client_phone", "").strip()[:40],
        "client_address": post.get("client_address", "").strip()[:255],
        "service_title": " ".join(post.get("service_title", "").split())[:255],
        "deliverables": deliverables_from(post),
        "currency": post.get("currency", "GHS"),
        "payment_basis": post.get("payment_basis", ""),
        "payment_basis_other": post.get("payment_basis_other", "").strip()[:120],
        "payment_schedule": post.get("payment_schedule", "").strip()[:2000],
    }

    if not c["client_name"]:
        errors["client_name"] = "Enter the client's full name."

    if c["client_email"] and not email_ok(c["client_email"]):
        errors["client_email"] = "Enter a valid email address."
    elif sending and not c["client_email"]:
        errors["client_email"] = "The client's email is needed to send the agreement."

    if c["client_phone"] and not phone_ok(c["client_phone"]):
        errors["client_phone"] = "Enter a valid phone number (7–15 digits)."

    for field, label in (("agreement_date", "agreement date"), ("start_date", "start date"),
                         ("completion_date", "expected completion date")):
        value = _date(post.get(field))
        if value is False:
            errors[field] = f"Enter a valid {label}."
            value = None
        elif value is None and sending:
            errors[field] = f"Enter the {label}."
        c[field] = value
    if c["start_date"] and c["completion_date"] and c["completion_date"] < c["start_date"]:
        errors["completion_date"] = "The completion date can't be before the start date."

    if sending and not c["service_title"]:
        errors["service_title"] = "Give the service or project a title."
    if sending and not c["deliverables"]:
        errors["deliverables"] = "List at least one deliverable."

    if c["currency"] not in dict(CURRENCIES):
        c["currency"] = "GHS"

    c["fee"] = _money(post.get("fee"))
    if c["fee"] is False:
        errors["fee"] = "Enter the fee as a number, e.g. 2500.00."
        c["fee"] = None
    elif sending and not c["fee"]:
        errors["fee"] = "Enter the agreed fee."

    deposit = _money(post.get("deposit"))
    if deposit is False:
        errors["deposit"] = "Enter the deposit as a number, or leave it blank."
        deposit = None
    c["deposit"] = deposit or Decimal("0.00")
    if c["fee"] and c["deposit"] > c["fee"]:
        errors["deposit"] = "The deposit can't be more than the agreed fee."

    if c["payment_basis"] not in Basis.values:
        if c["payment_basis"] or sending:
            errors["payment_basis"] = "Choose how the fee is charged."
        c["payment_basis"] = ""
    if c["payment_basis"] == Basis.OTHER and not c["payment_basis_other"]:
        errors["payment_basis_other"] = "Say how the fee is charged."
    if c["payment_basis"] != Basis.OTHER:
        c["payment_basis_other"] = ""

    if sending and not c["payment_schedule"]:
        errors["payment_schedule"] = "Give the payment due date or schedule."

    return c, errors


def parse_signature(post, prefix):
    """One signature block (assets/js/signature-pad.js). Returns
    (kind, value, error): a typed name, or a drawn signature as a cropped
    PNG data: URL. (None, None, None) when nothing was given."""
    kind = post.get(f"{prefix}_signature_kind", "")
    if kind == Kind.TYPED:
        name = " ".join(post.get(f"{prefix}_signature_typed", "").split())
        if not name:
            return None, None, None
        if len(name) < 2 or len(name) > 120:
            return None, None, "Type your full name to sign."
        return Kind.TYPED, name, None

    if kind == Kind.DRAWN:
        raw = post.get(f"{prefix}_signature_drawn", "")
        if not raw:
            return None, None, None
        head, _, body = raw.partition(",")
        if head != "data:image/png;base64" or len(body) > MAX_SIGNATURE_UPLOAD * 4 // 3:
            return None, None, "That signature couldn't be read. Please clear it and sign again."
        try:
            png = base64.b64decode(body, validate=True)
        except (binascii.Error, ValueError):
            return None, None, "That signature couldn't be read. Please clear it and sign again."

        from pages.signature import process_signature
        try:
            cleaned = process_signature(png)
        except ValueError:
            return None, None, "The signature is empty. Please sign in the box."
        return Kind.DRAWN, "data:image/png;base64," + base64.b64encode(cleaned).decode(), None

    return None, None, None


def parse_client(post):
    """The client's part. Three things are compulsory: their full name,
    their phone number and their signature -- signing is the acceptance
    (Section 5 of the agreement). The address is optional. The email isn't
    theirs to change here: it's where the agreement was sent and where the
    signed copy goes."""
    errors = {}
    c = {
        "client_name": " ".join(post.get("client_name", "").split())[:200],
        "client_phone": post.get("client_phone", "").strip()[:40],
        "client_address": post.get("client_address", "").strip()[:255],
    }
    if not c["client_name"]:
        errors["client_name"] = "Enter your full name."
    if not c["client_phone"]:
        errors["client_phone"] = "Enter your phone number."
    elif not phone_ok(c["client_phone"]):
        errors["client_phone"] = "Enter a valid phone number (7–15 digits)."

    kind, value, sig_error = parse_signature(post, "client")
    if sig_error:
        errors["client_signature"] = sig_error
    elif not value:
        errors["client_signature"] = "Sign the agreement by drawing your signature or typing your name."
    c["client_signature_kind"], c["client_signature"] = kind or "", value or ""
    return c, errors


CHANGE_MESSAGE_MIN, CHANGE_MESSAGE_MAX = 10, 2000


def parse_change_request(post):
    """The client flagging something to fix instead of signing: which part,
    and what's wrong with it."""
    errors = {}
    section = post.get("section", "")
    if section not in ChangeRequest.Section.values:
        section = ChangeRequest.Section.OTHER
    message = post.get("message", "").strip()
    if len(message) < CHANGE_MESSAGE_MIN:
        errors["message"] = "Tell us what needs to change (at least a few words)."
    elif len(message) > CHANGE_MESSAGE_MAX:
        errors["message"] = f"Please keep it under {CHANGE_MESSAGE_MAX} characters."
    return {"section": section, "message": message[:CHANGE_MESSAGE_MAX]}, errors
