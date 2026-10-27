"""The agreement as an A4 PDF -- downloaded from the PSA pages, attached to
the client's "thank you, it's signed" email, and offered on their signed
copy.

Laid out like a contract a firm would print, not a dashboard: a centred
title, a reference line, numbered sections under hairline rules, the
parties side by side, label/value rows, signature blocks over signing
lines, and a small electronic-signature record at the end.

Letterhead: the header and footer artwork uploaded under PSA > Letterhead
(PsaSettings) are drawn edge to edge on every page -- the way letterhead
paper is printed -- and the text frame is computed from their heights, so
the text always sits between them and never under them. Without artwork,
a plain text letterhead and footer are drawn instead.
"""
import base64
import binascii
import os
import re
from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

PAGE_W, PAGE_H = A4
MARGIN_X = 20 * mm
FRAME_W = PAGE_W - 2 * MARGIN_X

# Letterhead artwork is scaled down (never up) to fit within these heights;
# full-width artwork is the usual case and is never squeezed.
HEADER_MAX_H = 50 * mm
FOOTER_MAX_H = 35 * mm
GAP_BELOW_HEADER = 9 * mm
GAP_ABOVE_FOOTER = 10 * mm

INK = colors.HexColor("#14233f")       # headings, rules
BODY = colors.HexColor("#1b1f27")      # text
MUTED = colors.HexColor("#5b6474")     # labels, footer
HAIR = colors.HexColor("#d5dae2")      # row separators

LABEL_W = 46 * mm
SIGNATURE_FONT = "PsaGreatVibes"
_SIGNATURE_FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "GreatVibes-Regular.ttf")


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

def _fonts():
    """(sans, sans_bold, serif, serif_bold): Unicode TrueType faces where the
    server has them (shared with the workshop exports), ReportLab's
    built-in faces otherwise."""
    from workshop.exports import _fonts as system_fonts
    faces = system_fonts()
    return faces["sans"][0], faces["sans"][1], faces["serif"][0], faces["serif"][1]


def _signature_font():
    """The handwriting face for typed signatures (bundled, SIL OFL)."""
    if SIGNATURE_FONT not in pdfmetrics.getRegisteredFontNames():
        try:
            pdfmetrics.registerFont(TTFont(SIGNATURE_FONT, _SIGNATURE_FONT_PATH))
        except Exception:
            return None
    return SIGNATURE_FONT


def _font_covers(font_name, text):
    """True if every character of `text` has a glyph in a TrueType font, so
    a name like "Ɔsɛi" never prints as empty boxes in the script face."""
    try:
        face = pdfmetrics.getFont(font_name).face
    except Exception:
        return False
    glyphs = getattr(face, "charToGlyph", None)
    if glyphs is None:
        # A built-in (Type 1) face: Latin-1 only.
        return all(ord(ch) < 256 for ch in text)
    return all(ord(ch) in glyphs for ch in text if not ch.isspace())


# ---------------------------------------------------------------------------
# Letterhead
# ---------------------------------------------------------------------------

def _fit(image_bytes, max_h):
    """(ImageReader, x, width, height) spanning the page width, scaled down
    and centred only if that would be taller than max_h; None if absent or
    unreadable -- a bad image must never stop an agreement printing."""
    if not image_bytes:
        return None
    try:
        reader = ImageReader(BytesIO(image_bytes))
        iw, ih = reader.getSize()
        width, height = PAGE_W, PAGE_W * ih / iw
        if height > max_h:
            height, width = max_h, max_h * iw / ih
        return reader, (PAGE_W - width) / 2, width, height
    except Exception:
        return None


def letterhead(settings=None):
    """(header, footer) as fitted by _fit, each possibly None."""
    from .models import PsaSettings
    s = settings or PsaSettings.get_solo()
    return _fit(s.image("header"), HEADER_MAX_H), _fit(s.image("footer"), FOOTER_MAX_H)


def frame_bounds(header, footer):
    """(top_first, top_later, bottom): distances from the page's top and
    bottom edges that the text frame keeps clear on the first and later
    pages. Exposed so the settings page and the tests can check the fit."""
    if header:
        top = header[3] + GAP_BELOW_HEADER
        top_first = top_later = top
    else:
        top_first, top_later = 40 * mm, 24 * mm
    bottom = (footer[3] + GAP_ABOVE_FOOTER) if footer else 22 * mm
    return top_first, top_later, bottom


class _Canvas(rl_canvas.Canvas):
    """Draws the footer on every page once the total page count is known
    ("Page 2 of 3")."""

    def __init__(self, *args, footer=None, footer_text="", sans="Helvetica", **kwargs):
        super().__init__(*args, **kwargs)
        self._footer = footer
        self._footer_text = footer_text
        self._sans = sans
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        number = f"Page {self._pageNumber} of {total}"
        self.setFont(self._sans, 7.5)
        self.setFillColor(MUTED)
        if self._footer:
            reader, x, w, h = self._footer
            self.drawImage(reader, x, 0, width=w, height=h, mask="auto")
            self.drawRightString(PAGE_W - MARGIN_X, h + 3.5 * mm, number)
            return
        self.setStrokeColor(HAIR)
        self.setLineWidth(0.5)
        self.line(MARGIN_X, 16 * mm, PAGE_W - MARGIN_X, 16 * mm)
        self.drawString(MARGIN_X, 11.5 * mm, self._footer_text)
        self.drawRightString(PAGE_W - MARGIN_X, 11.5 * mm, number)


def _draw_text_letterhead(c, a, fonts, first):
    """The plain letterhead used when no header artwork is uploaded."""
    sans, sans_bold, serif, serif_bold = fonts
    if first:
        c.setFillColor(INK)
        c.setFont(serif_bold, 15)
        c.drawString(MARGIN_X, PAGE_H - 22 * mm, a.provider_name.title() if a.provider_name.isupper() else a.provider_name)
        c.setFont(sans, 8.3)
        c.setFillColor(MUTED)
        c.drawString(MARGIN_X, PAGE_H - 27.5 * mm, a.provider_address)
        c.setStrokeColor(INK)
        c.setLineWidth(0.9)
        c.line(MARGIN_X, PAGE_H - 32 * mm, PAGE_W - MARGIN_X, PAGE_H - 32 * mm)
        c.setLineWidth(0.3)
        c.line(MARGIN_X, PAGE_H - 33.1 * mm, PAGE_W - MARGIN_X, PAGE_H - 33.1 * mm)
    else:
        c.setFont(sans, 7.5)
        c.setFillColor(MUTED)
        c.drawString(MARGIN_X, PAGE_H - 14 * mm, "Metascholar Limited  ·  Professional Service Agreement")
        c.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 14 * mm, a.reference or "")
        c.setStrokeColor(HAIR)
        c.setLineWidth(0.5)
        c.line(MARGIN_X, PAGE_H - 16.5 * mm, PAGE_W - MARGIN_X, PAGE_H - 16.5 * mm)


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

def _text(value):
    """Escaped for a Paragraph, keeping the writer's line breaks."""
    return escape(str(value or "")).replace("\n", "<br/>")


def _day(d):
    return f"{d.day} {d:%B %Y}" if d else ""


def _when(dt):
    if not dt:
        return ""
    local = timezone.localtime(dt)
    return f"{local.day} {local:%B %Y} at {local:%H:%M} ({local:%Z})"


def _money(a, value):
    return f"{a.currency} {value:,.2f}" if value is not None else ""


def _data_url_image(data_url, max_w, max_h):
    """A drawn signature (PNG data: URL) as an Image flowable, or None."""
    head, _, body = (data_url or "").partition(",")
    if not head.startswith("data:image/"):
        return None
    try:
        raw = base64.b64decode(body)
        reader = ImageReader(BytesIO(raw))
        iw, ih = reader.getSize()
        scale = min(max_w / iw, max_h / ih)
        image = Image(BytesIO(raw), width=iw * scale, height=ih * scale)
        image.hAlign = "LEFT"
        return image
    except (binascii.Error, ValueError, OSError):
        return None


def filename(a):
    """"PSA-2026-0001 Kwame Mensah.pdf" -> a safe download name."""
    name = re.sub(r"[^A-Za-z0-9]+", "-", f"{a.reference or 'PSA'} {a.client_name}").strip("-")
    return f"{name or 'agreement'}.pdf"


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------

def render(a, settings=None):
    """The agreement as PDF bytes."""
    sans, sans_bold, serif, serif_bold = _fonts()
    # Names like "Ɔsɛi" must print: if the serif face lacks any character in
    # what was typed, set the text in the sans face (which usually has it).
    typed = " ".join(str(x or "") for x in [
        a.client_name, a.client_email, a.client_phone, a.client_address, a.service_title, a.payment_schedule,
        a.payment_basis_other, a.company_signatory_name, a.company_signatory_role, a.provider_address,
        *a.deliverable_list(),
    ])
    if not _font_covers(serif, typed) and _font_covers(sans, typed):
        serif, serif_bold = sans, sans_bold
    fonts = (sans, sans_bold, serif, serif_bold)
    header, footer = letterhead(settings)
    top_first, top_later, bottom = frame_bounds(header, footer)

    st = {
        "title": ParagraphStyle("title", fontName=serif_bold, fontSize=16, leading=20, textColor=INK,
                                alignment=TA_CENTER),
        "caption": ParagraphStyle("caption", fontName=sans, fontSize=7.6, leading=10, textColor=MUTED,
                                  alignment=TA_CENTER),
        "meta": ParagraphStyle("meta", fontName=sans, fontSize=8.4, leading=11, textColor=MUTED),
        "meta_r": ParagraphStyle("meta_r", fontName=sans, fontSize=8.4, leading=11, textColor=MUTED,
                                 alignment=TA_RIGHT),
        "h": ParagraphStyle("h", fontName=sans_bold, fontSize=9.2, leading=12, textColor=INK),
        "label": ParagraphStyle("label", fontName=sans, fontSize=8.4, leading=11.5, textColor=MUTED),
        "value": ParagraphStyle("value", fontName=serif, fontSize=10.5, leading=14, textColor=BODY),
        "value_b": ParagraphStyle("value_b", fontName=serif_bold, fontSize=10.5, leading=14, textColor=BODY),
        "body": ParagraphStyle("body", fontName=serif, fontSize=10.2, leading=14.2, textColor=BODY),
        "small": ParagraphStyle("small", fontName=sans, fontSize=7.6, leading=10.4, textColor=MUTED),
        "party": ParagraphStyle("party", fontName=sans_bold, fontSize=7.8, leading=10.5, textColor=MUTED),
    }
    P = Paragraph

    def section(number, title):
        heading = Table([[P(f"{number}.&nbsp;&nbsp;{escape(title.upper())}", st["h"])]], colWidths=[FRAME_W])
        heading.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 0.7, INK),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        # A heading is never left alone at the foot of a page.
        return [CondPageBreak(32 * mm), Spacer(1, 6.5 * mm), heading, Spacer(1, 2.5 * mm)]

    def rows(pairs):
        """Label / value rows on hairlines -- every label column the same
        width, so all sections line up down the page. A value may be a list
        of flowables: each becomes its own row under one label (with no
        rules between them), so a long list can break across pages."""
        data, style = [], [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]
        for label, value in pairs:
            parts = value if isinstance(value, list) else [value]
            first = len(data)
            for i, part in enumerate(parts):
                cell = P(part, st["value"]) if isinstance(part, str) else part
                data.append([P(escape(label), st["label"]) if i == 0 else "", cell])
            last = len(data) - 1
            style += [
                ("TOPPADDING", (1, first), (1, first), 4.2),
                ("TOPPADDING", (0, first), (0, first), 5.4),   # small sans label on the serif baseline
                ("TOPPADDING", (0, first + 1), (-1, last), 1.2),
                ("BOTTOMPADDING", (0, first), (-1, last - 1), 1.2),
                ("BOTTOMPADDING", (0, last), (-1, last), 4.2),
                ("LINEBELOW", (0, last), (-1, last), 0.4, HAIR),
            ]
        table = Table(data, colWidths=[LABEL_W, FRAME_W - LABEL_W])
        table.setStyle(TableStyle(style))
        return table

    def clause(text):
        return [Spacer(1, 3 * mm), P(_text(text), st["body"])]

    story = []

    # ---- Title block --------------------------------------------------
    status = {
        "signed": "Signed by both parties",
        "sent": "Awaiting the client's signature",
        "changes": "Under revision at the client's request",
        "cancelled": "Cancelled",
        "draft": "Draft",
    }.get(a.status, "")
    story += [
        P("PROFESSIONAL SERVICE AGREEMENT", st["title"]),
        Spacer(1, 1.6 * mm),
        P("C O N F I D E N T I A L", st["caption"]),
        Spacer(1, 5 * mm),
    ]
    meta = Table([[
        P(f"Agreement No.&nbsp; <font name='{sans_bold}' color='#14233f'>{escape(a.reference or '—')}</font>", st["meta"]),
        P(f"Agreement date&nbsp; <font name='{sans_bold}' color='#14233f'>{escape(_day(a.agreement_date))}</font>",
          ParagraphStyle("meta_c", parent=st["meta"], alignment=TA_CENTER)),
        P(f"Status&nbsp; <font name='{sans_bold}' color='#14233f'>{escape(status)}</font>", st["meta_r"]),
    ]], colWidths=[FRAME_W / 3] * 3)
    meta.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.4, HAIR), ("LINEBELOW", (0, 0), (-1, 0), 0.4, HAIR),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story += [meta, Spacer(1, 3.5 * mm),
              P("This agreement sets out the services, fees, timelines and responsibilities agreed between "
                "Metascholar Limited and its client.", st["body"])]

    # ---- 1. The parties -----------------------------------------------
    sec = section(1, "The Parties")
    provider = [P("SERVICE PROVIDER", st["party"]), Spacer(1, 1.5 * mm),
                P(escape(a.provider_name), st["value_b"]), P(_text(a.provider_address), st["value"])]
    client = [P("CLIENT", st["party"]), Spacer(1, 1.5 * mm), P(escape(a.client_name), st["value_b"])]
    client += [P(escape(v), st["value"]) for v in (a.client_email, a.client_phone) if v]
    if a.client_address:
        client.append(P(_text(a.client_address), st["value"]))
    parties = Table([[provider, client]], colWidths=[FRAME_W / 2] * 2)
    parties.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, -1), 6 * mm),
        ("RIGHTPADDING", (1, 0), (1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    sec.append(parties)
    sec += clause("Metascholar Limited and the Client are individually a “Party” and collectively the “Parties.”")
    story.append(KeepTogether(sec))

    # ---- 2. Term ------------------------------------------------------
    sec = section(2, "Term")
    term = [("Service start date", escape(_day(a.start_date)) or "—"),
            ("Expected completion date", escape(_day(a.completion_date)) or "—")]
    if a.term_days is not None:
        term.append(("Duration", f"{a.term_days} day{'s' if a.term_days != 1 else ''}"))
    sec.append(rows(term))
    story.append(KeepTogether(sec))

    # ---- 3. The service -----------------------------------------------
    sec = section(3, "The Service")
    sec.append(P("Metascholar Limited agrees to provide the following professional service(s):", st["body"]))
    sec.append(Spacer(1, 2 * mm))
    # Numbered with a hanging indent, so wrapped lines align with the text.
    numbered = ParagraphStyle("numbered", parent=st["value"], leftIndent=7 * mm, bulletIndent=0)
    items = [P(_text(d), numbered, bulletText=f"{i}.") for i, d in enumerate(a.deliverable_list(), 1)] or "—"
    sec.append(rows([("Service / project title", P(escape(a.service_title or "—"), st["value_b"])),
                     ("Scope of work / deliverables", items)]))
    sec += clause("The Client will provide all information, materials, approvals, and feedback reasonably "
                  "needed to complete the agreed service. Any changes to the scope, price, or deadline require "
                  "agreement by both Parties.")
    # A short list stays in one piece; a long one flows on from where it
    # starts rather than leaving the rest of the page empty.
    story += [KeepTogether(sec)] if len(a.deliverable_list()) <= 8 else sec

    # ---- 4. Payment ---------------------------------------------------
    sec = section(4, "Payment Amount")
    sec.append(rows([
        ("Agreed fee", P(escape(_money(a, a.fee) or "—"), st["value_b"])),
        ("Payment basis", escape(a.payment_basis_label or "—")),
        ("Deposit / amount due upfront", escape(_money(a, a.deposit))),
        ("Balance due", escape(_money(a, a.balance) or "—")),
        ("Payment due date / schedule", _text(a.payment_schedule) or "—"),
    ]))
    sec += clause("The Client agrees to pay the amounts stated above according to the agreed schedule. "
                  "Additional services or charges must be approved by the Client before they are incurred.")
    story.append(KeepTogether(sec))

    # ---- 5. Acceptance -------------------------------------------------
    acceptance = section(5, "Client Review and Acceptance")
    acceptance.append(P("By signing or electronically accepting this Agreement, the Client confirms that they have "
                        "reviewed and accepted the services, timelines, and payment terms set out above.", st["body"]))
    acceptance.append(Spacer(1, 7 * mm))

    col_w = (FRAME_W - 12 * mm) / 2
    sig_h = 17 * mm

    def signature(kind, value, name):
        """The signature itself, sitting on the signing line."""
        if kind == "drawn":
            mark = _data_url_image(value, col_w, sig_h)
            if mark:
                return mark
        if kind == "typed" and value:
            font = _signature_font()
            if font and _font_covers(font, value):
                size = 26
                while size > 13 and pdfmetrics.stringWidth(value, font, size) > col_w:
                    size -= 1
                return P(escape(value), ParagraphStyle("sig", fontName=font, fontSize=size, leading=size * 1.1,
                                                        textColor=colors.HexColor("#1b2a5c")))
            # A name the script face can't draw is set in the text face
            # (no <i>: the server's TrueType faces have no italic mapped).
            return P(escape(value), ParagraphStyle("sig_plain", parent=st["value"], fontSize=14, leading=17))
        return Spacer(1, sig_h)

    def block(heading, kind, value, name, lines):
        mark = Table([[signature(kind, value, name)]], colWidths=[col_w], rowHeights=[sig_h + 2 * mm])
        mark.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LINEBELOW", (0, 0), (-1, -1), 0.7, INK),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]))
        cell = [P(escape(heading), st["party"]), Spacer(1, 1 * mm), mark, Spacer(1, 1.8 * mm)]
        cell += [P(line, st["value_b"] if i == 0 else st["label"]) for i, line in enumerate(lines)]
        return cell

    client_block = block(
        "CLIENT SIGNATURE / ELECTRONIC ACCEPTANCE", a.client_signature_kind, a.client_signature, a.client_name,
        [escape(a.client_name),
         f"Date: {escape(_day(timezone.localtime(a.client_signed_at).date()))}" if a.client_signed_at
         else "Not yet signed"],
    )
    company_block = block(
        "FOR METASCHOLAR LIMITED", a.company_signature_kind, a.company_signature, a.company_signatory_name,
        [escape(a.company_signatory_name or "Metascholar Limited"),
         " · ".join(x for x in (escape(a.company_signatory_role),
                                f"Date: {escape(_day(timezone.localtime(a.company_signed_at).date()))}"
                                if a.company_signed_at else "") if x) or "Not yet signed"],
    )
    signatures = Table([[client_block, "", company_block]], colWidths=[col_w, 12 * mm, col_w])
    signatures.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    acceptance.append(signatures)

    # Electronic-signature record: what an auditor would ask for.
    record = []
    if a.company_signed_at:
        record.append(f"Signed for Metascholar Limited by {escape(a.company_signatory_name)}"
                      f"{' (' + escape(a.company_signatory_role) + ')' if a.company_signatory_role else ''} "
                      f"on {escape(_when(a.company_signed_at))}.")
    if a.client_signed_at:
        how = "a drawn signature" if a.client_signature_kind == "drawn" else "a typed name"
        where = f" from IP address {escape(a.client_signed_ip)}" if a.client_signed_ip else ""
        record.append(f"Signed electronically by {escape(a.client_name)} on {escape(_when(a.client_signed_at))}, "
                      f"using {how}{where}.")
    if record:
        acceptance += [Spacer(1, 8 * mm), P("ELECTRONIC SIGNATURE RECORD", st["party"]), Spacer(1, 1 * mm)]
        acceptance += [P(line, st["small"]) for line in record]
    story.append(KeepTogether(acceptance))

    # ---- Build --------------------------------------------------------
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=top_later, bottomMargin=bottom,
        title=f"Professional Service Agreement {a.reference or ''} — {a.client_name}",
        author="Metascholar Limited", subject="Professional Service Agreement",
    )
    first = Frame(MARGIN_X, bottom, FRAME_W, PAGE_H - top_first - bottom, id="first",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    later = Frame(MARGIN_X, bottom, FRAME_W, PAGE_H - top_later - bottom, id="later",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def on_first(c, d):
        if header:
            reader, x, w, h = header
            c.drawImage(reader, x, PAGE_H - h, width=w, height=h, mask="auto")
        else:
            _draw_text_letterhead(c, a, fonts, first=True)

    def on_later(c, d):
        if header:
            on_first(c, d)
        else:
            _draw_text_letterhead(c, a, fonts, first=False)

    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first], onPage=on_first, autoNextPageTemplate="later"),
        PageTemplate(id="later", frames=[later], onPage=on_later),
    ])
    footer_text = f"Professional Service Agreement  ·  {a.reference or ''}  ·  {a.client_name}"
    doc.build(story, canvasmaker=lambda *args, **kw: _Canvas(*args, footer=footer, footer_text=footer_text,
                                                              sans=sans, **kw))
    return buffer.getvalue()


def sample_agreement():
    """An unsaved, clearly-sample agreement for the letterhead preview, so
    the artwork can be checked on a realistic page before anything is sent."""
    from datetime import timedelta
    from decimal import Decimal

    from .models import ServiceAgreement

    today = timezone.localdate()
    return ServiceAgreement(
        reference="PSA-SAMPLE", status=ServiceAgreement.Status.SIGNED, agreement_date=today,
        client_name="Sample Client", client_email="client@example.com", client_phone="+233 24 000 0000",
        client_address="Sample address, Accra", start_date=today, completion_date=today + timedelta(days=30),
        service_title="Sample service — letterhead preview",
        deliverables=["First deliverable", "Second deliverable", "Third deliverable"],
        currency="GHS", fee=Decimal("2500.00"), payment_basis="fixed", deposit=Decimal("1000.00"),
        payment_schedule="Deposit on signing; balance on delivery.",
        company_signatory_name="Metascholar Limited", company_signature_kind="typed",
        company_signature="Metascholar", company_signed_at=timezone.now(),
        client_signature_kind="typed", client_signature="Sample Client", client_signed_at=timezone.now(),
    )
