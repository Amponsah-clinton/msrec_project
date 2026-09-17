"""Renders a completed Ethical Review Assessment Form (ReviewAssignment)
as a downloadable PDF -- reviewer_dashboard.views.review_application_pdf
is the only caller. Built with reportlab's platypus layer directly
(Table/Paragraph/SimpleDocTemplate) rather than converting the HTML
template, since that gives full control over pagination and keeps this
independent of a system-level HTML-to-PDF binary (wkhtmltopdf/Cairo)
that may not be installed wherever this runs.

Colours are the exact hex values from static/dashboard/css/style.css's
:root palette -- solid fills only, no gradients, so a printed/exported
report looks like it belongs to the same product as the web page it came
from rather than a generic "reporting tool" export.
"""
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# Same tokens as static/dashboard/css/style.css :root (light theme) --
# kept as plain hex here since reportlab has no notion of CSS variables.
NAVY = colors.HexColor("#1b2a4a")
TEAL = colors.HexColor("#159a96")
TEAL_LIGHT = colors.HexColor("#e4f6f5")
GREEN = colors.HexColor("#1fa971")
GREEN_LIGHT = colors.HexColor("#e7f7f0")
ORANGE = colors.HexColor("#e07a1f")
ORANGE_LIGHT = colors.HexColor("#fdf0e2")
RED = colors.HexColor("#e0483f")
RED_LIGHT = colors.HexColor("#fdeceb")
PURPLE = colors.HexColor("#7c5cf0")
PURPLE_LIGHT = colors.HexColor("#f0ecfe")
GRAY = colors.HexColor("#6b7280")
GRAY_LIGHT = colors.HexColor("#eef1f5")
TEXT_MAIN = colors.HexColor("#1f2733")
TEXT_SUB = colors.HexColor("#5b6472")
TEXT_FAINT = colors.HexColor("#9aa2af")
BORDER = colors.HexColor("#e6e9ef")
WHITE = colors.white

_BADGE_COLORS = {
    "green": (GREEN, GREEN_LIGHT),
    "orange": (ORANGE, ORANGE_LIGHT),
    "red": (RED, RED_LIGHT),
    "teal": (TEAL, TEAL_LIGHT),
    "purple": (PURPLE, PURPLE_LIGHT),
    "gray": (GRAY, GRAY_LIGHT),
}

PAGE_MARGIN = 2 * cm


def _styles():
    return {
        "eyebrow": ParagraphStyle(
            "eyebrow", fontName="Helvetica-Bold", fontSize=8.5, leading=11,
            textColor=TEXT_FAINT, spaceAfter=2, tracking=0.6,
        ),
        "doc_title": ParagraphStyle(
            "doc_title", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY,
        ),
        "org_name": ParagraphStyle(
            "org_name", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY,
        ),
        "org_sub": ParagraphStyle(
            "org_sub", fontName="Helvetica", fontSize=8.5, leading=11, textColor=TEXT_FAINT,
        ),
        "meta_right": ParagraphStyle(
            "meta_right", fontName="Helvetica", fontSize=9, leading=13, textColor=TEXT_SUB, alignment=2,
        ),
        "section_title": ParagraphStyle(
            "section_title", fontName="Helvetica-Bold", fontSize=12, leading=15,
            textColor=NAVY, spaceBefore=18, spaceAfter=8,
        ),
        "label": ParagraphStyle(
            "label", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=TEXT_SUB,
        ),
        "value": ParagraphStyle(
            "value", fontName="Helvetica", fontSize=10, leading=14, textColor=TEXT_MAIN,
        ),
        "body": ParagraphStyle(
            "body", fontName="Helvetica", fontSize=10, leading=15, textColor=TEXT_MAIN,
        ),
        "body_muted": ParagraphStyle(
            "body_muted", fontName="Helvetica-Oblique", fontSize=9.5, leading=14, textColor=TEXT_FAINT,
        ),
        "checklist_item": ParagraphStyle(
            "checklist_item", fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=TEXT_MAIN,
        ),
        "chip": ParagraphStyle(
            "chip", fontName="Helvetica-Bold", fontSize=9, leading=12, alignment=1,
        ),
        "decision_title": ParagraphStyle(
            "decision_title", fontName="Helvetica-Bold", fontSize=13, leading=17,
        ),
    }


def _chip(text, badge_key, styles):
    color, light = _BADGE_COLORS.get(badge_key, (GRAY, GRAY_LIGHT))
    style = ParagraphStyle("chip_dyn", parent=styles["chip"], textColor=color)
    table = Table([[Paragraph(text, style)]], colWidths=[None])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), light),
        ("BOX", (0, 0), (-1, -1), 0.6, color),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _kv_grid(pairs, styles, col_width):
    """Two-column label/value grid (Study Title, Reference No, ...) laid
    out as a borderless 4-cell-per-row table -- same "field label above
    value" shape as the web page's .field-grid, just in table form."""
    rows = []
    for i in range(0, len(pairs), 2):
        row = []
        for label, value in pairs[i:i + 2]:
            cell = [Paragraph(label.upper(), styles["label"]), Paragraph(value or "&mdash;", styles["value"])]
            row.append(cell)
        if len(row) == 1:
            row.append("")
        rows.append(row)

    # Each "cell" above is a list of flowables -- wrap each in its own
    # mini-table so multi-line values don't collide with the label.
    table_rows = []
    for row in rows:
        table_rows.append([
            cell if cell == "" else Table([[f] for f in cell], colWidths=[col_width])
            for cell in row
        ])
    t = Table(table_rows, colWidths=[col_width + 6, col_width + 6])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    return t


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.6)
    canvas.line(PAGE_MARGIN, 1.4 * cm, A4[0] - PAGE_MARGIN, 1.4 * cm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(TEXT_FAINT)
    canvas.drawString(PAGE_MARGIN, 1.0 * cm, "MSREC — Metascholar Research Ethics Committee · Confidential reviewer document")
    canvas.drawRightString(A4[0] - PAGE_MARGIN, 1.0 * cm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def render_assessment_pdf(assignment):
    """Returns the rendered PDF as raw bytes for one Completed
    ReviewAssignment. Callers only need this if assignment.status ==
    COMPLETED -- an in-progress assessment has nothing to export yet."""
    styles = _styles()
    application = assignment.application
    applicant = application.applicant

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=PAGE_MARGIN, bottomMargin=2.1 * cm,
        leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        title=f"Ethical Review Assessment - {application.reference_no or 'MSREC'}",
    )

    story = []

    # ---------------- Header ----------------
    header = Table(
        [[
            [Paragraph("MSREC", styles["org_name"]), Paragraph("Metascholar Research Ethics Committee", styles["org_sub"])],
            [
                Paragraph(application.reference_no or "Reference pending", styles["meta_right"]),
                Paragraph(f"Generated {timezone.localtime():%d %b %Y, %I:%M %p}", styles["meta_right"]),
            ],
        ]],
        colWidths=[10 * cm, doc.width - 10 * cm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceAfter=14))

    story.append(Paragraph("Ethical Review Assessment Report", styles["doc_title"]))
    story.append(Spacer(1, 14))

    # ---------------- Application summary ----------------
    story.append(Paragraph("Application Summary", styles["section_title"]))
    col_w = (doc.width - 20) / 2
    story.append(_kv_grid([
        ("Study Title", application.title),
        ("Review Pathway", application.review_type or "Not specified"),
        ("Principal Investigator", applicant.full_name),
        ("Institution", applicant.institution or "Not provided"),
        ("Submitted", application.submitted_at.strftime("%d %b %Y") if application.submitted_at else "—"),
        ("Reviewer", assignment.reviewer.full_name),
    ], styles, col_w))

    # ---------------- Reviewer declaration ----------------
    story.append(Paragraph("Reviewer Declaration", styles["section_title"]))
    coi_row = Table(
        [[
            Paragraph("CONFLICT OF INTEREST", styles["label"]),
            _chip("Potential conflict declared" if assignment.coi_has_conflict else "None declared",
                  "orange" if assignment.coi_has_conflict else "green", styles),
        ]],
        colWidths=[col_w, None],
    )
    coi_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (0, 0), 0)]))
    story.append(coi_row)
    if assignment.coi_has_conflict and assignment.coi_details:
        story.append(Spacer(1, 6))
        story.append(Paragraph(assignment.coi_details.replace("\n", "<br/>"), styles["body"]))
    story.append(Spacer(1, 10))
    confid_row = Table(
        [[Paragraph("CONFIDENTIALITY", styles["label"]), _chip("Confirmed", "green", styles)]],
        colWidths=[col_w, None],
    )
    confid_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (0, 0), 0)]))
    story.append(confid_row)

    # ---------------- Ethical review checklist ----------------
    story.append(Paragraph("Ethical Review Checklist", styles["section_title"]))
    checklist_data = [["#", "Assessment Area", "Outcome"]]
    row_styles = []
    for i, row in enumerate(assignment.checklist_rows, start=1):
        checklist_data.append([
            str(i),
            Paragraph(row["label"], styles["checklist_item"]),
            _chip(row["value_label"], row["badge"], styles),
        ])
        row_styles.append(("BACKGROUND", (0, i), (-1, i), WHITE if i % 2 else colors.HexColor("#f7f8fa")))

    checklist_table = Table(checklist_data, colWidths=[1.1 * cm, doc.width - 1.1 * cm - 4.2 * cm, 4.2 * cm], repeatRows=1)
    checklist_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, BORDER),
        *row_styles,
    ]))
    story.append(checklist_table)

    # ---------------- Reviewer comments ----------------
    story.append(Paragraph("Reviewer Comments", styles["section_title"]))
    for label, value in [
        ("Key ethical concerns or required revisions", assignment.key_concerns),
        ("Additional comments / recommendations", assignment.review_notes),
        ("Comments on additional documents", assignment.documents_comment),
    ]:
        story.append(Paragraph(label.upper(), styles["label"]))
        story.append(Spacer(1, 2))
        story.append(Paragraph((value or "None recorded.").replace("\n", "<br/>"), styles["body"]))
        story.append(Spacer(1, 10))

    # ---------------- Recommendation ----------------
    decision_color, decision_light = _BADGE_COLORS.get(assignment.recommendation_badge, (GRAY, GRAY_LIGHT))
    decision_block = [[Paragraph("RECOMMENDATION TO THE SECRETARIAT", styles["label"])]]
    decision_block.append([Paragraph(assignment.get_recommendation_display() or "Not recorded",
                                      ParagraphStyle("decision", parent=styles["decision_title"], textColor=decision_color))])
    if assignment.recommendation_reason:
        decision_block.append([Paragraph(assignment.recommendation_reason.replace("\n", "<br/>"), styles["body"])])

    decision_table = Table(decision_block, colWidths=[doc.width])
    decision_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), decision_light),
        ("BOX", (0, 0), (-1, -1), 0.8, decision_color),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (0, 0), 12),
        ("BOTTOMPADDING", (-1, -1), (-1, -1), 12),
        ("TOPPADDING", (0, 1), (0, -1), 4),
        ("BOTTOMPADDING", (0, 1), (0, -2), 4),
    ]))
    story.append(KeepTogether([Paragraph("Recommendation", styles["section_title"]), decision_table]))

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.6, color=BORDER, spaceAfter=8))
    completed_at = assignment.completed_at.strftime("%d %b %Y at %I:%M %p") if assignment.completed_at else "—"
    story.append(Paragraph(
        f"This assessment was submitted by {assignment.reviewer.full_name} on {completed_at} "
        f"and cannot be edited. It has been recorded against {application.reference_no or 'this application'} "
        f"in the MSREC review system.",
        styles["body_muted"],
    ))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
