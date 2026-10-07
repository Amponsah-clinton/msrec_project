"""Workshop certificate PDF.

Same MSREC "white edition" look as the Peer Review / Committee certificates
(it reuses their exact border, seal, logo letterhead, title and typography
from reviewer_dashboard.certificate). A workshop certificate can carry TWO
signatures, and each workshop sets its own wording, signatories and which
elements (body, seal, second signature, verification footer) appear --
Signature 1 falls back to the Chair (Site Settings -> Certificates) when left
blank, keeping it consistent with every other MSREC certificate.
"""
from io import BytesIO

from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph

from reviewer_dashboard.certificate import (
    BRASS, INK, INK_SOFT, PAGE_H, PAGE_W,
    _border, _seal, _signature_image, _spaced, draw_header, draw_title,
)


def _sig_block(c, cx, y, name, title, signature_png):
    if signature_png:
        _signature_image(c, cx, y, signature_png)
    c.setStrokeColor(INK)
    c.setLineWidth(0.5)
    c.line(cx - 35 * mm, y, cx + 35 * mm, y)
    c.setFillColor(INK)
    c.setFont("Times-Bold", 13)
    if name:
        c.drawCentredString(cx, y - 6 * mm, name)
    if title:
        _spaced(c, title.upper(), cx, y - 11 * mm, "Times-Roman", 8.5, 1.2, INK_SOFT)


def _date_block(c, cx, y, issued_at):
    c.setFillColor(INK)
    c.setFont("Times-Bold", 13)
    if issued_at:
        c.drawCentredString(cx, y - 6 * mm, issued_at.strftime("%d %B %Y").lstrip("0"))
    _spaced(c, "DATE OF ISSUE", cx, y - 11 * mm, "Times-Roman", 8.5, 1.2, INK_SOFT)


def _signatories(workshop):
    """(sig1, sig2) each (name, title, png|None). Slot 1 falls back to the
    Chair when no name is set."""
    from . import storage

    def png(path):
        return storage.download_object(path) if path else None

    s1_name = (workshop.cert_sig1_name or "").strip()
    if s1_name:
        sig1 = (s1_name, (workshop.cert_sig1_title or "").strip(), png(workshop.cert_sig1_signature_path))
    else:
        from pages.certificate_signatory import chair_details, chair_signature_bytes
        ch = chair_details()
        sig1 = (ch["name"], ch["title"], chair_signature_bytes(ch))

    sig2 = (
        (workshop.cert_sig2_name or "").strip(),
        (workshop.cert_sig2_title or "").strip() or "Workshop Coordinator",
        png(workshop.cert_sig2_signature_path),
    )
    return sig1, sig2


def render_workshop_certificate_pdf(registration, *, workshop=None):
    """Certificate PDF bytes for one registration, using its workshop's design.

    `workshop` lets the admin preview an *unsaved* design (a transient
    Workshop built from the posted fields). When omitted, the registration's
    saved workshop is used.
    """
    workshop = workshop or registration.workshop

    cert_id = registration.ensure_certificate_ref()
    issued_at = registration.paid_at or registration.created_at
    message = (workshop.cert_body or "").replace("{workshop}", workshop.title).replace("{name}", registration.name)

    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"Certificate {workshop.cert_title_tail} - {cert_id}")

    _border(c)
    mid = PAGE_W / 2
    draw_header(c)

    title_y = PAGE_H - 60 * mm
    draw_title(c, title_y, "Certificate", workshop.cert_title_tail or "")

    c.setFont("Times-Italic", 14)
    c.setFillColor(INK_SOFT)
    c.drawCentredString(mid, title_y - 22 * mm, (workshop.cert_intro or "This is to certify that"))

    name = registration.name
    name_y = title_y - 36 * mm
    name_size = 34
    while name_size > 20 and c.stringWidth(name, "Times-Bold", name_size) > 200 * mm:
        name_size -= 1
    c.setFont("Times-Bold", name_size)
    c.setFillColor(INK)
    c.drawCentredString(mid, name_y, name)

    name_w = max(c.stringWidth(name, "Times-Bold", name_size), 90 * mm)
    span = name_w + 12 * mm
    left = mid - span / 2
    c.setStrokeColor(BRASS)
    c.setLineWidth(0.9)
    for i in range(40):
        t = (i + 0.5) / 40
        c.setStrokeAlpha(min(1.0, min(t, 1 - t) * 5))
        c.line(left + span * i / 40, name_y - 4 * mm, left + span * (i + 1) / 40, name_y - 4 * mm)
    c.setStrokeAlpha(1.0)

    if workshop.cert_show_body and message.strip():
        body = Paragraph(
            message,
            ParagraphStyle("body", fontName="Times-Roman", fontSize=14, leading=21,
                           textColor=INK_SOFT, alignment=TA_CENTER),
        )
        body_w = 185 * mm
        _, body_h = body.wrap(body_w, 45 * mm)
        body.drawOn(c, mid - body_w / 2, name_y - 12 * mm - body_h)

    sign_y = 46 * mm
    (s1_name, s1_title, s1_png), (s2_name, s2_title, s2_png) = _signatories(workshop)
    if workshop.cert_show_second_signature:
        _sig_block(c, mid - 82 * mm, sign_y, s1_name, s1_title, s1_png)
        _sig_block(c, mid + 82 * mm, sign_y, s2_name, s2_title, s2_png)
    else:
        _date_block(c, mid - 82 * mm, sign_y, issued_at)
        _sig_block(c, mid + 82 * mm, sign_y, s1_name, s1_title, s1_png)

    if workshop.cert_show_seal:
        _seal(c, mid, sign_y + 6 * mm, workshop.cert_seal_caption or "WORKSHOP")

    if workshop.cert_show_verification:
        _spaced(c, f"CERTIFICATE NO. {cert_id}", mid, 24 * mm, "Times-Roman", 8.5, 1.0, INK_SOFT)

    c.showPage()
    c.save()
    return buffer.getvalue()


def _watermark_overlay_bytes(text="SPECIMEN · NOT A VALID CERTIFICATE"):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape

    W, H = landscape(A4)
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(W, H))
    c.saveState()
    c.translate(W / 2, H / 2)
    c.rotate(30)
    c.setFillColor(colors.HexColor("#c0392b"))
    c.setFillAlpha(0.16)
    c.setFont("Helvetica-Bold", 30)
    for row in range(-5, 6):
        c.drawCentredString(0, row * 46, text)
    c.restoreState()
    c.showPage()
    c.save()
    return buf.getvalue()


def render_sample_certificate_pdf(workshop, sample_name="Your Name Here"):
    """Watermarked sample of a workshop's certificate for the public preview."""
    from django.utils import timezone
    from pypdf import PdfReader, PdfWriter

    from .models import WorkshopRegistration

    sample = WorkshopRegistration(
        workshop=workshop,
        name=(sample_name or "Your Name Here").strip()[:80] or "Your Name Here",
        institution="Sample Institution", email="sample@example.com",
        wants_certificate=True, payment_status=WorkshopRegistration.PaymentStatus.SUCCESS,
    )
    sample.paid_at = timezone.now()
    sample.pk = 0

    base = render_workshop_certificate_pdf(sample, workshop=workshop)
    overlay = _watermark_overlay_bytes()

    base_reader = PdfReader(BytesIO(base))
    wm_page = PdfReader(BytesIO(overlay)).pages[0]
    writer = PdfWriter()
    for page in base_reader.pages:
        page.merge_page(wm_page)
        writer.add_page(page)
    out = BytesIO()
    writer.write(out)
    return out.getvalue()
