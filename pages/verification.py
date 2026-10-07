"""Public verification of MSREC ethics approvals (the /verify/ page).

An approval is a genuine, decided `Application` with status APPROVED. It is
identified by its reference number (Application.reference_no, e.g.
MSREC/2026/0042) or by a verification code printed on the approval letter /
certificate beside a QR code that links back to /verify/?ref=<number>.

The verification code is not stored: it is an HMAC of the reference number
under SECRET_KEY (verification_code()), so it can be regenerated for any
approved application, cannot be guessed from the sequential reference
number, and needs no migration or backfill. Changing SECRET_KEY changes
every code, so codes already printed on letters would stop matching.

Only approved applications are ever returned. Drafts, applications under
review, and refused ones look exactly like "no such approval", so this
public endpoint never confirms that an unapproved application exists.
"""

import base64
import hashlib
import hmac
import re

from django.conf import settings
from django.utils import timezone

from payments import fees

CODE_PREFIX = "VER"
_CODE_LEN = 8
_REF_RE = re.compile(r"MSREC\D*(\d{4})\D*(\d{1,6})\s*$", re.IGNORECASE)
# Workshop certificate ids look like MSREC/WS/CERT/2026/0001 -- matched before
# the generic approval reference above so the "WS/CERT" part isn't stripped.
_WS_REF_RE = re.compile(r"MSREC\W*WS\W*CERT\W*(\d{4})\W*(\d{1,6})\s*$", re.IGNORECASE)


def verification_code(reference_no):
    """VER-XXXX-XXXX for a reference number (base32, 40 bits)."""
    digest = hmac.new(
        settings.SECRET_KEY.encode(), f"msrec-verify:{reference_no}".encode(), hashlib.sha256
    ).digest()
    body = base64.b32encode(digest)[:_CODE_LEN].decode()
    return f"{CODE_PREFIX}-{body[:4]}-{body[4:]}"


def normalize_reference(raw):
    """'msrec 2026 42' / 'MSREC20260042' / 'MSREC/2026/0042' -> 'MSREC/2026/0042',
    or None when it doesn't look like a reference number."""
    match = _REF_RE.match((raw or "").strip())
    if not match:
        return None
    return f"MSREC/{match.group(1)}/{int(match.group(2)):04d}"


def normalize_workshop_ref(raw):
    """'MSREC/WS/CERT/2026/1' / 'MSREC WS CERT 2026 0001' -> 'MSREC/WS/CERT/2026/0001',
    or None when it isn't a workshop certificate id."""
    match = _WS_REF_RE.match((raw or "").strip())
    if not match:
        return None
    return f"MSREC/WS/CERT/{match.group(1)}/{int(match.group(2)):04d}"


def _normalize_code(raw):
    """'ver-abcd-2345' / 'VER ABCD 2345' / 'VERABCD2345' -> 'VER-ABCD-2345', or None."""
    compact = re.sub(r"[^A-Z0-9]", "", (raw or "").upper())
    if not compact.startswith(CODE_PREFIX) or len(compact) != len(CODE_PREFIX) + _CODE_LEN:
        return None
    body = compact[len(CODE_PREFIX):]
    return f"{CODE_PREFIX}-{body[:4]}-{body[4:]}"


def extract_query(raw):
    """A scanned QR may carry the full verify URL (…/verify/?ref=MSREC/2026/0042
    or ?code=VER-…); pull the reference or code out of it, else use the text as is."""
    from urllib.parse import parse_qs, urlparse

    text = (raw or "").strip()
    if "://" in text:
        params = parse_qs(urlparse(text).query)
        for key in ("ref", "code"):
            if params.get(key):
                return params[key][0].strip()
    return text


def _date(value):
    return f"{value.day} {value:%b %Y}" if value else ""


def _result(application):
    expires = application.approval_expires_at
    expired = bool(expires and timezone.now() > expires)
    applicant = application.applicant
    return {
        "found": True,
        "status": "expired" if expired else "approved",
        "number": application.reference_no,
        "code": verification_code(application.reference_no),
        "title": application.title,
        "pi": applicant.full_name,
        "institution": getattr(applicant, "institution", "") or "",
        "reviewType": fees.label_for(application.review_type),
        "approvedOn": _date(application.decided_at),
        "expiresOn": _date(expires),
    }


def _workshop_result(reg):
    return {
        "found": True,
        "kind": "workshop_certificate",
        "status": "valid",
        "number": reg.certificate_ref,
        "code": verification_code(reg.certificate_ref),
        "recipient": reg.name,
        "institution": reg.institution or "",
        "workshop": reg.workshop.title if reg.workshop_id else "",
        "issuedOn": _date(reg.paid_at or reg.created_at),
    }


def _paid_workshop_certs():
    """Paid workshop registrations that have been issued a certificate id --
    the only ones that verify (an unpaid registration has no certificate)."""
    from workshop.models import WorkshopRegistration

    return WorkshopRegistration.objects.filter(
        payment_status=WorkshopRegistration.PaymentStatus.SUCCESS,
    ).exclude(certificate_ref="")


def lookup(raw):
    """Returns the public result dict for an approval number, a workshop
    certificate id, or a verification code (any of them), or
    {"found": False, ...} for a miss. Returns None for blank input."""
    from applicant_dashboard.models import Application

    query = extract_query(raw)
    if not query:
        return None

    # Workshop certificate id (distinct namespace -- check before the generic
    # approval reference, whose looser regex would otherwise swallow it).
    ws_ref = normalize_workshop_ref(query)
    if ws_ref:
        reg = _paid_workshop_certs().filter(certificate_ref=ws_ref).first()
        return _workshop_result(reg) if reg else {"found": False, "query": query[:80]}

    approved = Application.objects.filter(
        status=Application.Status.APPROVED, reference_no__isnull=False
    ).select_related("applicant")

    reference = normalize_reference(query)
    if reference:
        application = approved.filter(reference_no=reference).first()
        if application is not None:
            return _result(application)
        return {"found": False, "query": query[:80]}

    code = _normalize_code(query)
    if code:
        # A verification code could belong to an approval or a workshop
        # certificate -- check approvals first, then workshop certificates.
        for candidate in approved:
            if hmac.compare_digest(verification_code(candidate.reference_no), code):
                return _result(candidate)
        for reg in _paid_workshop_certs():
            if hmac.compare_digest(verification_code(reg.certificate_ref), code):
                return _workshop_result(reg)

    return {"found": False, "query": query[:80]}


def verify_url(request, reference_no):
    from django.urls import reverse
    from urllib.parse import quote

    return request.build_absolute_uri(reverse("pages:verify")) + f"?ref={quote(reference_no, safe='/')}"


def qr_svg_data_uri(text, size=132):
    """A QR code for `text` as an inline data: URI (rendered server-side with
    reportlab, so letters print reliably with no CDN/JS dependency)."""
    from urllib.parse import quote

    from reportlab.graphics import renderSVG
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing

    widget = qr.QrCodeWidget(text, barLevel="M")
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    svg = renderSVG.drawToString(drawing)
    return "data:image/svg+xml;utf8," + quote(svg)
