"""The receipt for one payment against an agreement, as an A4 PDF.

Emailed to the client the moment a payment link is paid, and downloadable
from the agreement's page for any entry in the ledger -- including the
ones staff recorded by hand, which were numbered by the migration that
introduced receipt numbers.

Rendered on demand rather than stored: the receipt number and the payment
row behind it are write-once, so the same bytes come back every time it is
asked for, and there is no file to keep in step with the record. Same
contract as the agreement PDF, whose letterhead, fonts and page frame this
shares -- a receipt should look like it came from the same office as the
agreement it settles.
"""
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle

from . import pdf

PAGE_W, PAGE_H = A4
MARGIN_X = pdf.MARGIN_X
FRAME_W = pdf.FRAME_W

PAID_GREEN = colors.HexColor("#1d7a4c")


def filename(payment):
    return f"{payment.receipt_number or 'receipt'}.pdf"


def _money(currency, value):
    return f"{currency} {value:,.2f}"


def render(payment, settings=None):
    """The receipt as PDF bytes. `payment` is a psa.models.Payment."""
    a = payment.agreement
    sans, sans_bold, serif, serif_bold = pdf._fonts()
    typed = " ".join(str(x or "") for x in [a.client_name, a.client_address, a.service_title, payment.note])
    if not pdf._font_covers(serif, typed) and pdf._font_covers(sans, typed):
        serif, serif_bold = sans, sans_bold
    fonts = (sans, sans_bold, serif, serif_bold)

    header, footer = pdf.letterhead(settings)
    top_first, top_later, bottom = pdf.frame_bounds(header, footer)

    body = ParagraphStyle("body", fontName=serif, fontSize=10, leading=14.4, textColor=pdf.BODY)
    st = {
        "title": ParagraphStyle("title", fontName=serif_bold, fontSize=15.5, leading=19,
                                textColor=pdf.INK, alignment=TA_CENTER),
        "ref": ParagraphStyle("ref", fontName=serif, fontSize=9, leading=12, textColor=pdf.MUTED,
                              alignment=TA_CENTER),
        "body": body,
        "label": ParagraphStyle("label", fontName=serif, fontSize=9.6, leading=12.6, textColor=pdf.MUTED),
        "value": ParagraphStyle("value", fontName=serif, fontSize=9.6, leading=12.6, textColor=pdf.BODY),
        "value_r": ParagraphStyle("value_r", fontName=serif, fontSize=9.6, leading=12.6,
                                  textColor=pdf.BODY, alignment=TA_RIGHT),
        "total": ParagraphStyle("total", fontName=serif_bold, fontSize=13, leading=17, textColor=pdf.INK),
        "total_r": ParagraphStyle("total_r", fontName=serif_bold, fontSize=13, leading=17,
                                  textColor=PAID_GREEN, alignment=TA_RIGHT),
        "note": ParagraphStyle("note", fontName=serif, fontSize=8.2, leading=11, textColor=pdf.MUTED),
    }
    P = Paragraph

    story = []

    # ---- Title ---------------------------------------------------------
    rule = Table([[""]], colWidths=[34 * mm], rowHeights=[0.1])
    rule.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, pdf.INK)]))
    rule.hAlign = "CENTER"
    story += [
        P("OFFICIAL RECEIPT", st["title"]),
        Spacer(1, 2.6 * mm), rule, Spacer(1, 2.6 * mm),
        P(f"Receipt No. {escape(payment.receipt_number or 'pending')}", st["ref"]),
        Spacer(1, 7 * mm),
    ]

    # ---- Who and what --------------------------------------------------
    received_on = payment.paid_on
    rows = [
        ("Received from", escape(a.client_name)),
        ("Date received", escape(f"{received_on.day} {received_on:%B %Y}")),
        ("Payment method", escape(payment.get_method_display())),
        ("Against agreement", escape(a.reference or "")),
    ]
    if a.service_title:
        rows.append(("For", escape(a.service_title)))
    if payment.note:
        rows.append(("Reference", escape(payment.note)))

    table = Table([[P(label, st["label"]), P(value, st["value"])] for label, value in rows],
                  colWidths=[42 * mm, FRAME_W - 42 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 3.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, pdf.HAIR),
    ]))
    story += [table, Spacer(1, 7 * mm)]

    # ---- The amount ------------------------------------------------------
    amount = Table(
        [[P("Amount received", st["total"]), P(_money(a.currency, payment.abs_amount), st["total_r"])]],
        colWidths=[FRAME_W * 0.55, FRAME_W * 0.45],
    )
    amount.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, pdf.HAIR), ("BACKGROUND", (0, 0), (-1, -1), pdf.WASH),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [amount, Spacer(1, 6 * mm)]

    # ---- How the agreement stands after this -----------------------------
    owing = a.amount_owing
    standing = [
        ("Agreed fee", _money(a.currency, a.fee) if a.fee is not None else "As separately agreed"),
        ("Total received to date", _money(a.currency, a.amount_paid)),
        ("Balance outstanding", _money(a.currency, owing) if owing is not None and owing > 0
         else ("Nil - paid in full" if owing is not None else "")),
    ]
    standing_table = Table(
        [[P(escape(label), st["label"]), P(escape(value), st["value_r"])] for label, value in standing],
        colWidths=[FRAME_W * 0.55, FRAME_W * 0.45],
    )
    standing_table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.8),
        ("LINEABOVE", (0, 2), (-1, 2), 0.4, pdf.HAIR),
    ]))
    story += [
        P("How this agreement stands", ParagraphStyle("h", fontName=serif_bold, fontSize=10.4,
                                                      leading=13, textColor=pdf.INK)),
        Spacer(1, 2.4 * mm), standing_table, Spacer(1, 9 * mm),
    ]

    # ---- Provenance -------------------------------------------------------
    request = getattr(payment, "request", None)
    if request is not None:
        when = timezone.localtime(request.paid_at) if request.paid_at else None
        provenance = (
            f"Paid online by card or mobile money on "
            f"{when:%d %B %Y at %H:%M}" if when else "Paid online"
        ) + f". Transaction reference {escape(request.reference)}."
    else:
        recorder = getattr(payment.recorded_by, "full_name", "")
        provenance = ("Recorded against the agreement by "
                      f"{escape(recorder)}" if recorder else "Recorded against the agreement")
        provenance += f" on {timezone.localtime(payment.recorded_at):%d %B %Y}."

    note = Table([[P(f"{provenance} This receipt is issued by {escape(a.provider_name)} and is valid "
                     "without a signature.", st["note"])]], colWidths=[FRAME_W])
    note.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.4, pdf.HAIR), ("BACKGROUND", (0, 0), (-1, -1), pdf.WASH),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(note)

    # ---- Build -------------------------------------------------------------
    from io import BytesIO
    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X,
        topMargin=top_later, bottomMargin=bottom,
        title=f"Receipt {payment.receipt_number or ''} - {a.client_name}",
        author=a.provider_name, subject=f"Receipt for agreement {a.reference}",
    )
    frame = Frame(MARGIN_X, bottom, FRAME_W, PAGE_H - top_first - bottom, id="only",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)

    def on_page(c, d):
        if header:
            reader, x, w, h = header
            c.drawImage(reader, x, PAGE_H - h, width=w, height=h, mask="auto")
        else:
            pdf._draw_text_letterhead(c, a, fonts, first=True)

    doc.addPageTemplates([PageTemplate(id="only", frames=[frame], onPage=on_page)])
    footer_text = f"{payment.receipt_number or ''}  ·  {a.reference or ''}  ·  {a.client_name}"
    doc.build(story, canvasmaker=lambda *args, **kw: pdf._Canvas(
        *args, footer=footer, footer_text=footer_text, sans=sans, **kw))
    return buffer.getvalue()
