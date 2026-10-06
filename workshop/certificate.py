"""Workshop certificate PDF -- the same MSREC "white edition" look as the
Peer Review / Hall of Fame certificates (reviewer_dashboard.certificate),
but with the title, wording, seal caption and up to two signatories all
driven by WorkshopCertificateTemplate (admin-editable).
"""
from io import BytesIO

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph

from reviewer_dashboard.certificate import (
    BRASS, INK, INK_SOFT, PAGE_H, PAGE_W,
    _border, _seal, _signature_image, _spaced, draw_header, draw_title,
)


def _signatory_block(c, cx, y, name, title, signature_png):
    """Signature above the line; name and title beneath -- one column."""
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


def render_workshop_certificate_pdf(registration):
    """Returns the certificate PDF bytes for one paid registration."""
    from .models import WorkshopCertificateTemplate, WorkshopSettings

    tpl = WorkshopCertificateTemplate.get_solo()
    ws = WorkshopSettings.get_solo()
    from . import storage

    cert_id = registration.ensure_certificate_ref()
    issued_at = registration.paid_at or registration.created_at

    message = (tpl.body or "").replace("{workshop}", ws.workshop_title).replace(
        "{name}", registration.name
    )

    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"{tpl.title} {tpl.title_tail} - {cert_id}")

    _border(c)
    mid = PAGE_W / 2
    draw_header(c)

    title_y = PAGE_H - 60 * mm
    # draw_title always leads with the configured word ("Certificate" etc.)
    c.setFont("Times-Roman", 1)  # no-op to ensure font registered
    draw_title(c, title_y, tpl.title or "Certificate", tpl.title_tail or "")

    c.setFont("Times-Italic", 14)
    c.setFillColor(INK_SOFT)
    c.drawCentredString(mid, title_y - 22 * mm, tpl.intro or "This is to certify that")

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

    body = Paragraph(
        message,
        ParagraphStyle("body", fontName="Times-Roman", fontSize=14, leading=21,
                       textColor=INK_SOFT, alignment=TA_CENTER),
    )
    body_w = 185 * mm
    _, body_h = body.wrap(body_w, 45 * mm)
    body.drawOn(c, mid - body_w / 2, name_y - 12 * mm - body_h)

    sign_y = 46 * mm
    s1_name, s1_title = tpl.signatory1_name.strip(), tpl.signatory1_title.strip()
    s2_name, s2_title = tpl.signatory2_name.strip(), tpl.signatory2_title.strip()
    s1_png = storage.download_object(tpl.signatory1_signature_path) if tpl.signatory1_signature_path else None
    s2_png = storage.download_object(tpl.signatory2_signature_path) if tpl.signatory2_signature_path else None

    if s2_name or s2_title:
        # Two signatories, left and right.
        _signatory_block(c, mid - 82 * mm, sign_y, s1_name, s1_title, s1_png)
        _signatory_block(c, mid + 82 * mm, sign_y, s2_name, s2_title, s2_png)
    else:
        # One signatory on the right, the issue date on the left.
        _date_block(c, mid - 82 * mm, sign_y, issued_at)
        _signatory_block(c, mid + 82 * mm, sign_y, s1_name, s1_title, s1_png)

    _seal(c, mid, sign_y + 6 * mm, tpl.seal_caption or "WORKSHOP")

    _spaced(c, f"CERTIFICATE NO. {cert_id}", mid, 24 * mm, "Times-Roman", 8.5, 1.0, INK_SOFT)

    c.showPage()
    c.save()
    return buffer.getvalue()
