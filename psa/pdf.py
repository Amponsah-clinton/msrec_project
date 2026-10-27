"""The agreement as an A4 PDF -- downloaded from the PSA pages, attached to
the client's "thank you, it's signed" email, and offered on their signed
copy.

Set as a contract, not as a printout of the signing page. The web version
of the agreement is a form -- grey field labels, cards, tick boxes -- which
is right on screen and wrong on paper. Here the same facts are set the way
a law firm would set them: a title, a preamble naming the Parties, numbered
clauses in flowing prose with the dates and figures inside the sentences,
and an execution block at the end. One serif family carries the whole
document; the sans face is kept for the running footer alone.

Nothing is said here that the client did not see and accept on the signing
page -- the clause wording is the same; only its arrangement differs.

Letterhead: the header and footer artwork uploaded under PSA > Letterhead
(PsaSettings) are drawn edge to edge on every page -- the way letterhead
paper is printed -- and the text frame is computed from their heights, so
the text always sits between them and never under them. Without artwork,
a plain text letterhead and footer are drawn instead.

An agreement that is not yet signed by both Parties carries a pale
watermark saying so, so a draft can never be mistaken for an executed
contract.
"""
import base64
import binascii
import os
import re
from io import BytesIO
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, Image, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

PAGE_W, PAGE_H = A4
MARGIN_X = 22 * mm
FRAME_W = PAGE_W - 2 * MARGIN_X

# Letterhead artwork is scaled down (never up) to fit within these heights;
# full-width artwork is the usual case and is never squeezed.
HEADER_MAX_H = 50 * mm
FOOTER_MAX_H = 35 * mm
GAP_BELOW_HEADER = 9 * mm
GAP_ABOVE_FOOTER = 10 * mm

INK = colors.HexColor("#121823")       # headings
BODY = colors.HexColor("#1a1f29")      # text
MUTED = colors.HexColor("#5b6474")     # running footer
HAIR = colors.HexColor("#b9c0cc")      # signing lines, table rules
WASH = colors.HexColor("#f4f6f9")      # the one filled band, in the fee table

# Sub-clauses hang off their number at this indent, so "3.2" sits in the
# margin of its own paragraph and wrapped lines align under the text.
INDENT = 11 * mm
SUB_INDENT = INDENT + 8 * mm

SIGNATURE_FONT = "PsaGreatVibes"
_SIGNATURE_FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "GreatVibes-Regular.ttf")

# What the watermark says while the agreement is not executed by both
# Parties. A signed agreement carries none.
WATERMARKS = {
    "draft": "DRAFT",
    "sent": "UNSIGNED",
    "changes": "UNDER REVISION",
    "cancelled": "CANCELLED",
}


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
        top_first, top_later = 38 * mm, 26 * mm
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
        number = f"{self._pageNumber} of {total}"
        self.setFont(self._sans, 7.2)
        self.setFillColor(MUTED)
        if self._footer:
            reader, x, w, h = self._footer
            self.drawImage(reader, x, 0, width=w, height=h, mask="auto")
            self.drawRightString(PAGE_W - MARGIN_X, h + 3.5 * mm, number)
            return
        self.setStrokeColor(HAIR)
        self.setLineWidth(0.4)
        self.line(MARGIN_X, 16 * mm, PAGE_W - MARGIN_X, 16 * mm)
        self.drawString(MARGIN_X, 11.5 * mm, self._footer_text)
        self.drawRightString(PAGE_W - MARGIN_X, 11.5 * mm, number)


def _draw_watermark(c, word, serif_bold):
    """A pale diagonal word across the page, drawn before the text so it
    sits behind it."""
    c.saveState()
    c.translate(PAGE_W / 2, PAGE_H / 2)
    c.rotate(52)
    size = 78
    while size > 24 and pdfmetrics.stringWidth(word, serif_bold, size) > PAGE_H * 0.72:
        size -= 2
    c.setFont(serif_bold, size)
    c.setFillColor(colors.HexColor("#e5e9f0"))
    c.drawCentredString(0, -size * 0.35, word)
    c.restoreState()


def _draw_text_letterhead(c, a, fonts, first):
    """The plain letterhead used when no header artwork is uploaded. Set in
    the document's own serif, not a second voice."""
    sans, sans_bold, serif, serif_bold = fonts
    name = a.provider_name.title() if a.provider_name.isupper() else a.provider_name
    if first:
        c.setFillColor(INK)
        c.setFont(serif_bold, 14)
        c.drawString(MARGIN_X, PAGE_H - 21 * mm, name)
        c.setFont(serif, 8.6)
        c.setFillColor(MUTED)
        c.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 21 * mm, a.provider_address)
        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.line(MARGIN_X, PAGE_H - 25 * mm, PAGE_W - MARGIN_X, PAGE_H - 25 * mm)
    else:
        c.setFont(serif, 8)
        c.setFillColor(MUTED)
        c.drawString(MARGIN_X, PAGE_H - 15 * mm, f"{name}  ·  Professional Service Agreement")
        c.drawRightString(PAGE_W - MARGIN_X, PAGE_H - 15 * mm, a.reference or "")
        c.setStrokeColor(HAIR)
        c.setLineWidth(0.4)
        c.line(MARGIN_X, PAGE_H - 17.5 * mm, PAGE_W - MARGIN_X, PAGE_H - 17.5 * mm)


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

def _text(value):
    """Escaped for a Paragraph, keeping the writer's line breaks."""
    return escape(str(value or "")).replace("\n", "<br/>")


_ORDINALS = {1: "st", 2: "nd", 3: "rd", 21: "st", 22: "nd", 23: "rd", 31: "st"}


def _day(d):
    return f"{d.day} {d:%B %Y}" if d else ""


def _formal_day(d):
    """"27th day of October 2026" -- how a contract dates itself."""
    if not d:
        return ""
    return f"{d.day}{_ORDINALS.get(d.day, 'th')} day of {d:%B %Y}"


def _money(a, value):
    return f"{a.currency} {value:,.2f}" if value is not None else ""


def _letter(i):
    """1 -> 'a', 26 -> 'z', 27 -> 'aa': the lettering for deliverables."""
    label = ""
    while i > 0:
        i, rest = divmod(i - 1, 26)
        label = chr(97 + rest) + label
    return label


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

    # Ragged right, not justified: there is no hyphenation dictionary on
    # the server, so justifying this measure would open rivers of white
    # space down the page -- the surest sign of a document nobody set.
    body = ParagraphStyle("body", fontName=serif, fontSize=10, leading=14.4, textColor=BODY, spaceAfter=0)
    st = {
        "title": ParagraphStyle("title", fontName=serif_bold, fontSize=15.5, leading=19, textColor=INK,
                                alignment=TA_CENTER),
        "ref": ParagraphStyle("ref", fontName=serif, fontSize=9, leading=12, textColor=MUTED,
                              alignment=TA_CENTER),
        "body": body,
        "lead": ParagraphStyle("lead", parent=body, alignment=TA_CENTER, fontName=serif_bold, fontSize=9.4,
                               textColor=INK),
        "party": ParagraphStyle("party", parent=body, leftIndent=INDENT, bulletIndent=0),
        "h": ParagraphStyle("h", fontName=serif_bold, fontSize=10.4, leading=13, textColor=INK),
        "sub": ParagraphStyle("sub", parent=body, leftIndent=INDENT, bulletIndent=0),
        "item": ParagraphStyle("item", parent=body, leftIndent=SUB_INDENT, bulletIndent=INDENT),
        "cell": ParagraphStyle("cell", fontName=serif, fontSize=9.6, leading=12.6, textColor=BODY),
        "cell_b": ParagraphStyle("cell_b", fontName=serif_bold, fontSize=9.6, leading=12.6, textColor=INK),
        "sig_head": ParagraphStyle("sig_head", fontName=serif_bold, fontSize=8.6, leading=11.8, textColor=INK),
        "sig_line": ParagraphStyle("sig_line", fontName=serif, fontSize=9.2, leading=12.6, textColor=BODY),
        "note": ParagraphStyle("note", fontName=serif, fontSize=8.2, leading=11, textColor=MUTED),
    }
    P = Paragraph

    def strong(value, dash="—"):
        """A figure or date set in bold inside a sentence."""
        return f"<b>{escape(str(value))}</b>" if value else dash

    # Clause numbering runs straight through the document, so what the
    # heading says and what the sub-clauses say can never drift apart.
    counter = {"n": 0, "sub": 0}

    def heading(title):
        counter["n"] += 1
        counter["sub"] = 0
        return [Spacer(1, 5.4 * mm),
                P(f"{counter['n']}.&nbsp;&nbsp;{escape(title.upper())}", st["h"]),
                Spacer(1, 2.2 * mm)]

    def sub(text, style="sub", space=2.2 * mm):
        counter["sub"] += 1
        number = f"{counter['n']}.{counter['sub']}"
        return [P(text, st[style], bulletText=number), Spacer(1, space)]

    story = []

    # ---- Title --------------------------------------------------------
    rule = Table([[""]], colWidths=[48 * mm], rowHeights=[0.1])
    rule.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, INK)]))
    rule.hAlign = "CENTER"
    story += [
        P("PROFESSIONAL SERVICE AGREEMENT", st["title"]),
        Spacer(1, 2.6 * mm), rule, Spacer(1, 2.6 * mm),
        P(f"Agreement No. {escape(a.reference or 'not yet issued')}", st["ref"]),
        Spacer(1, 7 * mm),
    ]

    # ---- Preamble -----------------------------------------------------
    story += [
        P(f"THIS PROFESSIONAL SERVICE AGREEMENT is made on the "
          f"{strong(_formal_day(a.agreement_date), 'date stated below')}", st["lead"]),
        Spacer(1, 4 * mm),
        P("BETWEEN", st["lead"]),
        Spacer(1, 3 * mm),
    ]

    provider = (f"<b>{escape(a.provider_name)}</b>, of {escape(a.provider_address).rstrip('.')} "
                f"(the “<b>Provider</b>”); and")
    story += [P(provider, st["party"], bulletText="(1)"), Spacer(1, 2.6 * mm)]

    contact = "; ".join(x for x in [
        f"email {escape(a.client_email)}" if a.client_email else "",
        f"telephone {escape(a.client_phone)}" if a.client_phone else "",
    ] if x)
    client = f"<b>{escape(a.client_name)}</b>"
    if a.client_address:
        client += f", of {escape(a.client_address).rstrip('.')}"
    if contact:
        client += f" ({contact})"
    client += " (the “<b>Client</b>”)."
    story += [P(client, st["party"], bulletText="(2)"), Spacer(1, 4.5 * mm)]

    story += [P("The Provider and the Client are individually a “Party” and collectively the “Parties.” "
                "This Agreement sets out the services, fees, timelines and responsibilities agreed between them, "
                "and the Parties agree as follows.", st["body"])]

    # ---- 1. The service -----------------------------------------------
    story += heading("The Service")
    story += sub(f"The Provider shall provide the Client with the professional service known as "
                 f"{strong(a.service_title, 'the service described below')}.")
    deliverables = a.deliverable_list()
    if deliverables:
        story += sub("The scope of work comprises the following deliverables:", space=2 * mm)
        for i, d in enumerate(deliverables, 1):
            story += [P(_text(d), st["item"], bulletText=f"({_letter(i)})"), Spacer(1, 1.4 * mm)]
        story += [Spacer(1, 1 * mm)]
    else:
        story += sub("The scope of work and deliverables are as separately agreed between the Parties in writing.")
    story += sub("The Client will provide all information, materials, approvals, and feedback reasonably needed to "
                 "complete the agreed service.")
    story += sub("Any changes to the scope, price, or deadline require agreement by both Parties.", space=0)

    # ---- 2. Term --------------------------------------------------------
    story += heading("Term")
    duration = (f", a term of {strong(f'{a.term_days} day' + ('s' if a.term_days != 1 else ''))}"
                if a.term_days is not None else "")
    story += sub(f"The service shall begin on {strong(_day(a.start_date), 'the agreed start date')} and is expected "
                 f"to be completed by {strong(_day(a.completion_date), 'the agreed completion date')}"
                 f"{duration}.", space=0)

    # ---- 3. Payment -----------------------------------------------------
    story += heading("Payment")
    basis = f" on a {escape(a.payment_basis_label.lower())} basis" if a.payment_basis_label else ""
    story += sub(f"The agreed fee for the service is {strong(_money(a, a.fee), 'as separately agreed')}"
                 f"{basis}, payable as set out below.", space=2.6 * mm)

    amounts = [("Agreed fee", _money(a, a.fee) or "As separately agreed"),
               ("Deposit / amount due upfront", _money(a, a.deposit) or f"{a.currency} 0.00"),
               ("Balance after deposit", _money(a, a.balance) or "—")]
    fee_table = Table(
        [[P(escape(label), st["cell_b"] if i == 2 else st["cell"]),
          P(escape(value), st["cell_b"] if i == 2 else st["cell"])] for i, (label, value) in enumerate(amounts)],
        colWidths=[(FRAME_W - INDENT) * 0.6, (FRAME_W - INDENT) * 0.4],
    )
    fee_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.5, HAIR),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, HAIR),
        ("BACKGROUND", (0, 2), (-1, 2), WASH),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.5), ("RIGHTPADDING", (0, 0), (-1, -1), 4.5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.6),
    ]))
    fee_table.hAlign = "RIGHT"
    story += [fee_table, Spacer(1, 3.4 * mm)]

    if a.payment_schedule:
        story += sub(f"Payment is due as follows: {_text(a.payment_schedule)}")
    story += sub("The Client agrees to pay the amounts stated above according to the agreed schedule. Additional "
                 "services or charges must be approved by the Client before they are incurred.", space=0)

    # ---- 4. Acceptance ---------------------------------------------------
    story += heading("Client Review and Acceptance")
    story += sub("By signing or electronically accepting this Agreement, the Client confirms that they have "
                 "reviewed and accepted the services, timelines, and payment terms set out above.", space=0)

    # ---- Execution -------------------------------------------------------
    col_w = (FRAME_W - 14 * mm) / 2
    sig_h = 16 * mm

    def mark(kind, value):
        """The signature itself, sitting on the signing line."""
        if kind == "drawn":
            drawn = _data_url_image(value, col_w - 2 * mm, sig_h)
            if drawn:
                return drawn
        if kind == "typed" and value:
            font = _signature_font()
            if font and _font_covers(font, value):
                size = 26
                while size > 13 and pdfmetrics.stringWidth(value, font, size) > col_w - 2 * mm:
                    size -= 1
                return P(escape(value), ParagraphStyle("sig", fontName=font, fontSize=size, leading=size * 1.1,
                                                       textColor=colors.HexColor("#17306b")))
            # A name the script face can't draw is set in the text face
            # (no <i>: the server's TrueType faces have no italic mapped).
            return P(escape(value), ParagraphStyle("sig_plain", fontName=serif, fontSize=14, leading=17,
                                                   textColor=colors.HexColor("#17306b")))
        return Spacer(1, sig_h)

    def block(heading_lines, kind, value, fields):
        signing = Table([[mark(kind, value)]], colWidths=[col_w], rowHeights=[sig_h + 2 * mm])
        signing.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LINEBELOW", (0, 0), (-1, -1), 0.6, INK),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5), ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]))
        cell = [P(line, st["sig_head"]) for line in heading_lines]
        cell += [Spacer(1, 2 * mm), signing, Spacer(1, 1.6 * mm)]
        cell += [P(f"{escape(label)}:&nbsp; {value or '&nbsp;'}", st["sig_line"]) for label, value in fields]
        return cell

    company_role = escape(a.company_signatory_role) if a.company_signatory_role else "Authorised signatory"
    company = block(
        ["SIGNED for and on behalf of", escape(a.provider_name.upper())],
        a.company_signature_kind, a.company_signature,
        [("Name", f"<b>{escape(a.company_signatory_name)}</b>" if a.company_signatory_name else ""),
         ("Title", company_role),
         ("Date", escape(_day(timezone.localtime(a.company_signed_at).date())) if a.company_signed_at else "")],
    )
    client_signed = (f"<b>{escape(a.client_name)}</b>" if a.client_name else "")
    client = block(
        ["SIGNED by the CLIENT", "&nbsp;"],
        a.client_signature_kind, a.client_signature,
        [("Name", client_signed),
         ("Date", escape(_day(timezone.localtime(a.client_signed_at).date())) if a.client_signed_at else "")],
    )

    signatures = Table([[company, "", client]], colWidths=[col_w, 14 * mm, col_w])
    signatures.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    execution = [
        Spacer(1, 7 * mm),
        P("IN WITNESS WHEREOF the Parties have executed this Agreement on the dates stated below.", st["body"]),
        Spacer(1, 7 * mm),
        signatures,
    ]
    story.append(KeepTogether(execution))

    # ---- The electronic signature record ---------------------------------
    if a.client_signed_at:
        when = timezone.localtime(a.client_signed_at)
        how = dict(a.SignatureKind.choices).get(a.client_signature_kind, "electronic")
        record = (f"Electronic signature record — this Agreement was accepted electronically by "
                  f"{escape(a.client_name)} on {when:%d %B %Y} at {when:%H:%M} ({how.lower()} signature)"
                  + (f", from IP address {escape(a.client_signed_ip)}" if a.client_signed_ip else "")
                  + f". Reference {escape(a.reference or '')}.")
        note = Table([[P(record, st["note"])]], colWidths=[FRAME_W])
        note.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.4, HAIR), ("BACKGROUND", (0, 0), (-1, -1), WASH),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story += [Spacer(1, 9 * mm), note]

    # ---- Build ------------------------------------------------------------
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=top_later, bottomMargin=bottom,
        title=f"Professional Service Agreement {a.reference or ''} — {a.client_name}",
        author=a.provider_name, subject="Professional Service Agreement",
    )
    first_frame = Frame(MARGIN_X, bottom, FRAME_W, PAGE_H - top_first - bottom, id="first",
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    later_frame = Frame(MARGIN_X, bottom, FRAME_W, PAGE_H - top_later - bottom, id="later",
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    watermark = WATERMARKS.get(a.status)

    def on_first(c, d):
        if watermark:
            _draw_watermark(c, watermark, serif_bold)
        if header:
            reader, x, w, h = header
            c.drawImage(reader, x, PAGE_H - h, width=w, height=h, mask="auto")
        else:
            _draw_text_letterhead(c, a, fonts, first=True)

    def on_later(c, d):
        if watermark:
            _draw_watermark(c, watermark, serif_bold)
        if header:
            reader, x, w, h = header
            c.drawImage(reader, x, PAGE_H - h, width=w, height=h, mask="auto")
        else:
            _draw_text_letterhead(c, a, fonts, first=False)

    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first_frame], onPage=on_first, autoNextPageTemplate="later"),
        PageTemplate(id="later", frames=[later_frame], onPage=on_later),
    ])
    footer_text = f"{a.reference or 'Professional Service Agreement'}  ·  {a.client_name}  ·  Confidential"
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
        company_signatory_name="Metascholar Limited", company_signatory_role="Director",
        company_signature_kind="typed",
        company_signature="Metascholar", company_signed_at=timezone.now(),
        client_signature_kind="typed", client_signature="Sample Client", client_signed_at=timezone.now(),
    )
