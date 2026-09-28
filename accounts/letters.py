"""The A4 letter engine shared by the formal letters MSREC sends to an
account holder -- the Appointment Letter (accounts/appointment.py) and the
Suspension Letter (accounts/suspension.py).

Each letter has its own admin-editable template model in pages.models
(AppointmentLetterTemplate, SuspensionLetterTemplate) with the same
letterhead / signatory columns -- header_path, footer_path, sign_name,
sign_title, sign_path -- which is all this module reads from it. The letter
modules build a `content` dict (see _build for its keys) and hand it to
render().

Fitting the page: the letter is laid out at full size first; if it runs
onto a second page it is re-laid a step at a time with slightly smaller
type and spacing (never below ~9 pt) until it fits on one A4 sheet. Only a
letter too long for that flows onto a second page, at full size, with a
running head.
"""
import re
from io import BytesIO

from django.utils import timezone
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from applicant_dashboard.approval_documents import (
    _PLACEHOLDER_RE, BODY, COMMITTEE_NAME, FOOTER_MAX_H, HAIR, HEADER_MAX_H, INK, INK_SOFT, LETTER_H, LETTER_W,
    MARGIN_X, _NumberedCanvas, _draw_header_image, _draw_letterhead, _draw_running_head, _esc, _letter_image,
    _signature_flowable,
)

# Each step shrinks type and spacing together; 0.82 keeps body text at 9 pt.
FIT_SCALES = (1.0, 0.95, 0.9, 0.86, 0.82)


def date_text(value):
    return f"{value.day} {value:%B %Y}" if value else ""


def unknown_placeholders(keys, *texts):
    """{placeholders} used in `texts` that aren't in `keys`."""
    found = set()
    for text in texts:
        found.update(k for k in _PLACEHOLDER_RE.findall(text or "") if k not in keys)
    return sorted(found)


def text_blocks(text):
    """Free text as a list of paragraphs, each a list of lines -- the
    writer's own paragraph and line breaks are kept, so a short list typed
    one item per line stays a list on the letter."""
    blocks = []
    for block in re.split(r"\n\s*\n", text or ""):
        lines = [" ".join(line.split()) for line in block.split("\n") if line.strip()]
        if lines:
            blocks.append(lines)
    return blocks


def signatory(template):
    """Who signs: dict(name, title, image bytes|None). A signatory set on
    the letter's own template wins; otherwise the Chair (Site Settings >
    Certificates), signature included."""
    from pages import storage as pages_storage
    from pages.certificate_signatory import chair_details, chair_signature_bytes

    name = (template.sign_name or "").strip()
    if name:
        image = pages_storage.download_object(template.sign_path) if template.sign_path else None
        return {"name": name, "title": (template.sign_title or "").strip(), "image": image}
    chair = chair_details()
    return {"name": chair["name"], "title": chair["title"], "image": chair_signature_bytes(chair)}


def letterhead_images(template):
    """The letter's own header / footer artwork, falling back to the
    approval letter's, then (None) to the built-in text letterhead."""
    from pages import storage as pages_storage
    from pages.models import ApprovalDocumentTemplate

    approval = ApprovalDocumentTemplate.get_solo()
    header_path = template.header_path or approval.letter_header_path
    footer_path = template.footer_path or approval.letter_footer_path
    header = _letter_image(pages_storage.download_object(header_path), HEADER_MAX_H) if header_path else None
    footer = _letter_image(pages_storage.download_object(footer_path), FOOTER_MAX_H) if footer_path else None
    return header, footer


def render(user, content, template):
    """(pdf_bytes, page_count, scale) -- the largest scale in FIT_SCALES
    that keeps the letter on one page, or full size if none does."""
    from pages.models import SiteSettings

    header, footer = letterhead_images(template)
    site = SiteSettings.get_solo()
    first = None
    for scale in FIT_SCALES:
        pdf, pages = build(user, content, header, footer, site, scale)
        if first is None:
            first = (pdf, pages, scale)
        if pages == 1:
            return pdf, pages, scale
    return first


def build(user, content, header_image, footer_image, site, scale):
    """One layout pass at `scale`. Returns (pdf_bytes, page_count).

    `content` keys: ethics_id, date, flag (small caps line above the
    addressee, or ""), salutation, subject, body -- a list of ("text", str)
    paragraphs and ("box", (label, blocks)) panels -- closing (list of
    str), sign_off, signatory (see signatory()), doc_label."""
    s = lambda value: value * scale  # noqa: E731
    size, leading = s(11), s(15.2)
    styles = {
        "body": ParagraphStyle("body", fontName="Times-Roman", fontSize=size, leading=leading, textColor=BODY,
                               alignment=TA_JUSTIFY, spaceAfter=s(7)),
        "plain": ParagraphStyle("plain", fontName="Times-Roman", fontSize=size, leading=leading, textColor=BODY),
        "subject": ParagraphStyle("subject", fontName="Times-Bold", fontSize=s(11.4), leading=s(15.5),
                                  textColor=INK, spaceBefore=2, spaceAfter=s(8)),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8.6, leading=12, textColor=INK_SOFT),
        "flag": ParagraphStyle("flag", fontName="Helvetica-Bold", fontSize=7.4, leading=10, textColor=INK_SOFT),
        "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=7, leading=10, textColor=INK_SOFT,
                                spaceAfter=s(2.5)),
        "box": ParagraphStyle("box", fontName="Times-Roman", fontSize=size, leading=leading, textColor=BODY,
                              alignment=TA_JUSTIFY),
    }
    frame_w = LETTER_W - 2 * MARGIN_X
    ethics_id = content["ethics_id"]

    story = [NextPageTemplate("later")]
    meta = Table(
        [[Paragraph(f"Ethics ID: <font name='Helvetica-Bold' color='#14233f'>{_esc(ethics_id)}</font>"
                    if ethics_id else "", styles["meta"]),
          Paragraph(_esc(date_text(timezone.localtime(content["date"]))),
                    ParagraphStyle("right", parent=styles["meta"], alignment=2))]],
        colWidths=[frame_w / 2] * 2,
    )
    meta.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [meta, Spacer(1, s(4) * mm)]
    if content.get("flag"):
        story += [Paragraph(_esc(content["flag"]), styles["flag"]), Spacer(1, s(2) * mm)]

    addressee = [user.full_name, getattr(user, "position", ""), getattr(user, "institution", ""), user.email]
    for index, line in enumerate(x for x in addressee if (x or "").strip()):
        font = "Times-Bold" if index == 0 else "Times-Roman"
        story.append(Paragraph(f"<font name='{font}'>{_esc(line.strip())}</font>", styles["plain"]))
    story += [Spacer(1, s(5) * mm), Paragraph(_esc(content["salutation"]), styles["plain"]), Spacer(1, s(2) * mm),
              Paragraph(_esc(content["subject"]), styles["subject"])]

    for kind, item in content["body"]:
        if kind == "text":
            story.append(Paragraph(_esc(item), styles["body"]))
        else:
            label, blocks = item
            story += [_box(label, blocks, styles, frame_w, s), Spacer(1, s(3.5) * mm)]

    closing = [Paragraph(_esc(p), styles["body"]) for p in content["closing"]]
    sign = content["signatory"]
    block = [Spacer(1, s(2) * mm), Paragraph(_esc(content["sign_off"]), styles["plain"]), Spacer(1, s(1.5) * mm),
             _signature_flowable(sign["image"], max_h=s(15) * mm), Spacer(1, 1 * mm)]
    rule = Table([[""]], colWidths=[70 * mm], rowHeights=[1])
    rule.hAlign = "LEFT"
    rule.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.5, INK)]))
    block.append(rule)
    if sign["name"]:
        block.append(Paragraph(f"<b>{_esc(sign['name'])}</b>", styles["plain"]))
    if sign["title"]:
        block.append(Paragraph(_esc(sign["title"]), styles["plain"]))
    # The closing paragraph always travels with the signature, so a
    # signature never sits alone at the top of a page.
    story.append(KeepTogether(closing + block))

    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=22 * mm, bottomMargin=22 * mm,
        title=f"MSREC {content['doc_label']} - {user.full_name}", author=COMMITTEE_NAME,
    )
    first_top = (header_image[3] + 8 * mm) if header_image else 44 * mm
    bottom = (footer_image[3] + 10 * mm) if footer_image else 20 * mm
    first = Frame(MARGIN_X, bottom, frame_w, LETTER_H - first_top - bottom, id="first",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    later = Frame(MARGIN_X, bottom, frame_w, LETTER_H - 24 * mm - bottom, id="later",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    draw_first = ((lambda c, d: _draw_header_image(c, header_image)) if header_image
                  else (lambda c, d: _draw_letterhead(c, site)))
    running = ethics_id or user.full_name
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first], onPage=draw_first),
        PageTemplate(id="later", frames=[later], onPage=lambda c, d: _draw_running_head(c, running)),
    ])
    footer_text = f"{COMMITTEE_NAME}  ·  {content['doc_label']}  ·  {running}"
    doc.build(story, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, footer_text=footer_text,
                                                                 footer_image=footer_image, **k))
    return buffer.getvalue(), doc.page


def _box(label, blocks, styles, frame_w, s):
    """A lightly tinted panel with a navy rule down its left edge -- one
    table row per paragraph, so a long one can still break between
    paragraphs rather than overflowing the page."""
    rows = [[Paragraph(_esc(label.upper()), styles["label"])]]
    for lines in blocks:
        rows.append([Paragraph("<br/>".join(_esc(line) for line in lines), styles["box"])])
    box = Table(rows, colWidths=[frame_w])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), "#f4f6f9"),
        ("LINEBEFORE", (0, 0), (0, -1), 2, INK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, HAIR),
        ("LEFTPADDING", (0, 0), (-1, -1), s(4) * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), s(4) * mm),
        ("TOPPADDING", (0, 0), (-1, -1), s(1.2) * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), s(1.2) * mm),
        ("TOPPADDING", (0, 0), (-1, 0), s(3) * mm),
        ("BOTTOMPADDING", (0, -1), (-1, -1), s(3.2) * mm),
    ]))
    return box
