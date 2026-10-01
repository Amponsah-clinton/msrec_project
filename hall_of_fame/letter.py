from io import BytesIO

from django.utils import timezone
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from applicant_dashboard.approval_documents import (
    BODY, COMMITTEE_NAME, FOOTER_MAX_H, HAIR, HEADER_MAX_H, INK, LETTER_H, LETTER_W,
    MARGIN_X, _NumberedCanvas, _draw_header_image, _draw_letterhead, _esc, _letter_image,
    _signature_flowable,
)
def _date_text(value):
    return f"{value.day} {value:%B %Y}" if value else ""


def _chair_signatory():
    from pages.certificate_signatory import chair_details, chair_signature_bytes
    chair = chair_details()
    return {"name": chair["name"], "title": chair["title"], "image": chair_signature_bytes(chair)}


def render_recognition_letter_pdf(nomination):
    from pages.models import ApprovalDocumentTemplate, SiteSettings

    approval_tpl = ApprovalDocumentTemplate.get_solo()
    site = SiteSettings.get_solo()
    sign = _chair_signatory()

    header_path = approval_tpl.letter_header_path
    footer_path = approval_tpl.letter_footer_path
    from pages import storage as pages_storage
    header = _letter_image(pages_storage.download_object(header_path), HEADER_MAX_H) if header_path else None
    footer = _letter_image(pages_storage.download_object(footer_path), FOOTER_MAX_H) if footer_path else None

    now = timezone.localtime()
    approved_at = timezone.localtime(nomination.approved_at) if nomination.approved_at else now

    size, leading = 11, 15.2
    styles = {
        "body": ParagraphStyle("body", fontName="Times-Roman", fontSize=size, leading=leading,
                               textColor=BODY, alignment=TA_JUSTIFY, spaceAfter=7),
        "plain": ParagraphStyle("plain", fontName="Times-Roman", fontSize=size, leading=leading, textColor=BODY),
        "subject": ParagraphStyle("subject", fontName="Times-Bold", fontSize=11.4, leading=15.5,
                                  textColor=INK, spaceBefore=2, spaceAfter=8),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8.6, leading=12, textColor=BODY),
    }

    frame_w = LETTER_W - 2 * MARGIN_X
    story = []

    meta = Table(
        [[Paragraph(f"Hall of Fame ID: <font name='Helvetica-Bold' color='#14233f'>"
                    f"{_esc(nomination.hof_member_id or '')}</font>", styles["meta"]),
          Paragraph(_esc(_date_text(approved_at)),
                    ParagraphStyle("right", parent=styles["meta"], alignment=2))]],
        colWidths=[frame_w / 2] * 2,
    )
    meta.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [meta, Spacer(1, 4 * mm)]

    addressee_lines = [
        nomination.full_name,
        nomination.institution,
    ]
    for i, line in enumerate(x for x in addressee_lines if (x or "").strip()):
        font = "Times-Bold" if i == 0 else "Times-Roman"
        story.append(Paragraph(f"<font name='{font}'>{_esc(line.strip())}</font>", styles["plain"]))

    title = nomination.professional_title
    surname = nomination.full_name.split()[-1] if nomination.full_name else ""
    salutation = f"Dear {title} {surname}," if title else f"Dear {nomination.full_name},"

    story += [
        Spacer(1, 5 * mm),
        Paragraph(_esc(salutation), styles["plain"]),
        Spacer(1, 2 * mm),
        Paragraph(_esc(
            "RE: INDUCTION INTO THE METASCHOLAR RESEARCH ETHICS COMMITTEE HALL OF FAME"
        ), styles["subject"]),
    ]

    paragraphs_text = [
        f"On behalf of the {COMMITTEE_NAME}, we are pleased to inform you that your "
        f"nomination has been approved and that you have been formally inducted into the "
        f"MSREC Hall of Fame.",
        f"This recognition acknowledges your professional achievements and your contribution "
        f"to research ethics, scholarship, peer review, academic service, mentorship, innovation, "
        f"or other areas reflected in your approved nomination.",
        f"Your official Hall of Fame profile has been published on the MSREC platform. Your "
        f"recognition certificate and this letter are available for secure download from your "
        f"member dashboard.",
    ]
    for p in paragraphs_text:
        story.append(Paragraph(_esc(p), styles["body"]))

    info_rows = [
        [Paragraph(f"<b>Hall of Fame ID:</b> {_esc(nomination.hof_member_id or '')}", styles["plain"])],
        [Paragraph(f"<b>Recognition Reference:</b> {_esc(nomination.letter_ref or '')}", styles["plain"])],
        [Paragraph(f"<b>Recognition Year:</b> {_esc(str(nomination.recognition_year or ''))}", styles["plain"])],
    ]
    info_table = Table(info_rows, colWidths=[frame_w])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), "#f4f6f9"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2 * mm),
        ("TOPPADDING", (0, 0), (-1, 0), 3 * mm),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 3.2 * mm),
        ("LINEBEFORE", (0, 0), (0, -1), 2, INK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, HAIR),
    ]))
    story += [info_table, Spacer(1, 3.5 * mm)]

    story.append(Paragraph(_esc("Congratulations on this recognition."), styles["body"]))

    closing_block = [
        Spacer(1, 2 * mm),
        Paragraph(_esc("Yours faithfully,"), styles["plain"]),
        Spacer(1, 1.5 * mm),
        _signature_flowable(sign["image"], max_h=15 * mm),
        Spacer(1, 1 * mm),
    ]
    rule = Table([[""]], colWidths=[70 * mm], rowHeights=[1])
    rule.hAlign = "LEFT"
    rule.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.5, INK)]))
    closing_block.append(rule)
    if sign["name"]:
        closing_block.append(Paragraph(f"<b>{_esc(sign['name'])}</b>", styles["plain"]))
    if sign["title"]:
        closing_block.append(Paragraph(_esc(sign["title"]), styles["plain"]))
    closing_block.append(Paragraph(_esc(COMMITTEE_NAME), styles["plain"]))
    story.append(KeepTogether(closing_block))

    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X,
        topMargin=22 * mm, bottomMargin=22 * mm,
        title=f"MSREC Hall of Fame Recognition Letter - {nomination.full_name}",
        author=COMMITTEE_NAME,
    )
    first_top = (header[3] + 8 * mm) if header else 44 * mm
    bottom = (footer[3] + 10 * mm) if footer else 20 * mm
    frame = Frame(MARGIN_X, bottom, frame_w, LETTER_H - first_top - bottom, id="first",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    draw_first = ((lambda c, d: _draw_header_image(c, header)) if header
                  else (lambda c, d: _draw_letterhead(c, site)))
    footer_text = f"{COMMITTEE_NAME}  ·  Hall of Fame Recognition Letter  ·  {nomination.hof_member_id or ''}"
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[frame], onPage=draw_first),
    ])
    doc.build(story, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, footer_text=footer_text,
                                                                  footer_image=footer, **k))
    return buffer.getvalue()
