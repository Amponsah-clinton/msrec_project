"""Renders the Membership Certificate PDF for a confirmed Committee member --
committee_dashboard.account_views.certificate_download is the only caller.
Only ever called for a user with membership_ethics_id set (see
accounts.models.User.approve_role, which is the one place that gets issued),
so callers must check that themselves before rendering.

Built with reportlab's platypus layer directly, the same approach as
reviewer_dashboard/pdf.py, and reusing its exact colour tokens so this reads
as the same product rather than a bolted-on export.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = colors.HexColor("#1b2a4a")
TEAL = colors.HexColor("#159a96")
TEAL_LIGHT = colors.HexColor("#e4f6f5")
TEXT_MAIN = colors.HexColor("#1f2733")
TEXT_SUB = colors.HexColor("#5b6472")
TEXT_FAINT = colors.HexColor("#9aa2af")
BORDER = colors.HexColor("#e6e9ef")
GOLD = colors.HexColor("#b98b2e")

PAGE_SIZE = landscape(A4)
PAGE_MARGIN = 1.8 * cm


def _styles():
    return {
        "org_name": ParagraphStyle(
            "org_name", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=NAVY,
        ),
        "org_sub": ParagraphStyle(
            "org_sub", fontName="Helvetica", fontSize=9, leading=12, textColor=TEXT_FAINT,
        ),
        "eyebrow": ParagraphStyle(
            "eyebrow", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=TEAL,
            alignment=1, spaceAfter=6,
        ),
        "cert_title": ParagraphStyle(
            "cert_title", fontName="Helvetica-Bold", fontSize=28, leading=32, textColor=NAVY,
            alignment=1, spaceAfter=4,
        ),
        "cert_sub": ParagraphStyle(
            "cert_sub", fontName="Helvetica", fontSize=10.5, leading=15, textColor=TEXT_SUB,
            alignment=1,
        ),
        "recipient": ParagraphStyle(
            "recipient", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=NAVY,
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
            "value", fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=NAVY,
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
    consume any flowable width/height budget."""
    canvas.saveState()
    outer = 0.9 * cm
    canvas.setStrokeColor(GOLD)
    canvas.setLineWidth(1.6)
    canvas.rect(outer, outer, PAGE_SIZE[0] - 2 * outer, PAGE_SIZE[1] - 2 * outer)
    inner = outer + 0.14 * cm
    canvas.setStrokeColor(NAVY)
    canvas.setLineWidth(0.6)
    canvas.rect(inner, inner, PAGE_SIZE[0] - 2 * inner, PAGE_SIZE[1] - 2 * inner)

    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(TEXT_FAINT)
    canvas.drawCentredString(
        PAGE_SIZE[0] / 2, outer - 0.05 * cm,
        "Verify this certificate's Membership Ethics ID with the MSREC Secretariat.",
    )
    canvas.restoreState()


def render_membership_certificate_pdf(member):
    """Returns the rendered PDF as raw bytes for one confirmed Committee
    member (an accounts.models.User with membership_ethics_id set)."""
    styles = _styles()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=PAGE_SIZE,
        topMargin=PAGE_MARGIN + 0.6 * cm, bottomMargin=PAGE_MARGIN + 0.6 * cm,
        leftMargin=PAGE_MARGIN + 0.6 * cm, rightMargin=PAGE_MARGIN + 0.6 * cm,
        title=f"MSREC Membership Certificate - {member.membership_ethics_id}",
    )

    story = []

    story.append(Paragraph("MSREC", styles["org_name"]))
    story.append(Paragraph("Metascholar Research Ethics Committee", styles["org_sub"]))
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1, color=BORDER))
    story.append(Spacer(1, 22))

    story.append(Paragraph("CERTIFICATE OF MEMBERSHIP", styles["eyebrow"]))
    story.append(Paragraph("This certifies that", styles["cert_sub"]))
    story.append(Paragraph(member.full_name, styles["recipient"]))

    role_title = (member.committee_profile or {}).get("committeePosition") or member.position or "Committee Member"
    story.append(Paragraph(
        f"has been confirmed as a member of the Metascholar Research Ethics Committee, "
        f"serving as <b>{role_title}</b>, and is recognised as being in good standing "
        f"with MSREC's governing charter and code of research ethics conduct.",
        styles["body_center"],
    ))
    story.append(Spacer(1, 22))

    meta = Table(
        [[
            [Paragraph("MEMBERSHIP ETHICS ID", styles["label"]), Paragraph(member.membership_ethics_id, styles["value"])],
            [Paragraph("CONFIRMED ON", styles["label"]),
             Paragraph(member.membership_confirmed_at.strftime("%d %B %Y") if member.membership_confirmed_at else "—", styles["value"])],
        ]],
        colWidths=[doc.width / 2, doc.width / 2],
    )
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TEAL_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.6, TEAL),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LINEAFTER", (0, 0), (0, 0), 0.6, TEAL),
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
