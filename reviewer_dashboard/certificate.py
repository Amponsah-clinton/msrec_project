"""Peer Review Certificate for one completed ReviewAssignment.

Two renderings share the wording and signatories defined here:
  * the on-screen, print-ready HTML version (templates/certificates/
    award_certificate.html, via reviewer_dashboard.views.certificate_download)
  * the PDF attached to the award email (render_review_certificate_pdf below,
    called from secretariat_dashboard.views._handle_award_certificate)

The PDF is drawn straight onto a reportlab canvas rather than laid out with
platypus flowables, so it can reproduce the HTML version's fixed A4
composition -- navy ink on white, a teal lattice border, a line-art seal --
instead of reading like a generic generated report.

The design is the "white edition": crisp white paper, deep navy ink and the
MSREC brand teal (in place of the older ivory-and-brass scheme).
"""
import math
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Paragraph


PAPER = colors.HexColor("#ffffff")
INK = colors.HexColor("#14233f")
INK_SOFT = colors.HexColor("#56607a")
BRASS = colors.HexColor("#0f8a86")  # brand teal (name kept: used throughout)
RULE = colors.HexColor("#b7dcda")

LOGO_PATH = Path(__file__).resolve().parent.parent / "static" / "assets" / "img" / "logo1.png"

PAGE_W, PAGE_H = landscape(A4)


def certificate_signatories(assignment=None):
    """The Chair -- the only person named on a certificate (see pages.
    certificate_signatory). Kept under its old name so callers stay simple;
    `assignment` is unused now that the awarding staff member no longer
    appears on the certificate."""
    from pages.certificate_signatory import chair_details

    return chair_details()


def review_certificate_message(assignment):
    ref = assignment.application.reference_no or f"application #{assignment.application_id}"
    return (
        f"completed an independent ethical review for the Metascholar Research Ethics "
        f"Committee under reference {ref}, and is recognised for the rigour, "
        f"impartiality and confidentiality brought to that work."
    )


def _spaced(c, text, x, y, font, size, spacing, color):
    """Centred, letter-spaced caps -- reportlab's drawCentredString has no
    tracking option, so this lays each character out by hand."""
    c.setFont(font, size)
    c.setFillColor(color)
    widths = [c.stringWidth(ch, font, size) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    cursor = x - total / 2
    for ch, w in zip(text, widths):
        c.drawString(cursor, y, ch)
        cursor += w + spacing


def _border(c):
    c.setFillColor(PAPER)
    c.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)

    # Soft brand-teal glow at the top edge and a faint navy one at the foot.
    c.saveState()
    for i in range(24):
        c.setFillColor(BRASS)
        c.setFillAlpha(0.0035 * (24 - i) / 24 * 4)
        c.rect(0, PAGE_H - (i + 1) * 3 * mm, PAGE_W, 3 * mm, stroke=0, fill=1)
    for i in range(16):
        c.setFillColor(INK)
        c.setFillAlpha(0.0025 * (16 - i) / 16 * 4)
        c.rect(0, i * 3 * mm, PAGE_W, 3 * mm, stroke=0, fill=1)
    c.restoreState()

    c.setStrokeColor(INK)
    c.setLineWidth(0.6 * mm * 0.75)
    c.rect(7 * mm, 7 * mm, PAGE_W - 14 * mm, PAGE_H - 14 * mm)

    # Teal lattice band: a row of small diamonds running around the frame.
    c.setStrokeColor(BRASS)
    c.setLineWidth(0.35)
    step, half = 3 * mm, 1.5 * mm
    left, right = 9.5 * mm, PAGE_W - 9.5 * mm
    bottom, top = 9.5 * mm, PAGE_H - 9.5 * mm

    def diamond(cx, cy):
        p = c.beginPath()
        p.moveTo(cx - half, cy)
        p.lineTo(cx, cy + half)
        p.lineTo(cx + half, cy)
        p.lineTo(cx, cy - half)
        p.close()
        c.drawPath(p, stroke=1, fill=0)

    x = left
    while x <= right + 0.01:
        diamond(x, top)
        diamond(x, bottom)
        x += step
    y = bottom + step
    while y < top - 0.01:
        diamond(left, y)
        diamond(right, y)
        y += step

    c.setStrokeColor(INK)
    c.setLineWidth(0.25 * mm * 0.75)
    c.rect(12 * mm, 12 * mm, PAGE_W - 24 * mm, PAGE_H - 24 * mm)

    c.setFillColor(BRASS)
    for cx, cy in [(12, 12), (PAGE_W / mm - 12, 12), (12, PAGE_H / mm - 12), (PAGE_W / mm - 12, PAGE_H / mm - 12)]:
        c.saveState()
        c.translate(cx * mm, cy * mm)
        c.rotate(45)
        c.rect(-1.6 * mm, -1.6 * mm, 3.2 * mm, 3.2 * mm, stroke=0, fill=1)
        c.restoreState()


_LOGO_PNG = None


def _logo_reader():
    """The logo downscaled once per process: the bundled file is ~1 MB at
    1254 px, far more than a 13 mm letterhead needs, and embedding it as-is
    made every emailed certificate over a megabyte."""
    global _LOGO_PNG
    if _LOGO_PNG is None:
        from PIL import Image

        with Image.open(LOGO_PATH) as im:
            im = im.convert("RGBA")
            im.thumbnail((520, 520), Image.LANCZOS)
            buf = BytesIO()
            im.save(buf, format="PNG", optimize=True)
            _LOGO_PNG = buf.getvalue()
    return ImageReader(BytesIO(_LOGO_PNG))


def _logo(c, cx, top, height, alpha=1.0, center_y=None):
    """Draws the bundled MSREC logo, horizontally centred on cx. Silently
    skipped if the file can't be read -- a missing logo must never stop a
    certificate from being issued."""
    try:
        img = _logo_reader()
        iw, ih = img.getSize()
        w = height * iw / ih
        y = (center_y - height / 2) if center_y is not None else (top - height)
        c.saveState()
        c.setFillAlpha(alpha)
        c.drawImage(img, cx - w / 2, y, width=w, height=height, mask="auto")
        c.restoreState()
    except Exception:
        pass


def _seal(c, cx, cy, caption):
    c.setStrokeColor(BRASS)
    for r, w in [(18, 1.1), (16.7, 0.4), (11.3, 0.7), (10.3, 0.35)]:
        c.setLineWidth(w)
        c.circle(cx, cy, r * mm, stroke=1, fill=0)

    ring_text = "METASCHOLAR RESEARCH ETHICS COMMITTEE · "
    font, size = "Times-Roman", 6.3
    radius = 13.9 * mm
    c.setFont(font, size)
    c.setFillColor(BRASS)
    angle_per_char = 360 / len(ring_text)
    for i, ch in enumerate(ring_text):
        angle = 90 - i * angle_per_char
        rad = math.radians(angle)
        c.saveState()
        c.translate(cx + radius * math.cos(rad), cy + radius * math.sin(rad))
        c.rotate(angle - 90)
        c.drawCentredString(0, -size / 3, ch)
        c.restoreState()

    c.setFillColor(INK)
    c.setFont("Times-Bold", 13)
    c.drawCentredString(cx, cy + 0.6 * mm, "MSREC")
    c.setStrokeColor(BRASS)
    c.setLineWidth(0.5)
    c.line(cx - 5 * mm, cy - 1.6 * mm, cx + 5 * mm, cy - 1.6 * mm)
    _spaced(c, caption, cx, cy - 5 * mm, "Times-Roman", 5.2, 0.9, BRASS)


SIG_BOX_W, SIG_BOX_H = 70 * mm, 20 * mm  # the space the certificate allots to the signature


def _signature_image(c, cx, y, png_bytes):
    """Fits the (already cropped, background-free) signature into the
    allotted box by aspect ratio, centred, resting just above the line."""
    try:
        img = ImageReader(BytesIO(png_bytes))
        iw, ih = img.getSize()
        scale = min(SIG_BOX_W / iw, SIG_BOX_H / ih)
        w, h = iw * scale, ih * scale
        c.drawImage(img, cx - w / 2, y + 1 * mm, width=w, height=h, mask="auto")
    except Exception:
        pass  # an unreadable image must never stop a certificate being issued


def _chair_block(c, cx, y, details, signature_png):
    """Signature above the line; the Chair's name and title beneath it."""
    if signature_png:
        _signature_image(c, cx, y, signature_png)
    c.setStrokeColor(INK)
    c.setLineWidth(0.5)
    c.line(cx - 35 * mm, y, cx + 35 * mm, y)
    c.setFillColor(INK)
    c.setFont("Times-Bold", 13)
    if details["name"]:
        c.drawCentredString(cx, y - 6 * mm, details["name"])
    _spaced(c, details["title"].upper(), cx, y - 11 * mm, "Times-Roman", 8.5, 1.2, INK_SOFT)


def _date_block(c, cx, y, issued_at):
    """The date where the Chair's name sits and the caption where the title
    sits, so both sides align -- but no rule above it: only the Chair signs,
    and a line here would read as a second signature space."""
    c.setFillColor(INK)
    c.setFont("Times-Bold", 13)
    if issued_at:
        c.drawCentredString(cx, y - 6 * mm, issued_at.strftime("%d %B %Y").lstrip("0"))
    _spaced(c, "DATE OF ISSUE", cx, y - 11 * mm, "Times-Roman", 8.5, 1.2, INK_SOFT)


def render_review_certificate_pdf(assignment):
    """Returns the PDF as raw bytes. Only call for an assignment that has
    already been issued a certificate_id."""
    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"MSREC Certificate of Peer Review - {assignment.certificate_id}")

    _border(c)
    mid = PAGE_W / 2

    # Faint watermark behind the wording, then the letterhead logo.
    _logo(c, mid, 0, 110 * mm, alpha=0.045, center_y=PAGE_H * 0.47)
    _logo(c, mid, PAGE_H - 17 * mm, 13 * mm)

    _spaced(c, "METASCHOLAR RESEARCH ETHICS COMMITTEE", mid, PAGE_H - 37 * mm, "Times-Roman", 10, 2.4, BRASS)
    c.setStrokeColor(RULE)
    c.setLineWidth(0.6)
    c.line(mid - 22 * mm, PAGE_H - 41.5 * mm, mid - 4 * mm, PAGE_H - 41.5 * mm)
    c.line(mid + 4 * mm, PAGE_H - 41.5 * mm, mid + 22 * mm, PAGE_H - 41.5 * mm)
    c.saveState()
    c.translate(mid, PAGE_H - 41.5 * mm)
    c.rotate(45)
    c.setFillColor(BRASS)
    c.rect(-0.9 * mm, -0.9 * mm, 1.8 * mm, 1.8 * mm, stroke=0, fill=1)
    c.restoreState()

    title_y = PAGE_H - 60 * mm
    lead, tail = "Certificate ", "of Peer Review"
    lead_w = c.stringWidth(lead, "Times-Roman", 40)
    tail_w = c.stringWidth(tail, "Times-Italic", 40)
    start = mid - (lead_w + tail_w) / 2
    c.setFont("Times-Roman", 40)
    c.setFillColor(INK)
    c.drawString(start, title_y, lead)
    c.setFont("Times-Italic", 40)
    c.setFillColor(BRASS)
    c.drawString(start + lead_w, title_y, tail)

    c.setFont("Times-Italic", 14)
    c.setFillColor(INK_SOFT)
    c.drawCentredString(mid, title_y - 22 * mm, "This is to certify that")

    name = assignment.reviewer.full_name
    name_y = title_y - 36 * mm
    name_size = 34
    while name_size > 20 and c.stringWidth(name, "Times-Bold", name_size) > 200 * mm:
        name_size -= 1
    c.setFont("Times-Bold", name_size)
    c.setFillColor(INK)
    c.drawCentredString(mid, name_y, name)
    name_w = max(c.stringWidth(name, "Times-Bold", name_size), 90 * mm)
    # Underline fades out at both ends (stepped, since PDF lines are flat).
    span = name_w + 12 * mm
    left = mid - span / 2
    steps = 40
    c.setStrokeColor(BRASS)
    c.setLineWidth(0.9)
    for i in range(steps):
        t = (i + 0.5) / steps
        c.setStrokeAlpha(min(1.0, min(t, 1 - t) * 5))
        c.line(left + span * i / steps, name_y - 4 * mm, left + span * (i + 1) / steps, name_y - 4 * mm)
    c.setStrokeAlpha(1.0)

    body = Paragraph(
        review_certificate_message(assignment),
        ParagraphStyle("body", fontName="Times-Roman", fontSize=14, leading=21,
                       textColor=INK_SOFT, alignment=TA_CENTER),
    )
    body_w = 185 * mm
    _, body_h = body.wrap(body_w, 40 * mm)
    body.drawOn(c, mid - body_w / 2, name_y - 12 * mm - body_h)

    from pages.certificate_signatory import chair_signature_bytes

    chair = certificate_signatories(assignment)
    sign_y = 46 * mm
    _date_block(c, mid - 82 * mm, sign_y, assignment.certificate_awarded_at)
    _chair_block(c, mid + 82 * mm, sign_y, chair, chair_signature_bytes(chair))
    _seal(c, mid, sign_y + 6 * mm, "PEER REVIEW")

    footer = f"CERTIFICATE NO. {assignment.certificate_id}"
    _spaced(c, footer, mid, 24 * mm, "Times-Roman", 8.5, 1.0, INK_SOFT)

    c.showPage()
    c.save()
    return buffer.getvalue()
