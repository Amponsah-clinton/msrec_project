"""Workshop certificate PDF.

Same MSREC "white edition" look as the Peer Review / Committee certificates
(it reuses their exact border, seal, logo letterhead, title and typography
from reviewer_dashboard.certificate) -- but a workshop certificate carries
TWO signatures instead of the single Chair + date block. The wording and the
two signatories are admin-editable on WorkshopCertificateTemplate; signatory
1 falls back to the Chair (Site Settings -> Certificates) when left blank, so
it stays consistent with every other MSREC certificate.
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


def _signatory_block(c, cx, y, name, title, signature_png):
    """One signature column: signature above the line, name + title beneath."""
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


def _two_signatories(tpl):
    """[(name, title, png|None), (name, title, png|None)] -- the two people
    who sign. Slot 1 falls back to the Chair when no name is set."""
    from . import storage

    def png(path):
        return storage.download_object(path) if path else None

    s1_name = (tpl.signatory1_name or "").strip()
    if s1_name:
        sig1 = (s1_name, (tpl.signatory1_title or "").strip(), png(tpl.signatory1_signature_path))
    else:
        from pages.certificate_signatory import chair_details, chair_signature_bytes
        ch = chair_details()
        sig1 = (ch["name"], ch["title"], chair_signature_bytes(ch))

    sig2 = (
        (tpl.signatory2_name or "").strip(),
        (tpl.signatory2_title or "").strip() or "Workshop Coordinator",
        png(tpl.signatory2_signature_path),
    )
    return sig1, sig2


def render_workshop_certificate_pdf(registration, *, tpl=None, ws=None):
    """Certificate PDF bytes for one registration (two signatures).

    `tpl`/`ws` let the admin preview an *unsaved* design: the editor passes a
    transient WorkshopCertificateTemplate built from the posted fields. When
    omitted, the saved singletons are used (the real issued certificate).
    """
    from .models import WorkshopCertificateTemplate, WorkshopSettings

    tpl = tpl or WorkshopCertificateTemplate.get_solo()
    ws = ws or WorkshopSettings.get_solo()

    cert_id = registration.ensure_certificate_ref()
    issued_at = registration.paid_at or registration.created_at
    message = (tpl.body or "").replace("{workshop}", ws.workshop_title).replace("{name}", registration.name)

    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"{tpl.title or 'Certificate'} {tpl.title_tail} - {cert_id}")

    _border(c)
    mid = PAGE_W / 2
    draw_header(c)

    title_y = PAGE_H - 60 * mm
    draw_title(c, title_y, tpl.title or "Certificate", tpl.title_tail or "")

    c.setFont("Times-Italic", 14)
    c.setFillColor(INK_SOFT)
    c.drawCentredString(mid, title_y - 22 * mm, (tpl.intro or "This is to certify that"))

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

    # Two signatures: left and right, with the seal between them.
    sign_y = 46 * mm
    (s1_name, s1_title, s1_png), (s2_name, s2_title, s2_png) = _two_signatories(tpl)
    _signatory_block(c, mid - 82 * mm, sign_y, s1_name, s1_title, s1_png)
    _signatory_block(c, mid + 82 * mm, sign_y, s2_name, s2_title, s2_png)
    _seal(c, mid, sign_y + 6 * mm, tpl.seal_caption or "WORKSHOP")

    _spaced(c, f"CERTIFICATE NO. {cert_id}", mid, 24 * mm, "Times-Roman", 8.5, 1.0, INK_SOFT)

    c.showPage()
    c.save()
    return buffer.getvalue()


def _watermark_overlay_bytes(text="SPECIMEN · NOT A VALID CERTIFICATE"):
    """A landscape-A4 overlay PDF: the watermark text tiled diagonally in
    faint red across the whole page, stamped over the sample certificate so
    the preview can never pass as a real one."""
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


def render_sample_certificate_pdf(sample_name="Your Name Here"):
    """A watermarked sample of the certificate for the public /workshop
    preview -- same design as the real one, but stamped SPECIMEN so it is
    visibly unusable. Never issued; only ever shown in the preview modal."""
    from django.utils import timezone
    from pypdf import PdfReader, PdfWriter

    from .models import WorkshopRegistration

    sample = WorkshopRegistration(
        name=(sample_name or "Your Name Here").strip()[:80] or "Your Name Here",
        institution="Sample Institution", email="sample@example.com",
        wants_certificate=True, payment_status=WorkshopRegistration.PaymentStatus.SUCCESS,
    )
    sample.paid_at = timezone.now()
    sample.pk = 0

    base = render_workshop_certificate_pdf(sample)
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
