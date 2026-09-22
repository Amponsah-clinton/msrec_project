"""Renders the Peer Review Certificate PDF for one completed ReviewAssignment
-- reviewer_dashboard.account_views.certificate_download (self-serve) and
secretariat_dashboard.views._handle_award_certificate (the Secretariat's
"Award Certificate" button, which is what actually sets certificate_id/
certificate_awarded_at in the first place -- see accounts.models.User for
the equivalent Committee membership certificate) are the only callers.
Only ever called for an assignment with certificate_id set, so callers
must check that themselves before rendering.

Built with reportlab's platypus layer directly, the same approach and
exact colour tokens as committee_dashboard/certificate.py, so a reviewer's
certificate reads as the same product as a committee member's rather than
a differently-branded export.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Same wine/gold palette as templates/certificates/award_certificate.html's
# :root custom properties -- this simpler reportlab rendering (used only
# for the PDF attached to the award email; the dashboard's "Certificate"
# link opens that exact HTML design instead, see certificate_download's
# docstring) is still styled to match rather than reverting to the old
# navy/teal report theme.
WINE = colors.HexColor("#7b0b0d")
GOLD_DEEP = colors.HexColor("#9b6900")
GOLD_LIGHT = colors.HexColor("#f6efdd")
TEXT_MAIN = colors.HexColor("#4c1111")
TEXT_SUB = colors.HexColor("#7a3a3a")
TEXT_FAINT = colors.HexColor("#a98a8a")
BORDER = colors.HexColor("#e9ded0")
GOLD = colors.HexColor("#d2b364")

PAGE_SIZE = landscape(A4)
PAGE_MARGIN = 1.8 * cm


def _styles():
    return {
        "org_name": ParagraphStyle(
            "org_name", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=WINE,
        ),
        "org_sub": ParagraphStyle(
            "org_sub", fontName="Helvetica", fontSize=9, leading=12, textColor=TEXT_FAINT,
        ),
        "eyebrow": ParagraphStyle(
            "eyebrow", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=GOLD_DEEP,
            alignment=1, spaceAfter=6,
        ),
        "cert_sub": ParagraphStyle(
            "cert_sub", fontName="Helvetica", fontSize=10.5, leading=15, textColor=TEXT_SUB,
            alignment=1,
        ),
        "recipient": ParagraphStyle(
            "recipient", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=WINE,
            alignment=1, spaceBefore=16, spaceAfter=6,
        ),
        "body_center": ParagraphStyle(
            "body_center", fontName="Helvetica", fontSize=11, leading=17, textColor=TEXT_MAIN,
            alignment=1,
        ),
        "label": ParagraphStyle(
            "label", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=TEXT_FAINT,
            alignment=1,
        ),
        "value": ParagraphStyle(
            "value", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=WINE,
            alignment=1,
        ),
        "sign_name": ParagraphStyle(
            "sign_name", fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=TEXT_MAIN,
            alignment=1,
        ),
        "sign_title": ParagraphStyle(
            "sign_title", fontName="Helvetica", fontSize=8.5, leading=11, textColor=TEXT_FAINT,
            alignment=1,
        ),
    }


def _border_frame(canvas, doc):
    """Double-rule border that reads as "certificate" rather than "report",
    drawn straight on the canvas rather than as a Table so it doesn't
    consume any flowable width/height budget -- identical treatment to
    committee_dashboard/certificate.py's membership certificate."""
    canvas.saveState()
    outer = 0.9 * cm
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(1.6)
    canvas.rect(outer, outer, PAGE_SIZE[0] - 2 * outer, PAGE_SIZE[1] - 2 * outer)
    inner = outer + 0.14 * cm
    canvas.setStrokeColor(WINE)
    canvas.setLineWidth(0.6)
    canvas.rect(inner, inner, PAGE_SIZE[0] - 2 * inner, PAGE_SIZE[1] - 2 * inner)

    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(TEXT_FAINT)
    canvas.drawCentredString(
        PAGE_SIZE[0] / 2, outer - 0.05 * cm,
        "Verify this certificate's ID with the MSREC Secretariat.",
    )
    canvas.restoreState()


def render_review_certificate_pdf(assignment):
    """Returns the rendered PDF as raw bytes for one completed
    ReviewAssignment that has already been issued a certificate_id."""
    styles = _styles()
    reviewer = assignment.reviewer
    application = assignment.application

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=PAGE_SIZE,
        topMargin=PAGE_MARGIN + 0.6 * cm, bottomMargin=PAGE_MARGIN + 0.6 * cm,
        leftMargin=PAGE_MARGIN + 0.6 * cm, rightMargin=PAGE_MARGIN + 0.6 * cm,
        title=f"MSREC Peer Review Certificate - {assignment.certificate_id}",
    )

    story = []

    story.append(Paragraph("MSREC", styles["org_name"]))
    story.append(Paragraph("Metascholar Research Ethics Committee", styles["org_sub"]))
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER))
    story.append(Spacer(1, 22))

    story.append(Paragraph("CERTIFICATE OF APPRECIATION", styles["eyebrow"]))
    story.append(Paragraph("Presented to", styles["cert_sub"]))
    story.append(Paragraph(reviewer.full_name, styles["recipient"]))

    ref = application.reference_no or f"Application #{application.pk}"
    story.append(Paragraph(
        f"in recognition of your time and expertise in completing an independent ethical "
        f"review for the Metascholar Research Ethics Committee, under reference <b>{ref}</b>. "
        f"Your contribution supports MSREC's commitment to rigorous, independent research "
        f"ethics oversight.",
        styles["body_center"],
    ))
    story.append(Spacer(1, 22))

    meta = Table(
        [[
            [Paragraph("CERTIFICATE ID", styles["label"]), Paragraph(assignment.certificate_id, styles["value"])],
            [Paragraph("AWARDED ON", styles["label"]),
             Paragraph(assignment.certificate_awarded_at.strftime("%d %B %Y") if assignment.certificate_awarded_at else "—", styles["value"])],
        ]],
        colWidths=[doc.width / 2, doc.width / 2],
    )
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GOLD_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.6, GOLD_DEEP),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LINEAFTER", (0, 0), (0, 0), 0.6, GOLD_DEEP),
    ]))
    story.append(meta)
    story.append(Spacer(1, 34))

    sign_row = Table(
        [[
            [HRFlowable(width="70%", thickness=0.8, color=TEXT_SUB, hAlign="CENTER"),
             Spacer(1, 4), Paragraph("Secretariat", styles["sign_name"]), Paragraph("MSREC Secretariat", styles["sign_title"])],
            [HRFlowable(width="70%", thickness=0.8, color=TEXT_SUB, hAlign="CENTER"),
             Spacer(1, 4), Paragraph("Chair", styles["sign_name"]), Paragraph("MSREC Committee Chair", styles["sign_title"])],
        ]],
        colWidths=[doc.width / 2, doc.width / 2],
    )
    sign_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(sign_row)

    doc.build(story, onFirstPage=_border_frame, onLaterPages=_border_frame)
    return buffer.getvalue()
