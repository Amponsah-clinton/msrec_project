"""The applicant's downloadable record of a reviewer's requested changes --
backs the "Reviewer Comments" block and its "Download as PDF" button on
the Revisions Required page (templates/dashboards/applicant/
application-revisions.html).

Reuses the same MSREC letterhead/footer machinery as approval_documents.
py's approval letter (this is the same kind of "official record the
applicant can keep" PDF, just built from Application.revision_comment
instead of an approval template) rather than duplicating that layout code.
"""
import re
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Frame, ListFlowable, ListItem, PageTemplate, Paragraph, Spacer
from reportlab.platypus import BaseDocTemplate

from .approval_documents import (
    BODY, COMMITTEE_NAME, INK, INK_SOFT, LETTER_H, LETTER_W, MARGIN_X, _NumberedCanvas, _draw_letterhead, _esc, _site,
)

# Matches one "N. <text>" line -- exactly the shape secretariat_dashboard.
# views._compose_revision_comment / admin_dashboard.views write into
# Application.revision_comment. Anything before the first numbered line is
# treated as a free-text intro note; a comment with no numbering at all
# (the plainer admin_dashboard path) ends up entirely as that note.
_ITEM_RE = re.compile(r"^\d+\.\s*(.+)$")


def revision_comments_filename(application):
    ref = (application.reference_no or "draft").replace("/", "-")
    return f"MSREC-Reviewer-Comments-{ref}.pdf"


def revision_comment_parts(application):
    """(note, items) parsed from Application.revision_comment -- shared by
    the PDF below and available to any template that wants the same
    structured breakdown instead of one linebreaksbr blob."""
    raw = (application.revision_comment or "").strip()
    if not raw:
        return "", []
    note_lines, items = [], []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        match = _ITEM_RE.match(line)
        if match:
            items.append(match.group(1))
        elif not items:
            note_lines.append(line)
    return " ".join(note_lines), items


def render_revision_comments_pdf(application):
    """One-page PDF of the reviewer comments behind this application's
    current revision request. Rendered on demand from Application.
    revision_comment, never stored."""
    site = _site()
    note, items = revision_comment_parts(application)

    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=22 * mm, bottomMargin=22 * mm,
        title=f"Reviewer Comments - {application.reference_no or application.title}", author=COMMITTEE_NAME,
    )
    frame = Frame(
        MARGIN_X, 20 * mm, LETTER_W - 2 * MARGIN_X, LETTER_H - 44 * mm - 20 * mm, id="main",
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
    )
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=lambda c, d: _draw_letterhead(c, site))])

    styles = {
        "heading": ParagraphStyle("heading", fontName="Times-Bold", fontSize=17, leading=21, textColor=INK, spaceAfter=10),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=9.5, leading=14, textColor=INK_SOFT, spaceAfter=18),
        "note": ParagraphStyle("note", fontName="Times-Roman", fontSize=11, leading=16, textColor=BODY, spaceAfter=12),
        "item": ParagraphStyle("item", fontName="Times-Roman", fontSize=11, leading=16.5, textColor=BODY, spaceAfter=8),
        "footer_note": ParagraphStyle("footer_note", fontName="Helvetica-Oblique", fontSize=9.5, leading=14, textColor=INK_SOFT),
    }

    requested = (
        f" &middot; Requested {application.revision_requested_at.strftime('%d %B %Y').lstrip('0')}"
        if application.revision_requested_at else ""
    )
    story = [
        Paragraph("Reviewer Comments", styles["heading"]),
        Paragraph(
            f"{_esc(application.title)}<br/>{_esc(application.reference_no or 'Reference pending')}{requested}",
            styles["meta"],
        ),
    ]
    if note:
        story.append(Paragraph(_esc(note), styles["note"]))
    if items:
        story.append(ListFlowable(
            [ListItem(Paragraph(_esc(item), styles["item"]), leftIndent=14) for item in items],
            bulletType="1", bulletFormat="%s.", bulletFontName="Times-Roman", bulletFontSize=11,
            leftIndent=14, bulletColor=INK,
        ))
    if not note and not items:
        story.append(Paragraph(
            "No detailed comments were recorded for this revision request. Contact the Secretariat for the "
            "full feedback.",
            styles["note"],
        ))
    story.append(Spacer(1, 14 * mm))
    story.append(Paragraph(
        "Address each point above, then resubmit from your MSREC dashboard — no review fee is charged again.",
        styles["footer_note"],
    ))

    footer_text = f"{COMMITTEE_NAME}  ·  Reviewer Comments  ·  {application.reference_no or ''}"
    doc.build(story, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, footer_text=footer_text, footer_image=None, **k))
    return buffer.getvalue()
