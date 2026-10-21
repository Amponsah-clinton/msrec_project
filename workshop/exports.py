"""CSV and PDF exports of a workshop's registrations (the Registrations
tab's Export buttons). Both are built from the same rows, so the two files
always agree with each other and with what was on screen.
"""
import csv
import os
from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.utils.text import slugify

from .models import WorkshopRegistration

PS = WorkshopRegistration.PaymentStatus


def _when(dt, with_time=True):
    if not dt:
        return ""
    return timezone.localtime(dt).strftime("%d %b %Y %H:%M" if with_time else "%d %b %Y").lstrip("0")


def certificate_label(reg):
    if not reg.wants_certificate:
        return "No certificate"
    return "Required" if reg.certificate_required_at_signup else "Wants certificate"






def filename(ws, ext):
    return f"msrec-{slugify(ws.title)[:60] or 'workshop'}-registrations-{timezone.localdate().isoformat()}.{ext}"


# ---------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------

CSV_HEADER = [
    "No.", "Name", "Institution", "Email", "Phone", "SMS Number",
    "Certificate", "Payment Status", "Amount", "Currency", "Paid On",
    "Registered On", "Meeting Link Sent", "Materials Sent", "Last Messaged",
    "Approved", "Documents Sent", "Certificate Ref", "Comments",
]


def csv_response(ws, regs):
    from notifications import sms

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename(ws, "csv")}"'
    # A BOM so Excel reads names with accents (é, ɛ, ɔ ...) correctly.
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(CSV_HEADER)
    for i, r in enumerate(regs, start=1):
        writer.writerow([
            i, r.name, r.institution, r.email, r.phone, sms.clean_phone(r.phone),
            certificate_label(r), r.get_payment_status_display() if r.wants_certificate else "",
            r.amount if r.wants_certificate and r.amount else "", r.currency if r.wants_certificate else "",
            _when(r.paid_at), _when(r.created_at),
            _when(r.meeting_link_sent_at), _when(r.materials_sent_at), _when(r.message_sent_at),
            _when(r.approved_at), _when(r.documents_sent_at), r.certificate_ref, r.comments,
        ])
    return response


# ---------------------------------------------------------------------
# PDF -- a formal participant register
# ---------------------------------------------------------------------
# Laid out like a document a secretariat files, not a dashboard: a quiet
# letterhead, a serif title, label/value particulars, one line of totals,
# a ruled table with no fills, and a sign-off block. Ink is near-black and
# grey; the only colour is the logo.

_FONT_CANDIDATES = {
    "sans": [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
    ],
    "serif": [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
        ("/usr/share/fonts/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/dejavu/DejaVuSerif-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"),
        ("C:/Windows/Fonts/georgia.ttf", "C:/Windows/Fonts/georgiab.ttf"),
        ("C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/timesbd.ttf"),
        ("/Library/Fonts/Georgia.ttf", "/Library/Fonts/Georgia Bold.ttf"),
    ],
}
_BUILTIN = {"sans": ("Helvetica", "Helvetica-Bold"), "serif": ("Times-Roman", "Times-Bold")}


def _fonts():
    """{"sans": (regular, bold), "serif": (regular, bold)} -- Unicode
    TrueType faces where the server has them, so names like "Ɔsɛi" print
    properly; ReportLab's built-in Latin-only faces otherwise."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    registered = pdfmetrics.getRegisteredFontNames()
    out = {}
    for family, candidates in _FONT_CANDIDATES.items():
        name, bold = f"Ws{family.title()}", f"Ws{family.title()}Bold"
        if name in registered:
            out[family] = (name, bold)
            continue
        out[family] = _BUILTIN[family]
        for regular_path, bold_path in candidates:
            if os.path.exists(regular_path) and os.path.exists(bold_path):
                try:
                    pdfmetrics.registerFont(TTFont(name, regular_path))
                    pdfmetrics.registerFont(TTFont(bold, bold_path))
                    out[family] = (name, bold)
                    break
                except Exception:
                    continue
    return out


_LOGO_CACHE = {}


def _small_logo(path):
    """The logo scaled to 240px, as PNG bytes. The original is ~470 KB at
    788px; embedded as-is it would make every list export ~0.8 MB to show
    a small mark. Scaled once, then reused."""
    if path in _LOGO_CACHE:
        return BytesIO(_LOGO_CACHE[path]) if _LOGO_CACHE[path] else None
    data = None
    if os.path.exists(path):
        try:
            from PIL import Image as PILImage

            with PILImage.open(path) as im:
                im.thumbnail((240, 240))
                out = BytesIO()
                im.save(out, format="PNG", optimize=True)
                data = out.getvalue()
        except Exception:
            with open(path, "rb") as fh:
                data = fh.read()
    _LOGO_CACHE[path] = data
    return BytesIO(data) if data else None


def fee_status(reg):
    """Plain words for the register: Paid / Outstanding / Failed / Free / —."""
    if not reg.wants_certificate:
        return "—"
    return {
        PS.SUCCESS: "Paid", PS.PENDING: "Outstanding", PS.FAILED: "Failed",
    }.get(reg.payment_status, "No fee")


def pdf_response(ws, regs, group_label="", prepared_by=""):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (
        BaseDocTemplate, Frame, Image, KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    )

    fonts = _fonts()
    SANS, SANS_B = fonts["sans"]
    SERIF, SERIF_B = fonts["serif"]

    INK = colors.HexColor("#1a1a1a")       # body text
    GREY = colors.HexColor("#5f6368")      # secondary text
    FAINT = colors.HexColor("#8c9096")     # labels, footer
    RULE_DARK = colors.HexColor("#1a1a1a")
    RULE = colors.HexColor("#c9ccd1")
    HAIR = colors.HexColor("#e3e5e8")

    page_size = landscape(A4)
    margin = 16 * mm
    width = page_size[0] - 2 * margin
    now = timezone.localtime()
    regs = list(regs)

    def style(name, font, size, color=INK, leading=None, **kw):
        return ParagraphStyle(name, fontName=font, fontSize=size, textColor=color,
                              leading=leading or round(size * 1.32, 1), **kw)

    st = {
        "org": style("org", SANS_B, 8.5, INK, 10.5),
        "org_sub": style("orgs", SANS, 7.5, GREY, 9.5),
        "doc": style("doc", SANS_B, 8, INK, 10, alignment=TA_RIGHT),
        "doc_sub": style("docs", SANS, 7.5, GREY, 9.5, alignment=TA_RIGHT),
        "label": style("lbl", SANS, 6.8, FAINT, 9),
        "value": style("val", SANS, 9, INK, 11.5),
        "fig": style("fig", SERIF_B, 13, INK, 15),
        "fig_l": style("figl", SANS, 6.8, GREY, 8.5),
        "th": style("th", SANS_B, 7, INK, 9),
        "th_r": style("thr", SANS_B, 7, INK, 9, alignment=TA_RIGHT),
        "td": style("td", SANS, 8.2, INK, 10.6),
        "td_b": style("tdb", SANS_B, 8.4, INK, 10.6),
        "td_sub": style("tds", SANS, 7, GREY, 8.8),
        "td_r": style("tdr", SANS, 8.2, INK, 10.6, alignment=TA_RIGHT),
        "td_n": style("tdn", SANS, 7.6, FAINT, 10.6),
        "note": style("note", SANS, 7.6, GREY, 10),
    }
    title_size = 17 if len(ws.title) <= 70 else 14.5 if len(ws.title) <= 140 else 12.5
    st["title"] = style("title", SERIF_B, title_size, INK, round(title_size * 1.22, 1))

    def para(text, key="td"):
        return Paragraph(escape(str(text if text is not None else "")), st[key])

    story = []

    # ---- letterhead: logo + body on the left, document name on the right ----
    logo_file = _small_logo(os.path.join(settings.BASE_DIR, "static", "assets", "img", "MSREC_LOGO.png"))
    org = [para("Metascholar Research Ethics Committee", "org"),
           para("Established under Metascholar Limited  ·  Ghana", "org_sub")]
    doc_id = [para("PARTICIPANT REGISTER", "doc"),
              para(f"Prepared {now.strftime('%d %B %Y').lstrip('0')}", "doc_sub")]
    if logo_file:
        lh = Table([[Image(logo_file, width=11 * mm, height=11 * mm, kind="proportional"), org, doc_id]],
                   colWidths=[14 * mm, width * 0.55, width * 0.45 - 14 * mm])
    else:
        lh = Table([[org, doc_id]], colWidths=[width * 0.55, width * 0.45])
    lh.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, 0), (-1, 0), 1.1, RULE_DARK),
    ]))
    story += [lh, Spacer(1, 7 * mm)]

    # ---- title + particulars ----
    story += [Paragraph(escape(ws.title), st["title"]), Spacer(1, 4 * mm)]

    when = ""
    if ws.starts_at:
        start = timezone.localtime(ws.starts_at)
        when = start.strftime("%A %d %B %Y, %I:%M %p").replace(" 0", " ")
        if ws.ends_at:
            end = timezone.localtime(ws.ends_at)
            when += " – " + (end.strftime("%I:%M %p").lstrip("0") if end.date() == start.date()
                             else end.strftime("%d %B %Y, %I:%M %p").lstrip("0"))
    particulars = [
        ("DATE", when or "Not set"),
        ("VENUE", ws.location or "Not set"),
        ("LIST", group_label or "All registrations"),
        ("PREPARED", f"{now.strftime('%d %B %Y, %I:%M %p').lstrip('0')}" + (f" by {prepared_by}" if prepared_by else "")),
    ]
    cells = [[para(label, "label"), para(value, "value")] for label, value in particulars]
    grid = Table(
        [cells[0] + cells[1], cells[2] + cells[3]],
        colWidths=[19 * mm, width / 2 - 19 * mm, 22 * mm, width / 2 - 22 * mm],
    )
    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (0, -1), 3), ("TOPPADDING", (2, 0), (2, -1), 3),
    ]))
    story += [grid, Spacer(1, 6 * mm)]

    # ---- totals: one ruled line, no boxes ----
    paid = sum(1 for r in regs if r.is_paid)
    owing = sum(1 for r in regs if r.payment_outstanding)
    wants = sum(1 for r in regs if r.wants_certificate)
    received = sum((r.amount for r in regs if r.is_paid), 0)
    figures = [
        (str(len(regs)), "Participants listed"),
        (str(wants), "Certificate requested"),
        (str(paid), "Fee paid"),
        (str(owing), "Fee outstanding"),
        (f"{ws.fee_currency} {received:,.2f}", "Fees received"),
    ]
    fig_table = Table(
        [[[para(v, "fig"), para(l, "fig_l")] for v, l in figures]],
        colWidths=[width / len(figures)] * len(figures),
    )
    fig_table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, RULE),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, RULE),
        ("LINEAFTER", (0, 0), (-2, 0), 0.5, HAIR),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (1, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [fig_table, Spacer(1, 7 * mm)]

    # ---- the register ----
    cols = [
        ("No.", 10, "th"), ("Participant", 66, "th"), ("Email", 58, "th"), ("Telephone", 31, "th"),
        ("Certificate", 22, "th"), ("Fee", 20, "th"), (f"Amount ({ws.fee_currency})", 22, "th_r"),
        ("Registered", 22, "th"),
    ]
    scale = width / (sum(c[1] for c in cols) * mm)
    widths = [c[1] * mm * scale for c in cols]
    data = [[para(label.upper() if i else label.upper(), key) for i, (label, _, key) in enumerate(cols)]]
    for n, r in enumerate(regs, start=1):
        who = [para(r.name, "td_b")]
        if r.institution:
            who.append(para(r.institution, "td_sub"))
        amount = f"{r.amount:,.2f}" if r.wants_certificate and r.amount else "—"
        data.append([
            para(n, "td_n"), who, para(r.email), para(r.phone or "—"),
            para("Required" if r.wants_certificate and r.certificate_required_at_signup
                 else "Yes" if r.wants_certificate else "No"),
            para(fee_status(r)), para(amount, "td_r"),
            para(_when(r.created_at, with_time=False)),
        ])
    if not regs:
        data.append([para(""), para("No participants in this list.", "td_sub")] + [""] * (len(cols) - 2))

    register = Table(data, colWidths=widths, repeatRows=1)
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
        ("TOPPADDING", (0, 0), (-1, 0), 5), ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("TOPPADDING", (0, 1), (-1, -1), 3.6), ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        # Formal "book" rules: heavy above and below the header, hairlines between rows,
        # and a closing rule under the last row.
        ("LINEABOVE", (0, 0), (-1, 0), 0.9, RULE_DARK),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE_DARK),
        ("LINEBELOW", (0, 1), (-1, -2), 0.35, HAIR),
        ("LINEBELOW", (0, -1), (-1, -1), 0.9, RULE_DARK),
    ]
    if not regs:
        commands.append(("SPAN", (1, 1), (-1, 1)))
    register.setStyle(TableStyle(commands))
    story.append(register)

    # ---- notes and sign-off ----
    def field(value=""):
        return para(value, "value") if value else ""

    # Four writing lines with their captions beneath, separated by real
    # gaps (a cell's underline runs the full cell width, padding included).
    gap = 12 * mm
    line_w = (width - 3 * gap) / 4
    sign_rule = Table(
        [[field(prepared_by), "", "", "", "", "", ""],
         [para("Prepared by", "label"), "", para("Signature and date", "label"), "",
          para("Checked by", "label"), "", para("Signature and date", "label")]],
        colWidths=[line_w, gap, line_w, gap, line_w, gap, line_w],
        rowHeights=[12 * mm, None],
    )
    sign_rule.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 3), ("TOPPADDING", (0, 1), (-1, 1), 3),
        ("LINEBELOW", (0, 0), (0, 0), 0.5, GREY), ("LINEBELOW", (2, 0), (2, 0), 0.5, GREY),
        ("LINEBELOW", (4, 0), (4, 0), 0.5, GREY), ("LINEBELOW", (6, 0), (6, 0), 0.5, GREY),
    ]))
    story.append(KeepTogether([
        Spacer(1, 6 * mm),
        para("Fee status reflects payment records at the time this register was prepared. "
             "Certificates are issued only to participants whose fee, where one applies, has been received. "
             "This register contains personal data and is to be handled in line with the MSREC Privacy Policy.", "note"),
        Spacer(1, 8 * mm),
        sign_rule,
    ]))

    footer_title = ws.title if len(ws.title) <= 80 else ws.title[:77].rstrip() + "…"

    class _Canvas(rl_canvas.Canvas):
        """Running footer with a true "Page X of Y", drawn once every page exists."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for n, state in enumerate(self._saved, start=1):
                self.__dict__.update(state)
                y = 9 * mm
                self.setStrokeColor(RULE)
                self.setLineWidth(0.4)
                self.line(margin, y + 4 * mm, page_size[0] - margin, y + 4 * mm)
                self.setFillColor(FAINT)
                self.setFont(SANS, 6.8)
                self.drawString(margin, y, f"MSREC  ·  Participant Register  ·  {footer_title}")
                self.drawRightString(page_size[0] - margin, y, f"Confidential   ·   Page {n} of {total}")
                super().showPage()
            super().save()

    buffer = BytesIO()
    top, bottom = 13 * mm, 18 * mm
    doc = BaseDocTemplate(
        buffer, pagesize=page_size, leftMargin=margin, rightMargin=margin,
        topMargin=top, bottomMargin=bottom,
        title=f"Participant Register: {ws.title}", author="Metascholar Research Ethics Committee",
    )
    # No inner frame padding, so the title, figures, table and notes all
    # start on the same left edge as the letterhead rule.
    frame = Frame(margin, bottom, width, page_size[1] - top - bottom,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="register", frames=[frame])])
    doc.build(story, canvasmaker=_Canvas)

    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename(ws, "pdf")}"'
    return response
