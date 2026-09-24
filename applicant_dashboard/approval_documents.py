"""What an applicant receives when their study is approved.

  * the approval email (sent by send_approval_email, called from
    oversight.send_decision_email for both Secretariat and Admin approvals)
  * the approval letter -- A4 portrait PDF on MSREC letterhead
  * the certificate of ethical clearance -- A4 landscape PDF, same frame,
    seal and Chair signature as MSREC's other certificates

All wording comes from pages.models.ApprovalDocumentTemplate (Site Settings >
Approval Documents), with {placeholders} filled from the application. The
PDFs are rendered on demand, never stored, so an edited template or a new
Chair signature applies to every later download as well as new emails.
"""
import logging
import re
from datetime import timedelta
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import quote, urlparse

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, KeepTogether, ListFlowable, ListItem, NextPageTemplate,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from payments import fees

logger = logging.getLogger(__name__)

COMMITTEE_NAME = "Metascholar Research Ethics Committee"

# Shown as click-to-insert chips on the settings page, in this order.
PLACEHOLDERS = [
    ("applicant_name", "Principal investigator, with title"),
    ("study_title", "Title of the study"),
    ("reference_no", "Approval reference, e.g. MSREC/2026/0042"),
    ("review_pathway", "Exemption, Expedited or Full Committee Review"),
    ("approval_date", "Date the study was approved"),
    ("valid_until", "Date the approval expires"),
    ("investigator", "Investigator's name and institution"),
    ("institution", "Investigator's institution"),
    ("committee_name", "Metascholar Research Ethics Committee"),
    ("chair_name", "Chair's name"),
    ("chair_title", "Chair's title"),
    ("verification_code", "Code to verify the approval online"),
    ("today", "Today's date"),
]
PLACEHOLDER_KEYS = {key for key, _ in PLACEHOLDERS}
_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")

INK = colors.HexColor("#14233f")
INK_SOFT = colors.HexColor("#56607a")
TEAL = colors.HexColor("#0f8a86")
HAIR = colors.HexColor("#d9dee6")
TINT = colors.HexColor("#f5f8f9")


# ---------------------------------------------------------------------------
# Values and placeholders
# ---------------------------------------------------------------------------

def _date(value):
    return f"{value.day} {value:%B %Y}" if value else ""


def _investigator_name(application):
    data = application.form_data or {}
    name = (data.get("piName") or "").strip()
    title = (data.get("piTitle") or "").strip()
    if name:
        if title and not name.lower().startswith(title.lower().rstrip(".")):
            name = f"{title} {name}"
        return name
    return application.applicant.full_name


def _institution(application):
    data = application.form_data or {}
    return (data.get("piInstitution") or "").strip() or (getattr(application.applicant, "institution", "") or "").strip()


def _department(application):
    data = application.form_data or {}
    return (data.get("piDepartment") or "").strip() or (getattr(application.applicant, "department", "") or "").strip()


def verify_page_url(reference_no=None):
    url = settings.SITE_URL.rstrip("/") + reverse("pages:verify")
    return f"{url}?ref={quote(reference_no, safe='/')}" if reference_no else url


def values(application):
    """Every {placeholder} value for one application."""
    from pages import verification
    from pages.certificate_signatory import chair_details

    chair = chair_details()
    name = _investigator_name(application)
    institution = _institution(application)
    reference = application.reference_no or ""
    decided = application.decided_at or timezone.now()
    expires = getattr(application, "approval_expires_at", None)
    if expires is None and decided:
        from .models import Application
        expires = decided + timedelta(days=Application.APPROVAL_VALIDITY_DAYS)
    return {
        "applicant_name": name,
        "study_title": application.title,
        "reference_no": reference,
        "review_pathway": fees.label_for(application.review_type) or "ethics review",
        "approval_date": _date(decided),
        "valid_until": _date(expires),
        "investigator": f"{name} ({institution})" if institution else name,
        "institution": institution,
        "committee_name": COMMITTEE_NAME,
        "chair_name": chair["name"],
        "chair_title": chair["title"],
        "verification_code": verification.verification_code(reference) if reference else "",
        "today": _date(timezone.localtime()),
    }


def fill(text, vals):
    """Replaces known {placeholders}; anything else is left exactly as typed."""
    return _PLACEHOLDER_RE.sub(lambda m: str(vals[m.group(1)]) if m.group(1) in vals else m.group(0), text or "")


def unknown_placeholders(*texts):
    found = set()
    for text in texts:
        found.update(k for k in _PLACEHOLDER_RE.findall(text or "") if k not in PLACEHOLDER_KEYS)
    return sorted(found)


def paragraphs(text):
    return [" ".join(block.split()) for block in re.split(r"\n\s*\n", text or "") if block.strip()]


def lines(text):
    return [line.strip(" \t-•*") for line in (text or "").splitlines() if line.strip(" \t-•*")]


def _esc(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Content (shared by the PDFs, the on-screen pages and the email)
# ---------------------------------------------------------------------------

def _template(template=None):
    if template is not None:
        return template
    from pages.models import ApprovalDocumentTemplate
    return ApprovalDocumentTemplate.get_solo()


def letter_content(application, template=None):
    t = _template(template)
    v = values(application)
    return {
        "values": v,
        "subject": fill(t.letter_subject, v),
        "salutation": fill(t.letter_salutation, v),
        "body": [fill(p, v) for p in paragraphs(t.letter_body)],
        "conditions_heading": fill(t.letter_conditions_heading, v),
        "conditions": [fill(c, v) for c in lines(t.letter_conditions)],
        "closing": [fill(p, v) for p in paragraphs(t.letter_closing)],
        "sign_off": fill(t.letter_sign_off, v),
        "show_summary": t.letter_show_summary,
        "show_verification": t.letter_show_verification and bool(v["reference_no"]),
        "addressee": [x for x in (v["applicant_name"], _department(application), v["institution"]) if x],
    }


def certificate_content(application, template=None):
    t = _template(template)
    v = values(application)
    details = []
    if t.cert_show_reference and v["reference_no"]:
        details.append(("Reference No.", v["reference_no"]))
    if t.cert_show_pathway:
        details.append(("Review Pathway", v["review_pathway"]))
    if t.cert_show_approval_date:
        details.append(("Date of Approval", v["approval_date"]))
    if t.cert_show_valid_until and v["valid_until"]:
        details.append(("Valid Until", v["valid_until"]))
    return {
        "values": v,
        "title": fill(t.cert_title, v),
        "subtitle": fill(t.cert_subtitle, v),
        "intro": fill(t.cert_intro, v),
        "study_title": v["study_title"],
        "statement": fill(t.cert_statement, v),
        "seal_caption": (fill(t.cert_seal_caption, v) or "ETHICAL CLEARANCE").upper()[:24],
        "details": details,
        "show_verification": t.cert_show_verification and bool(v["reference_no"]),
    }


def email_content(application, template=None):
    t = _template(template)
    v = values(application)
    return {
        "values": v,
        "subject": fill(t.email_subject, v),
        "heading": fill(t.email_heading, v),
        "paragraphs": [fill(p, v) for p in paragraphs(t.email_body)],
    }


def pdf_response(application, kind, *, download=False):
    """HttpResponse with the approval letter (kind="approval") or the
    certificate of ethical clearance (kind="certificate")."""
    from django.http import HttpResponse

    if kind == "approval":
        body, name = render_letter_pdf(application), letter_filename(application)
    else:
        body, name = render_certificate_pdf(application), certificate_filename(application)
    response = HttpResponse(body, content_type="application/pdf")
    response["Content-Disposition"] = f'{"attachment" if download else "inline"}; filename="{name}"'
    return response


def letter_filename(application):
    return f"MSREC-Approval-Letter-{(application.reference_no or 'draft').replace('/', '-')}.pdf"


def certificate_filename(application):
    return f"MSREC-Ethical-Clearance-Certificate-{(application.reference_no or 'draft').replace('/', '-')}.pdf"


# ---------------------------------------------------------------------------
# Shared drawing bits
# ---------------------------------------------------------------------------

def _qr_drawing(text, size):
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing

    widget = qr.QrCodeWidget(text, barLevel="M")
    widget.barFillColor = INK
    x0, y0, x1, y1 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x1 - x0), 0, 0, size / (y1 - y0), 0, 0])
    drawing.add(widget)
    return drawing


def _signature_flowable(max_w=56 * mm, max_h=15 * mm):
    from pages.certificate_signatory import chair_signature_bytes

    png = chair_signature_bytes()
    if not png:
        return Spacer(1, 14 * mm)
    try:
        reader = ImageReader(BytesIO(png))
        iw, ih = reader.getSize()
        scale = min(max_w / iw, max_h / ih)
        image = Image(BytesIO(png), width=iw * scale, height=ih * scale)
        image.hAlign = "LEFT"
        return image
    except Exception:
        return Spacer(1, 14 * mm)


def _site():
    from pages.models import SiteSettings
    return SiteSettings.get_solo()


# ---------------------------------------------------------------------------
# Approval letter (A4 portrait)
# ---------------------------------------------------------------------------

LETTER_W, LETTER_H = A4
MARGIN_X = 22 * mm


class _NumberedCanvas(rl_canvas.Canvas):
    """Canvas that knows the total page count, for "Page 1 of 2"."""

    def __init__(self, *args, **kwargs):
        self._footer_text = kwargs.pop("footer_text", "")
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        self.setStrokeColor(HAIR)
        self.setLineWidth(0.5)
        self.line(MARGIN_X, 16 * mm, LETTER_W - MARGIN_X, 16 * mm)
        self.setFont("Helvetica", 7.5)
        self.setFillColor(INK_SOFT)
        self.drawString(MARGIN_X, 11.5 * mm, self._footer_text)
        self.drawRightString(LETTER_W - MARGIN_X, 11.5 * mm, f"Page {self._pageNumber} of {total}")


def _draw_letterhead(c, site):
    from reviewer_dashboard.certificate import _logo_reader

    top = LETTER_H - 14 * mm
    logo_h = 19 * mm
    try:
        reader = _logo_reader()
        iw, ih = reader.getSize()
        c.drawImage(reader, MARGIN_X, top - logo_h, width=logo_h * iw / ih, height=logo_h, mask="auto")
        text_x = MARGIN_X + logo_h * iw / ih + 5 * mm
    except Exception:
        text_x = MARGIN_X

    c.setFillColor(INK)
    c.setFont("Times-Bold", 15.5)
    c.drawString(text_x, top - 6 * mm, COMMITTEE_NAME)
    address = [line.strip() for line in (site.footer_address or "").splitlines() if line.strip()]
    if address and address[0].lower() == COMMITTEE_NAME.lower():
        address = address[1:]
    c.setFont("Helvetica", 8.2)
    c.setFillColor(INK_SOFT)
    y = top - 11 * mm
    for line in address[:3]:
        c.drawString(text_x, y, line)
        y -= 3.7 * mm

    contact = [
        site.contact_secretariat_email or site.footer_email,
        site.footer_phone,
        urlparse(settings.SITE_URL).netloc,
    ]
    y = top - 5 * mm
    for line in [x for x in contact if x]:
        c.drawRightString(LETTER_W - MARGIN_X, y, line)
        y -= 3.7 * mm

    rule_y = LETTER_H - 38 * mm
    c.setStrokeColor(TEAL)
    c.setLineWidth(1.1)
    c.line(MARGIN_X, rule_y, LETTER_W - MARGIN_X, rule_y)
    c.setStrokeColor(HAIR)
    c.setLineWidth(0.4)
    c.line(MARGIN_X, rule_y - 1.2 * mm, LETTER_W - MARGIN_X, rule_y - 1.2 * mm)


def _draw_running_head(c, reference_no):
    c.setFont("Helvetica", 7.5)
    c.setFillColor(INK_SOFT)
    c.drawString(MARGIN_X, LETTER_H - 14 * mm, COMMITTEE_NAME)
    c.drawRightString(LETTER_W - MARGIN_X, LETTER_H - 14 * mm, reference_no or "")
    c.setStrokeColor(HAIR)
    c.setLineWidth(0.5)
    c.line(MARGIN_X, LETTER_H - 16.5 * mm, LETTER_W - MARGIN_X, LETTER_H - 16.5 * mm)


def render_letter_pdf(application, template=None):
    content = letter_content(application, template)
    v = content["values"]
    site = _site()

    styles = {
        "body": ParagraphStyle("body", fontName="Times-Roman", fontSize=11, leading=15.2, textColor=INK,
                               alignment=TA_JUSTIFY, spaceAfter=7),
        "plain": ParagraphStyle("plain", fontName="Times-Roman", fontSize=11, leading=15.2, textColor=INK),
        "subject": ParagraphStyle("subject", fontName="Times-Bold", fontSize=11.4, leading=15.5, textColor=INK,
                                  spaceBefore=2, spaceAfter=8),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8.6, leading=12, textColor=INK_SOFT),
        "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=6.6, leading=8.5, textColor=TEAL),
        "value": ParagraphStyle("value", fontName="Times-Roman", fontSize=10.6, leading=13.2, textColor=INK),
        "heading": ParagraphStyle("heading", fontName="Times-Bold", fontSize=11.4, leading=15, textColor=INK,
                                  spaceBefore=6, spaceAfter=5),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8.4, leading=11.5, textColor=INK_SOFT),
        "small_bold": ParagraphStyle("small_bold", fontName="Helvetica-Bold", fontSize=8.6, leading=12, textColor=INK),
    }

    story = [NextPageTemplate("later")]
    meta_table = Table(
        [[Paragraph(f"Our ref: <font name='Helvetica-Bold' color='#14233f'>{_esc(v['reference_no'])}</font>", styles["meta"]),
          Paragraph(_esc(v["approval_date"]), ParagraphStyle("right", parent=styles["meta"], alignment=2))]],
        colWidths=[(LETTER_W - 2 * MARGIN_X) / 2] * 2,
    )
    meta_table.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [meta_table, Spacer(1, 5 * mm)]

    for index, line in enumerate(content["addressee"]):
        font = "Times-Bold" if index == 0 else "Times-Roman"
        story.append(Paragraph(f"<font name='{font}'>{_esc(line)}</font>", styles["plain"]))
    story += [Spacer(1, 5 * mm), Paragraph(_esc(content["salutation"]), styles["plain"]), Spacer(1, 2 * mm)]
    story.append(Paragraph(_esc(content["subject"]), styles["subject"]))
    story += [Paragraph(_esc(p), styles["body"]) for p in content["body"]]

    if content["show_summary"]:
        def cell(label, value):
            return [Paragraph(label, styles["label"]), Spacer(1, 0.8 * mm),
                    Paragraph(_esc(value) or "&mdash;", styles["value"])]

        col = (LETTER_W - 2 * MARGIN_X) / 3
        summary = Table([
            [cell("STUDY TITLE", v["study_title"]), "", ""],
            [cell("PRINCIPAL INVESTIGATOR", v["investigator"]), cell("REFERENCE NUMBER", v["reference_no"]),
             cell("REVIEW PATHWAY", v["review_pathway"])],
            [cell("DATE OF APPROVAL", v["approval_date"]), cell("VALID UNTIL", v["valid_until"]),
             cell("DECISION", "Approved")],
        ], colWidths=[col] * 3)
        summary.setStyle(TableStyle([
            ("SPAN", (0, 0), (2, 0)),
            ("BACKGROUND", (0, 0), (-1, -1), TINT),
            ("BOX", (0, 0), (-1, -1), 0.6, HAIR),
            ("LINEBELOW", (0, 0), (-1, 1), 0.4, HAIR),
            ("LINEAFTER", (0, 1), (1, -1), 0.4, HAIR),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story += [Spacer(1, 1.5 * mm), summary, Spacer(1, 4 * mm)]

    if content["conditions"]:
        items = ListFlowable(
            [ListItem(Paragraph(_esc(c), ParagraphStyle("cond", parent=styles["body"], spaceAfter=3)), leftIndent=14)
             for c in content["conditions"]],
            bulletType="1", bulletFormat="%s.", bulletFontName="Times-Roman", bulletFontSize=11,
            leftIndent=14, bulletColor=INK,
        )
        story += [KeepTogether([Paragraph(_esc(content["conditions_heading"]), styles["heading"]), items]),
                  Spacer(1, 3 * mm)]

    story += [Paragraph(_esc(p), styles["body"]) for p in content["closing"]]

    sign = [Paragraph(_esc(content["sign_off"]), styles["plain"]), Spacer(1, 1.5 * mm),
            _signature_flowable(), Spacer(1, 1 * mm)]
    if v["chair_name"]:
        sign.append(Paragraph(f"<b>{_esc(v['chair_name'])}</b>", styles["plain"]))
    sign.append(Paragraph(_esc(v["chair_title"]), styles["plain"]))

    frame_w = LETTER_W - 2 * MARGIN_X
    if content["show_verification"]:
        host_path = urlparse(verify_page_url()).netloc + urlparse(verify_page_url()).path.rstrip("/")
        verify = Table([[
            _qr_drawing(verify_page_url(v["reference_no"]), 20 * mm),
            [
                Paragraph("Verify this approval", styles["small_bold"]),
                Spacer(1, 1 * mm),
                Paragraph(
                    f"Scan the code or visit <font color='#0f8a86'>{_esc(host_path)}</font> and enter "
                    f"verification code <font name='Courier-Bold' color='#14233f'>{_esc(v['verification_code'])}</font>.",
                    styles["small"],
                ),
            ],
        ]], colWidths=[24 * mm, 50 * mm])
        verify.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.6, HAIR),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        closing = Table([[sign, verify]], colWidths=[frame_w - 76 * mm, 76 * mm])
        closing.setStyle(TableStyle([
            ("VALIGN", (0, 0), (0, 0), "TOP"),
            ("VALIGN", (1, 0), (1, 0), "BOTTOM"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story += [KeepTogether([closing])]
    else:
        story += [Spacer(1, 3 * mm), KeepTogether(sign)]

    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=22 * mm, bottomMargin=22 * mm,
        title=f"Approval Letter - {v['reference_no']}", author=COMMITTEE_NAME,
    )
    first = Frame(MARGIN_X, 20 * mm, frame_w, LETTER_H - 44 * mm - 20 * mm, id="first", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    later = Frame(MARGIN_X, 20 * mm, frame_w, LETTER_H - 24 * mm - 20 * mm, id="later", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first], onPage=lambda c, d: _draw_letterhead(c, site)),
        PageTemplate(id="later", frames=[later], onPage=lambda c, d: _draw_running_head(c, v["reference_no"])),
    ])
    footer = f"{COMMITTEE_NAME}  ·  Approval letter  ·  {v['reference_no']}"
    doc.build(story, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, footer_text=footer, **k))
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Certificate of ethical clearance (A4 landscape)
# ---------------------------------------------------------------------------

def render_certificate_pdf(application, template=None):
    from reportlab.graphics import renderPDF

    from pages.certificate_signatory import chair_signature_bytes
    from reviewer_dashboard.certificate import (
        BRASS, INK as C_INK, INK_SOFT as C_SOFT, PAGE_H, PAGE_W, RULE, _border, _chair_block, _seal, _spaced,
        certificate_signatories, draw_fitted, draw_header, draw_title, fit_paragraphs, xml_escape,
    )

    content = certificate_content(application, template)
    v = content["values"]
    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"Certificate of Ethical Clearance - {v['reference_no']}")
    c.setAuthor(COMMITTEE_NAME)

    _border(c)
    draw_header(c)
    mid = PAGE_W / 2
    title_y = PAGE_H - 57 * mm
    draw_title(c, title_y, content["title"], content["subtitle"], size=38)

    c.setFont("Times-Italic", 13.5)
    c.setFillColor(C_SOFT)
    c.drawCentredString(mid, title_y - 12.5 * mm, content["intro"])

    # Details strip and signature row are fixed; the study title and the
    # statement get whatever room is left between them, however long.
    sign_y = 40 * mm
    details = content["details"]
    strip_h = 14.5 * mm if details else 0
    strip_top = sign_y + 27 * mm + strip_h
    band_top = title_y - 18 * mm
    band_bottom = strip_top + 5 * mm

    title_style = {"fontName": "Times-Bold", "fontSize": 23, "leading": 28, "textColor": C_INK}
    body_style = {"fontName": "Times-Roman", "fontSize": 13.5, "leading": 19, "textColor": C_SOFT, "minScale": 0.82}
    parts = [(xml_escape(content["study_title"]), title_style, 3.6),
             (xml_escape(content["statement"]), body_style, 0)]
    laid, total = fit_paragraphs(parts, 215 * mm, band_top - band_bottom, min_scale=0.5, shrink_index=0)
    draw_fitted(c, laid, band_top - max(0, (band_top - band_bottom - total) / 2))

    if details:
        col_w = min(62 * mm, 236 * mm / len(details))
        left = mid - col_w * len(details) / 2
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(left, strip_top, left + col_w * len(details), strip_top)
        c.line(left, strip_top - strip_h, left + col_w * len(details), strip_top - strip_h)
        for index, (label, value) in enumerate(details):
            cx = left + col_w * (index + 0.5)
            if index:
                c.line(left + col_w * index, strip_top - 2.5 * mm, left + col_w * index, strip_top - strip_h + 2.5 * mm)
            _spaced(c, label.upper(), cx, strip_top - 4.8 * mm, "Times-Roman", 7, 1.0, BRASS)
            from reportlab.lib.utils import simpleSplit

            size = 12
            wrapped = simpleSplit(value, "Times-Bold", size, col_w - 6 * mm)
            while len(wrapped) > 1 and size > 10:
                size -= 0.5
                wrapped = simpleSplit(value, "Times-Bold", size, col_w - 6 * mm)
            while len(wrapped) > 2 and size > 7:
                size -= 0.5
                wrapped = simpleSplit(value, "Times-Bold", size, col_w - 6 * mm)
            c.setFont("Times-Bold", size)
            c.setFillColor(C_INK)
            if len(wrapped) == 1:
                c.drawCentredString(cx, strip_top - 10.2 * mm, value)
            else:
                c.drawCentredString(cx, strip_top - 8.6 * mm, wrapped[0])
                c.drawCentredString(cx, strip_top - 8.6 * mm - size * 1.1, " ".join(wrapped[1:]))

    chair = certificate_signatories()
    _chair_block(c, mid + 82 * mm, sign_y, chair, chair_signature_bytes(chair))
    _seal(c, mid, sign_y + 6 * mm, content["seal_caption"])

    if content["show_verification"]:
        qr_size = 22 * mm
        qr_x, qr_y = mid - 82 * mm - 36 * mm, sign_y - 13 * mm
        renderPDF.draw(_qr_drawing(verify_page_url(v["reference_no"]), qr_size), c, qr_x, qr_y)
        tx = qr_x + qr_size + 3.5 * mm
        _left_spaced(c, "VERIFY THIS CERTIFICATE", tx, qr_y + qr_size - 4 * mm, "Times-Roman", 7, 1.0, BRASS)
        c.setFillColor(C_INK)
        c.setFont("Courier-Bold", 10.5)
        c.drawString(tx, qr_y + qr_size - 10 * mm, v["verification_code"])
        c.setFont("Times-Roman", 8.5)
        c.setFillColor(C_SOFT)
        host = urlparse(settings.SITE_URL).netloc
        c.drawString(tx, qr_y + qr_size - 15 * mm, f"{host}/verify")
        c.drawString(tx, qr_y + qr_size - 19 * mm, f"Issued {v['approval_date']}")

    if v["reference_no"] and not any(label == "Reference No." for label, _ in details):
        _spaced(c, f"REFERENCE {v['reference_no']}", mid, 20 * mm, "Times-Roman", 8, 1.0, C_SOFT)
    c.showPage()
    c.save()
    return buffer.getvalue()


def _left_spaced(c, text, x, y, font, size, spacing, color):
    c.setFont(font, size)
    c.setFillColor(color)
    for ch in text:
        c.drawString(x, y, ch)
        x += c.stringWidth(ch, font, size) + spacing


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def send_approval_email(request, application):
    """The applicant's approval email with the letter and certificate
    attached. A PDF problem never stops the email itself going out."""
    from notifications.emails import send_branded_email

    content = email_content(application)
    v = content["values"]
    attachments = []
    for filename, render in ((letter_filename(application), render_letter_pdf),
                             (certificate_filename(application), render_certificate_pdf)):
        try:
            attachments.append((filename, render(application), "application/pdf"))
        except Exception:
            logger.exception("Couldn't render %s for application %s", filename, application.pk)

    paragraphs_out = list(content["paragraphs"])
    if len(attachments) < 2:
        paragraphs_out.append(
            "Your approval documents can be downloaded from Documents in your applicant dashboard."
        )
    login_url = request.build_absolute_uri(reverse("pages:login")) if request else (
        settings.SITE_URL.rstrip("/") + reverse("pages:login")
    )
    note = f"Verification code {v['verification_code']}" if v["verification_code"] else None
    if v["valid_until"]:
        note = f"{note}  ·  Valid until {v['valid_until']}" if note else f"Valid until {v['valid_until']}"
    return send_branded_email(
        subject=content["subject"],
        to=application.applicant.email,
        heading=content["heading"],
        paragraphs=paragraphs_out,
        callout_label="Approval reference",
        callout_value=v["reference_no"],
        callout_note=note,
        callout_after=1,
        cta_text="View my documents",
        cta_url=login_url,
        preheader=f"{v['reference_no']} has been approved. Your approval letter and certificate are attached.",
        attachments=attachments,
    )


# ---------------------------------------------------------------------------
# Previews (Site Settings)
# ---------------------------------------------------------------------------

SAMPLE_TITLE = (
    "Community Perceptions of AI-Assisted Diagnostic Tools Among Nurses and Midwives in Rural District "
    "Hospitals of the Ashanti and Bono Regions of Ghana: A Mixed-Methods Study"
)


def preview_application():
    """The most recently approved application, or a realistic sample when
    there isn't one yet -- so previews show real-length titles."""
    from .models import Application

    latest = (
        Application.objects.filter(status=Application.Status.APPROVED, reference_no__isnull=False)
        .select_related("applicant").order_by("-decided_at").first()
    )
    if latest:
        return latest
    now = timezone.now()
    applicant = SimpleNamespace(full_name="Dr. Ama Serwaa Mensah", institution="University of Ghana",
                                department="School of Public Health", email="sample@example.com")
    return SimpleNamespace(
        pk=0, title=SAMPLE_TITLE, reference_no=f"MSREC/{now.year}/0042", review_type="expedited",
        decided_at=now, approval_expires_at=now + timedelta(days=730), applicant=applicant,
        form_data={"piName": "Ama Serwaa Mensah", "piTitle": "Dr.", "piInstitution": "University of Ghana",
                   "piDepartment": "School of Public Health"},
    )
