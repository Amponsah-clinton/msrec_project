"""Renders a full Application record as a downloadable PDF -- the
Secretariat/Admin "Download PDF" button on application_detail.html is the
only caller. Same reportlab platypus approach, same NAVY/TEAL palette and
building blocks (_kv_grid, _chip, header/footer) as reviewer_dashboard/pdf.py
(render_assessment_pdf) -- one visual language for every document this
system exports, rather than each feature growing its own look.

Application.form_data is a ~90-field free-form JSON blob (see
Application's docstring) that varies a lot by study type, so this can't
hand-place every field the way a fixed form could. Instead it surfaces the
handful of fields staff always care about in named sections (Research
Info, PI, Research Team, Documents, Revision History, Decision,
Declaration), then dumps everything else into a final "Additional
Details" section -- humanized and type-aware (tag lists become
comma-joined readable text, not a Python list's repr) rather than a raw
key/value printout, and with whatever already appeared in a named section
above excluded so nothing repeats twice on the page.
"""
import logging
import re
from io import BytesIO

from django.utils import timezone
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

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
BLUE = colors.HexColor("#2f6fed")
BLUE_LIGHT = colors.HexColor("#eaf1fd")
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
    "blue": (BLUE, BLUE_LIGHT),
    "gray": (GRAY, GRAY_LIGHT),
}

_STATUS_BADGE = {
    "submitted": ("New", "orange"),
    "under_review": ("Under Review", "blue"),
    "with_committee": ("With Committee", "purple"),
    "revisions_required": ("Revisions Requested", "red"),
    "approved": ("Approved", "green"),
    "not_approved": ("Not Approved", "red"),
}

PAGE_MARGIN = 2 * cm

logger = logging.getLogger(__name__)


def _is_mergeable_pdf(doc_item):
    """Whether an uploaded-documents entry looks like a PDF worth
    appending as real pages rather than just naming in the list above --
    Word/image/other uploads have no reliable, dependency-free way to
    become PDF pages here, so they stay a filename reference only."""
    if not isinstance(doc_item, dict):
        return False
    content_type = (doc_item.get("content_type") or "").lower()
    if content_type == "application/pdf":
        return True
    name = (doc_item.get("name") or "").lower()
    return name.endswith(".pdf")

# Same camelCase -> "Camel Case" treatment as secretariat_dashboard's
# humanize_key template filter, duplicated here (not imported) so this
# module has no dependency on a specific dashboard app -- both
# secretariat_dashboard and admin_dashboard call render_application_pdf.
_ACRONYMS = {
    "pi": "PI", "irb": "IRB", "rec": "REC", "orcid": "ORCID", "hod": "HOD",
    "cv": "CV", "id": "ID", "no": "No.", "url": "URL", "dob": "DOB",
    "sop": "SOP", "coi": "COI", "ai": "AI",
}
_KEY_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|[_\-\s]+")
_SLUG_BOUNDARY = re.compile(r"[-_\s]+")

# Deliberately NOT the same table as _ACRONYMS above: that one maps "no"
# -> "No." because it's meant for field *names* like "irbReferenceNo".
# Applied to a plain yes/no *answer* instead, that turns "no" into the
# nonsensical "No." -- so slug/answer text gets its own, much smaller set.
_VALUE_ACRONYMS = {"ai": "AI", "irb": "IRB", "coi": "COI"}


def humanize_key(value):
    """'piName' -> 'PI Name', 'irbReferenceNo' -> 'IRB Reference No.' --
    for form_data *keys* only (see _humanize_value for answer text)."""
    text = str(value).strip()
    if not text:
        return ""
    words = [w for w in _KEY_BOUNDARY.split(text) if w]
    return " ".join(_ACRONYMS.get(w.lower(), w[:1].upper() + w[1:]) for w in words)


def _humanize_value(value):
    """'clinical-trial' -> 'Clinical Trial', 'no' -> 'No' -- for answer
    *text* (checkbox slugs, yes/no answers), never form_data keys."""
    text = str(value).strip()
    if not text:
        return ""
    words = [w for w in _SLUG_BOUNDARY.split(text) if w]
    return " ".join(_VALUE_ACRONYMS.get(w.lower(), w[:1].upper() + w[1:]) for w in words)


def _format_value(value):
    """Renders one form_data value as display text. Returns "" for
    anything that should be skipped (blank, unanswered, or a
    researchTeam-shaped list -- handled separately as its own table)."""
    if isinstance(value, bool):
        return "Yes" if value else ""
    if isinstance(value, list):
        if not value or all(isinstance(v, dict) for v in value):
            return ""
        return ", ".join(_humanize_value(v) if isinstance(v, str) else str(v) for v in value)
    return str(value).strip()


def _styles():
    return {
        "org_name": ParagraphStyle("org_name", fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY),
        "org_sub": ParagraphStyle("org_sub", fontName="Helvetica", fontSize=8.5, leading=11, textColor=TEXT_FAINT),
        "meta_right": ParagraphStyle("meta_right", fontName="Helvetica", fontSize=9, leading=13, textColor=TEXT_SUB, alignment=2),
        "doc_title": ParagraphStyle("doc_title", fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=NAVY),
        "doc_sub": ParagraphStyle("doc_sub", fontName="Helvetica", fontSize=10.5, leading=15, textColor=TEXT_SUB),
        "section_title": ParagraphStyle(
            "section_title", fontName="Helvetica-Bold", fontSize=12, leading=15,
            textColor=NAVY, spaceBefore=18, spaceAfter=8,
        ),
        "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=TEXT_SUB),
        "value": ParagraphStyle("value", fontName="Helvetica", fontSize=10, leading=14, textColor=TEXT_MAIN),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, leading=15, textColor=TEXT_MAIN),
        "body_muted": ParagraphStyle("body_muted", fontName="Helvetica-Oblique", fontSize=9.5, leading=14, textColor=TEXT_FAINT),
        "chip": ParagraphStyle("chip", fontName="Helvetica-Bold", fontSize=9, leading=12, alignment=1),
        "table_head": ParagraphStyle("table_head", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=WHITE),
        "table_cell": ParagraphStyle("table_cell", fontName="Helvetica", fontSize=9.5, leading=13, textColor=TEXT_MAIN),
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
    """Two-column label/value grid -- same "field label above value" shape
    as the web page's .field-grid. Pairs with a blank value are dropped
    entirely rather than printed as an empty field."""
    pairs = [(label, value) for label, value in pairs if (value or "").strip()]
    if not pairs:
        return None

    rows = []
    for i in range(0, len(pairs), 2):
        row = []
        for label, value in pairs[i:i + 2]:
            cell = [Paragraph(label.upper(), styles["label"]), Paragraph(value, styles["value"])]
            row.append(cell)
        if len(row) == 1:
            row.append("")
        rows.append(row)

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
    canvas.drawString(PAGE_MARGIN, 1.0 * cm, "MSREC — Metascholar Research Ethics Committee · Confidential application record")
    canvas.drawRightString(A4[0] - PAGE_MARGIN, 1.0 * cm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


# form_data keys already surfaced in a named section below -- left out of
# the catch-all "Additional Details" section at the end so nothing prints
# twice. studyTitle/shortTitle are here even though Full Title comes from
# application.title (a property that just reads form_data["studyTitle"]).
_SHOWN_KEYS = {
    "studyTitle", "shortTitle", "riskLevel", "studyPurpose", "studyStatus", "studyStatusOther",
    "startDate", "completionDate",
    "piName", "piEmail", "piPhone", "piTitle", "piOrcid", "piInstitution", "piDepartment",
    "piQualification", "applicantCategory", "applicantCategoryOther",
    "researchTeam",
    "fundedYn", "fundingOrg", "commerciallySponsoredYn", "coi", "coiExplain",
    "studyType", "studyTypeOther", "researchArea", "researchAreaOther",
    "possibleRisks", "possibleRisksOther", "risksDescribe", "risksMinimize",
    "dataCollection", "dataCollectionOther", "consentMethod", "consentMethodOther",
    "documentsAttached", "documentsAttachedOther", "documents",
    "declarationName", "declarationSignature", "declarationDate", "confirmDeclaration",
}


def render_application_pdf(application):
    """Returns the rendered PDF as raw bytes for one Application (any
    status except Draft -- a draft has nothing decided or documented yet
    worth exporting, same reasoning as review PDFs only existing for
    Completed assignments)."""
    styles = _styles()
    applicant = application.applicant
    form = application.form_data or {}

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=PAGE_MARGIN, bottomMargin=2.1 * cm,
        leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        title=f"Application Record - {application.reference_no or 'MSREC'}",
    )
    col_w = (doc.width - 20) / 2
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

    story.append(Paragraph("Application Record", styles["doc_title"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"{application.title} &middot; submitted by {applicant.full_name}", styles["doc_sub"]))
    story.append(Spacer(1, 10))

    # ---------------- Status row ----------------
    status_label, status_badge = _STATUS_BADGE.get(application.status, (application.get_status_display(), "gray"))
    status_cells = [_chip(status_label, status_badge, styles)]
    if application.resubmitted_at:
        status_cells.append(_chip(
            f"Revised · round {application.revision_count}", "blue", styles,
        ))
    status_row = Table([status_cells], colWidths=[None] * len(status_cells))
    status_row.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(status_row)

    # ---------------- Research Information ----------------
    story.append(Paragraph("Research Information", styles["section_title"]))
    grid = _kv_grid([
        ("Full Title", application.title),
        ("Short Title", form.get("shortTitle", "")),
        ("Requested Review Pathway", application.review_type or "Not specified"),
        ("Risk Level", form.get("riskLevel", "")),
        ("Study Status", _humanize_value(form.get("studyStatus", "")) or form.get("studyStatusOther", "")),
        ("Start Date", form.get("startDate", "")),
        ("Expected Completion", form.get("completionDate", "")),
        ("Submitted", application.submitted_at.strftime("%d %b %Y, %I:%M %p") if application.submitted_at else ""),
    ], styles, col_w)
    if grid:
        story.append(grid)
    if form.get("studyPurpose"):
        story.append(Paragraph("PURPOSE OF THE STUDY", styles["label"]))
        story.append(Spacer(1, 3))
        story.append(Paragraph(form["studyPurpose"].replace("\n", "<br/>"), styles["body"]))
        story.append(Spacer(1, 6))

    # ---------------- Principal Investigator ----------------
    story.append(Paragraph("Principal Investigator", styles["section_title"]))
    grid = _kv_grid([
        ("Name", form.get("piName", "")),
        ("Title", form.get("piTitle", "")),
        ("Email", form.get("piEmail", "")),
        ("Phone", form.get("piPhone", "")),
        ("Institution", form.get("piInstitution", "") or applicant.institution),
        ("Department", form.get("piDepartment", "")),
        ("Qualification", form.get("piQualification", "")),
        ("ORCID", form.get("piOrcid", "")),
        ("Applicant Category", _humanize_value(form.get("applicantCategory", "")) or form.get("applicantCategoryOther", "")),
    ], styles, col_w)
    if grid:
        story.append(grid)

    # ---------------- Research Team ----------------
    team = form.get("researchTeam") or []
    if team:
        story.append(Paragraph("Research Team", styles["section_title"]))
        team_data = [[
            Paragraph("Name", styles["table_head"]), Paragraph("Role", styles["table_head"]),
            Paragraph("Institution", styles["table_head"]),
        ]]
        for member in team:
            team_data.append([
                Paragraph(member.get("name", "") or "—", styles["table_cell"]),
                Paragraph(member.get("role", "") or "—", styles["table_cell"]),
                Paragraph(member.get("institution", "") or "—", styles["table_cell"]),
            ])
        team_table = Table(team_data, colWidths=[doc.width * 0.34, doc.width * 0.3, doc.width * 0.36], repeatRows=1)
        team_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, -2), 0.5, BORDER),
            *[("BACKGROUND", (0, i), (-1, i), WHITE if i % 2 else colors.HexColor("#f7f8fa"))
              for i in range(1, len(team_data))],
        ]))
        story.append(team_table)

    # ---------------- Funding & Conflict of Interest ----------------
    grid = _kv_grid([
        ("External Funding", _humanize_value(form.get("fundedYn", ""))),
        ("Funding Organisation", form.get("fundingOrg", "")),
        ("Commercially Sponsored", _humanize_value(form.get("commerciallySponsoredYn", ""))),
        ("Conflict of Interest", _humanize_value(form.get("coi", ""))),
    ], styles, col_w)
    if grid:
        story.append(Paragraph("Funding &amp; Conflict of Interest", styles["section_title"]))
        story.append(grid)
        if form.get("coiExplain"):
            story.append(Paragraph(form["coiExplain"].replace("\n", "<br/>"), styles["body"]))
            story.append(Spacer(1, 6))

    # ---------------- Ethics & Risk overview ----------------
    ethics_pairs = [
        ("Study Type", _format_value(form.get("studyType")) or form.get("studyTypeOther", "")),
        ("Research Area", _format_value(form.get("researchArea")) or form.get("researchAreaOther", "")),
        ("Possible Risks", _format_value(form.get("possibleRisks")) or form.get("possibleRisksOther", "")),
        ("Data Collection Methods", _format_value(form.get("dataCollection")) or form.get("dataCollectionOther", "")),
        ("Consent Method", _format_value(form.get("consentMethod")) or form.get("consentMethodOther", "")),
    ]
    grid = _kv_grid(ethics_pairs, styles, col_w)
    if grid:
        story.append(Paragraph("Ethics &amp; Risk Overview", styles["section_title"]))
        story.append(grid)
        for label, key in [("How risks are minimized", "risksMinimize"), ("Risk description", "risksDescribe")]:
            if form.get(key):
                story.append(Paragraph(label.upper(), styles["label"]))
                story.append(Spacer(1, 3))
                story.append(Paragraph(form[key].replace("\n", "<br/>"), styles["body"]))
                story.append(Spacer(1, 6))

    # ---------------- Documents Attached ----------------
    story.append(Paragraph("Documents Attached", styles["section_title"]))
    checklist = _format_value(form.get("documentsAttached"))
    if checklist:
        story.append(Paragraph("DECLARED ON THE APPLICATION FORM", styles["label"]))
        story.append(Spacer(1, 3))
        story.append(Paragraph(checklist, styles["body"]))
        story.append(Spacer(1, 8))
    uploaded = list(getattr(application, "documents", None) or [])
    if uploaded:
        story.append(Paragraph("UPLOADED FILES", styles["label"]))
        story.append(Spacer(1, 3))
        for doc_item in uploaded:
            name = doc_item.get("name") if isinstance(doc_item, dict) else str(doc_item)
            note = " (appended as pages below)" if _is_mergeable_pdf(doc_item) else " (not a PDF -- see the copy on file)"
            story.append(Paragraph(f"&bull; {name}{note}", styles["body"]))
    elif not checklist:
        story.append(Paragraph("No documents were attached to this application.", styles["body_muted"]))

    # ---------------- Revision History ----------------
    if application.revision_count:
        story.append(Paragraph("Revision History", styles["section_title"]))
        grid = _kv_grid([
            ("Revision Rounds", str(application.revision_count)),
            ("Last Requested", application.revision_requested_at.strftime("%d %b %Y") if application.revision_requested_at else ""),
            ("Last Resubmitted", application.resubmitted_at.strftime("%d %b %Y") if application.resubmitted_at else "Not yet resubmitted"),
        ], styles, col_w)
        if grid:
            story.append(grid)
        if application.revision_comment:
            story.append(Paragraph("SECRETARIAT'S LAST REVISION REQUEST", styles["label"]))
            story.append(Spacer(1, 3))
            story.append(Paragraph(application.revision_comment.replace("\n", "<br/>"), styles["body"]))
            story.append(Spacer(1, 6))

    # ---------------- Decision ----------------
    if application.status in ("approved", "not_approved") and application.decided_at:
        decision_color, decision_light = _BADGE_COLORS.get(
            "green" if application.status == "approved" else "red", (GRAY, GRAY_LIGHT)
        )
        decision_block = [[Paragraph("MSREC DECISION", styles["label"])]]
        decision_block.append([Paragraph(
            application.get_status_display(),
            ParagraphStyle("decision", fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=decision_color),
        )])
        decision_block.append([Paragraph(
            f"Decided {application.decided_at.strftime('%d %b %Y')}", styles["body_muted"],
        )])
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
        story.append(KeepTogether([Paragraph("Decision", styles["section_title"]), decision_table]))

    # ---------------- Declaration ----------------
    grid = _kv_grid([
        ("Declared By", form.get("declarationName", "")),
        ("Signature", form.get("declarationSignature", "")),
        ("Date", form.get("declarationDate", "")),
        ("Declaration Confirmed", "Yes" if form.get("confirmDeclaration") else ""),
    ], styles, col_w)
    if grid:
        story.append(Paragraph("Principal Investigator Declaration", styles["section_title"]))
        story.append(grid)

    # ---------------- Additional Details (everything else) ----------------
    extra_pairs = []
    for key, value in form.items():
        if key in _SHOWN_KEYS:
            continue
        text = _format_value(value)
        # A bare lowercase slug ("no", "yes", "anonymous", ...) is one of
        # this form's short enum answers, not free text -- Title Case it
        # for a page that otherwise reads as data, not a raw JSON dump.
        # Anything else (names, emails, explanations, dates) is left
        # exactly as the applicant typed it.
        if text and re.fullmatch(r"[a-z]+(?:-[a-z]+)*", text):
            text = _humanize_value(text)
        if text:
            extra_pairs.append((humanize_key(key), text))
    extra_pairs.sort(key=lambda pair: pair[0])
    grid = _kv_grid(extra_pairs, styles, col_w)
    if grid:
        story.append(Paragraph("Additional Details", styles["section_title"]))
        story.append(grid)

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.6, color=BORDER, spaceAfter=8))
    story.append(Paragraph(
        f"This is a system-generated record of {application.reference_no or 'this application'} as held by MSREC. "
        "It reflects the applicant's own submission and is provided for internal Secretariat/Committee use.",
        styles["body_muted"],
    ))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return _with_uploaded_pdfs_appended(buffer.getvalue(), uploaded)


def _with_uploaded_pdfs_appended(record_pdf_bytes, uploaded_documents):
    """Merges every uploaded document that's actually a PDF onto the end
    of the just-built Application Record, so a Secretariat/Committee/
    Reviewer downloading "the" PDF gets one single file -- the record plus
    the protocol, consent forms, etc. the applicant attached -- instead of
    having to separately open each one from the Documents list. A file
    that turns out not to be a real, readable PDF (wrong extension, or
    corrupted) is skipped rather than failing the whole download; the
    Documents section above still names every uploaded file either way.
    """
    from . import storage as application_storage

    writer = PdfWriter()
    writer.append(BytesIO(record_pdf_bytes))

    for doc_item in uploaded_documents:
        if not _is_mergeable_pdf(doc_item):
            continue
        path = doc_item.get("path")
        data = application_storage.download_bytes(path) if path else None
        if not data:
            continue
        try:
            writer.append(PdfReader(BytesIO(data)))
        except PdfReadError:
            logger.warning("Skipping unreadable uploaded PDF %s when merging application record", path)

    out = BytesIO()
    writer.write(out)
    return out.getvalue()
