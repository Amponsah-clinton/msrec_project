"""Renders a full Application record as a downloadable PDF -- served from
the Secretariat/Admin "Download PDF" button on application_detail.html and,
unchanged, to a Reviewer the moment a protocol is assigned to them
(reviewer_dashboard.views). One document, one visual language.

The design brief is a formal institutional record, not a web page printed
to paper: a single restrained accent (navy, with a thin teal rule),
numbered and ruled section headers, hairline tables rather than filled/
zebra-striped ones, status shown as a quiet labelled line rather than a
coloured pill, a running header and "Page X of Y" -- so it reads like a
document an ethics committee would file, not a dashboard screenshot.

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
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (
    Flowable, HRFlowable, KeepTogether, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

# A deliberately tight palette: one primary (navy), one accent (teal), and
# a greyscale ramp for text and rules. The former rainbow of badge colours
# is gone -- the only colour that now carries meaning is a single semantic
# hue used for the status dot and the decision block, and nothing else.
NAVY = colors.HexColor("#17233f")
TEAL = colors.HexColor("#0f7a76")
TEXT_MAIN = colors.HexColor("#1f2733")
TEXT_SUB = colors.HexColor("#56606f")
TEXT_FAINT = colors.HexColor("#8a93a1")
RULE = colors.HexColor("#c8cdd6")
RULE_SOFT = colors.HexColor("#e6e9ef")
ROW_ALT = colors.HexColor("#f6f7f9")
WHITE = colors.white

# Semantic colours, used ONLY for the small status dot and the decision
# accent bar -- never as fills behind text. Kept muted (print-friendly,
# not screen-bright) so a single one reads as a considered accent rather
# than a toy badge.
GREEN = colors.HexColor("#1f8a5b")
AMBER = colors.HexColor("#b9791c")
RED = colors.HexColor("#c0392f")
BLUE = colors.HexColor("#2b5fb8")
PURPLE = colors.HexColor("#6b4fc0")

_STATUS_META = {
    "submitted": ("New submission", AMBER),
    "under_review": ("Under review", BLUE),
    "with_committee": ("With committee", PURPLE),
    "revisions_required": ("Revisions requested", RED),
    "approved": ("Approved", GREEN),
    "not_approved": ("Not approved", RED),
}

PAGE_MARGIN = 2.1 * cm
TOP_MARGIN = 2.2 * cm
BOTTOM_MARGIN = 2.0 * cm

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


def _esc(text):
    """Escape user text before it goes into a reportlab Paragraph, whose
    mini-HTML parser would otherwise choke on a stray & or <."""
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _para_text(text):
    """User free-text -> paragraph-safe HTML: escaped, with newlines kept
    as line breaks."""
    return _esc(text).replace("\n", "<br/>")


def _styles():
    return {
        "org_name": ParagraphStyle(
            "org_name", fontName="Helvetica-Bold", fontSize=13, leading=15,
            textColor=NAVY, trackingAmount=0.6,
        ),
        "org_sub": ParagraphStyle(
            "org_sub", fontName="Helvetica", fontSize=7.5, leading=10,
            textColor=TEXT_FAINT, trackingAmount=0.3,
        ),
        "meta_right": ParagraphStyle(
            "meta_right", fontName="Helvetica", fontSize=8.5, leading=13,
            textColor=TEXT_SUB, alignment=TA_RIGHT,
        ),
        "meta_right_strong": ParagraphStyle(
            "meta_right_strong", fontName="Helvetica-Bold", fontSize=8.5, leading=13,
            textColor=NAVY, alignment=TA_RIGHT,
        ),
        "kicker": ParagraphStyle(
            "kicker", fontName="Helvetica-Bold", fontSize=8, leading=11,
            textColor=TEAL, trackingAmount=1.6,
        ),
        "doc_title": ParagraphStyle(
            "doc_title", fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=NAVY,
        ),
        "doc_sub": ParagraphStyle(
            "doc_sub", fontName="Helvetica", fontSize=9.5, leading=14, textColor=TEXT_SUB,
        ),
        "status": ParagraphStyle(
            "status", fontName="Helvetica-Bold", fontSize=9, leading=13, textColor=NAVY,
        ),
        "section_title": ParagraphStyle(
            "section_title", fontName="Helvetica-Bold", fontSize=10.5, leading=14,
            textColor=NAVY, trackingAmount=0.8,
        ),
        "label": ParagraphStyle(
            "label", fontName="Helvetica-Bold", fontSize=7, leading=10,
            textColor=TEXT_FAINT, trackingAmount=0.7,
        ),
        "value": ParagraphStyle("value", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=TEXT_MAIN),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=14.5, textColor=TEXT_MAIN),
        "body_muted": ParagraphStyle("body_muted", fontName="Helvetica-Oblique", fontSize=9, leading=13, textColor=TEXT_FAINT),
        "table_head": ParagraphStyle(
            "table_head", fontName="Helvetica-Bold", fontSize=7.5, leading=11,
            textColor=TEXT_SUB, trackingAmount=0.6,
        ),
        "table_cell": ParagraphStyle("table_cell", fontName="Helvetica", fontSize=9, leading=12.5, textColor=TEXT_MAIN),
    }


def _hex(color):
    """reportlab Color -> '#rrggbb', for inline <font color=...> tags."""
    return "#{:02x}{:02x}{:02x}".format(
        int(color.red * 255), int(color.green * 255), int(color.blue * 255)
    )


def _section(number, title, styles):
    """A numbered, ruled section header -- '01  RESEARCH INFORMATION' with
    the number in teal and a hairline beneath. Returns the flowables so a
    caller can KeepTogether them with the first block of the section and
    never strand a header at the foot of a page."""
    heading = Paragraph(
        f'<font color="{_hex(TEAL)}">{number:02d}</font>&nbsp;&nbsp;&nbsp;{_esc(title.upper())}',
        styles["section_title"],
    )
    return [
        Spacer(1, 16),
        heading,
        Spacer(1, 4),
        HRFlowable(width="100%", thickness=0.75, color=NAVY, spaceAfter=10),
    ]


def _kv_grid(pairs, styles, col_width):
    """Two-column label/value grid -- a small-caps label sitting above its
    value, the cleanest way to lay a record of mixed-length fields.
    Pairs with a blank value are dropped entirely rather than printed as
    an empty field."""
    pairs = [(label, value) for label, value in pairs if (value or "").strip()]
    if not pairs:
        return None

    rows = []
    for i in range(0, len(pairs), 2):
        row = []
        for label, value in pairs[i:i + 2]:
            cell = [
                Paragraph(_esc(label).upper(), styles["label"]),
                Spacer(1, 2),
                Paragraph(_esc(value), styles["value"]),
            ]
            row.append(Table([[c] for c in cell], colWidths=[col_width]))
        if len(row) == 1:
            row.append("")
        rows.append(row)

    t = Table(rows, colWidths=[col_width + 8, col_width + 8])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 16),
    ]))
    return t


def _field_block(label, text, styles):
    """A full-width labelled free-text block (study purpose, risk
    narrative, revision note) -- the label small-caps above a justified
    body paragraph."""
    return [
        Paragraph(_esc(label).upper(), styles["label"]),
        Spacer(1, 3),
        Paragraph(_para_text(text), styles["body"]),
        Spacer(1, 4),
    ]


class _DecisionBar(Flowable):
    """The final decision, set as a quiet card with a semantic colour used
    only as a thin left accent bar -- restrained where the old version
    filled the whole box with colour. Draws its own box so the accent bar
    lines up flush with the border."""

    def __init__(self, title, detail, accent, width):
        super().__init__()
        self.title = title
        self.detail = detail
        self.accent = accent
        self.width = width
        self.height = 1.75 * cm

    def wrap(self, avail_w, avail_h):
        self.width = avail_w
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(colors.HexColor("#fbfcfd"))
        c.setStrokeColor(RULE_SOFT)
        c.setLineWidth(0.75)
        c.roundRect(0, 0, self.width, self.height, 4, stroke=1, fill=1)
        c.setFillColor(self.accent)
        c.rect(0, 0, 3.2, self.height, stroke=0, fill=1)
        c.setFillColor(TEXT_FAINT)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(18, self.height - 20, "MSREC DECISION")
        c.setFillColor(self.accent)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(18, self.height - 42, self.title)
        if self.detail:
            c.setFillColor(TEXT_SUB)
            c.setFont("Helvetica", 8.5)
            c.drawString(18, 14, self.detail)


def _letterhead(application, styles, content_width):
    """The page-one letterhead: wordmark on the left, a right-aligned
    reference/date block, and a navy rule under the pair."""
    left = [
        Paragraph("MSREC", styles["org_name"]),
        Spacer(1, 1),
        Paragraph("METASCHOLAR RESEARCH ETHICS COMMITTEE", styles["org_sub"]),
    ]
    right = [
        Paragraph(_esc(application.reference_no or "Reference pending"), styles["meta_right_strong"]),
        Paragraph(f"Generated {timezone.localtime():%d %b %Y, %I:%M %p}", styles["meta_right"]),
    ]
    head = Table([[left, right]], colWidths=[content_width * 0.6, content_width * 0.4])
    head.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [head, Spacer(1, 9), HRFlowable(width="100%", thickness=1.4, color=NAVY, spaceAfter=18)]


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
        topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN,
        leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        title=f"Application Record — {application.reference_no or 'MSREC'}",
        author="Metascholar Research Ethics Committee",
        subject="Research ethics application record",
    )
    col_w = (doc.width - 24) / 2
    story = []
    section_no = 0

    def section(title):
        nonlocal section_no
        section_no += 1
        return _section(section_no, title, styles)

    # ---------------- Letterhead ----------------
    story.extend(_letterhead(application, styles, doc.width))

    # ---------------- Title block ----------------
    story.append(Paragraph("RESEARCH ETHICS APPLICATION RECORD", styles["kicker"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(_esc(application.title), styles["doc_title"]))
    story.append(Spacer(1, 7))

    submitted = (
        f"Submitted {application.submitted_at:%d %b %Y}" if application.submitted_at else "Not yet submitted"
    )
    story.append(Paragraph(
        f"Submitted by {_esc(applicant.full_name)} &nbsp;·&nbsp; {submitted}",
        styles["doc_sub"],
    ))
    story.append(Spacer(1, 9))

    # Status as a quiet labelled line: a small semantic dot + plain text,
    # not a coloured pill.
    status_label, status_color = _STATUS_META.get(
        application.status, (application.get_status_display(), TEXT_SUB)
    )
    status_bits = [f'<font color="{_hex(status_color)}">●</font>&nbsp;&nbsp;{_esc(status_label)}']
    if application.resubmitted_at:
        status_bits.append(
            f'<font color="{_hex(TEXT_FAINT)}">&nbsp;&nbsp;·&nbsp;&nbsp;'
            f'Revised, round {application.revision_count}</font>'
        )
    story.append(Paragraph("".join(status_bits), styles["status"]))

    # ---------------- Research Information ----------------
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
    head = section("Research Information")
    story.append(KeepTogether(head + ([grid] if grid else [])))
    if form.get("studyPurpose"):
        story.append(Spacer(1, 2))
        story.extend(_field_block("Purpose of the study", form["studyPurpose"], styles))

    # ---------------- Principal Investigator ----------------
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
    head = section("Principal Investigator")
    story.append(KeepTogether(head + ([grid] if grid else [])))

    # ---------------- Research Team ----------------
    team = form.get("researchTeam") or []
    if team:
        team_data = [[
            Paragraph("NAME", styles["table_head"]), Paragraph("ROLE", styles["table_head"]),
            Paragraph("INSTITUTION", styles["table_head"]),
        ]]
        for member in team:
            team_data.append([
                Paragraph(_esc(member.get("name", "") or "—"), styles["table_cell"]),
                Paragraph(_esc(member.get("role", "") or "—"), styles["table_cell"]),
                Paragraph(_esc(member.get("institution", "") or "—"), styles["table_cell"]),
            ])
        team_table = Table(
            team_data, colWidths=[doc.width * 0.34, doc.width * 0.3, doc.width * 0.36], repeatRows=1,
        )
        # Hairline table: a header with only a rule beneath it and thin row
        # separators -- no navy fill, no zebra. Reads as a document table,
        # not a UI grid.
        team_style = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("LINEBELOW", (0, 0), (-1, 0), 0.9, NAVY),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE_SOFT),
        ]
        head = section("Research Team")
        story.append(KeepTogether(head + [team_table]))

    # ---------------- Funding & Conflict of Interest ----------------
    grid = _kv_grid([
        ("External Funding", _humanize_value(form.get("fundedYn", ""))),
        ("Funding Organisation", form.get("fundingOrg", "")),
        ("Commercially Sponsored", _humanize_value(form.get("commerciallySponsoredYn", ""))),
        ("Conflict of Interest", _humanize_value(form.get("coi", ""))),
    ], styles, col_w)
    if grid:
        head = section("Funding & Conflict of Interest")
        story.append(KeepTogether(head + [grid]))
        if form.get("coiExplain"):
            story.append(Spacer(1, 2))
            story.extend(_field_block("Conflict of interest — explanation", form["coiExplain"], styles))

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
        head = section("Ethics & Risk Overview")
        story.append(KeepTogether(head + [grid]))
        for label, key in [("How risks are minimized", "risksMinimize"), ("Risk description", "risksDescribe")]:
            if form.get(key):
                story.append(Spacer(1, 2))
                story.extend(_field_block(label, form[key], styles))

    # ---------------- Documents Attached ----------------
    checklist = _format_value(form.get("documentsAttached"))
    uploaded = list(getattr(application, "documents", None) or [])
    doc_blocks = []
    if checklist:
        doc_blocks.extend([
            Paragraph("DECLARED ON THE APPLICATION FORM", styles["label"]),
            Spacer(1, 3),
            Paragraph(_esc(checklist), styles["body"]),
            Spacer(1, 8),
        ])
    if uploaded:
        doc_blocks.extend([Paragraph("UPLOADED FILES", styles["label"]), Spacer(1, 3)])
        for doc_item in uploaded:
            name = doc_item.get("name") if isinstance(doc_item, dict) else str(doc_item)
            note = " (appended as pages below)" if _is_mergeable_pdf(doc_item) else " (not a PDF — see the copy on file)"
            doc_blocks.append(Paragraph(
                f'<font color="{_hex(TEAL)}">•</font>&nbsp;&nbsp;{_esc(name)}'
                f'<font color="{_hex(TEXT_FAINT)}">{_esc(note)}</font>',
                styles["body"],
            ))
    elif not checklist:
        doc_blocks.append(Paragraph("No documents were attached to this application.", styles["body_muted"]))
    head = section("Documents Attached")
    story.append(KeepTogether(head + doc_blocks[:1]))
    for block in doc_blocks[1:]:
        story.append(block)

    # ---------------- Revision History ----------------
    if application.revision_count:
        grid = _kv_grid([
            ("Revision Rounds", str(application.revision_count)),
            ("Last Requested", application.revision_requested_at.strftime("%d %b %Y") if application.revision_requested_at else ""),
            ("Last Resubmitted", application.resubmitted_at.strftime("%d %b %Y") if application.resubmitted_at else "Not yet resubmitted"),
        ], styles, col_w)
        head = section("Revision History")
        story.append(KeepTogether(head + ([grid] if grid else [])))
        if application.revision_comment:
            story.append(Spacer(1, 2))
            story.extend(_field_block("Secretariat's last revision request", application.revision_comment, styles))

    # ---------------- Decision ----------------
    if application.status in ("approved", "not_approved") and application.decided_at:
        accent = GREEN if application.status == "approved" else RED
        head = section("Decision")
        bar = _DecisionBar(
            application.get_status_display(),
            f"Decided {application.decided_at:%d %b %Y}",
            accent, doc.width,
        )
        story.append(KeepTogether(head + [bar]))

    # ---------------- Declaration ----------------
    grid = _kv_grid([
        ("Declared By", form.get("declarationName", "")),
        ("Signature", form.get("declarationSignature", "")),
        ("Date", form.get("declarationDate", "")),
        ("Declaration Confirmed", "Yes" if form.get("confirmDeclaration") else ""),
    ], styles, col_w)
    if grid:
        head = section("Principal Investigator Declaration")
        story.append(KeepTogether(head + [grid]))

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
        head = section("Additional Details")
        story.append(KeepTogether(head + [grid]))

    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE_SOFT, spaceAfter=8))
    story.append(Paragraph(
        f"This is a system-generated record of {_esc(application.reference_no or 'this application')} as held by MSREC. "
        "It reflects the applicant's own submission and is provided for internal Secretariat, Committee and Reviewer use.",
        styles["body_muted"],
    ))

    reference = application.reference_no or "Application record"
    doc.build(
        story,
        canvasmaker=lambda *a, **k: _RecordCanvas(*a, reference=reference, **k),
    )
    return _with_uploaded_pdfs_appended(buffer.getvalue(), uploaded)


class _RecordCanvas(_canvas.Canvas):
    """Draws the running header (page 2 onward) and the footer with a true
    'Page X of Y' -- which needs the total page count, known only once the
    whole story has been laid out, so every page is buffered and the
    decorations are drawn in a second pass at save() time."""

    def __init__(self, *args, reference="", **kwargs):
        super().__init__(*args, **kwargs)
        self._reference = reference
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for index, state in enumerate(self._pages, start=1):
            self.__dict__.update(state)
            self._draw_decorations(index, total)
            super().showPage()
        super().save()

    def _draw_decorations(self, page, total):
        width = A4[0]

        if page > 1:
            y = A4[1] - 1.25 * cm
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(TEXT_FAINT)
            self.drawString(PAGE_MARGIN, y, "MSREC · APPLICATION RECORD")
            self.setFont("Helvetica", 7.5)
            self.drawRightString(width - PAGE_MARGIN, y, self._reference)
            self.setStrokeColor(RULE_SOFT)
            self.setLineWidth(0.5)
            self.line(PAGE_MARGIN, y - 4, width - PAGE_MARGIN, y - 4)

        self.setStrokeColor(RULE_SOFT)
        self.setLineWidth(0.5)
        self.line(PAGE_MARGIN, 1.4 * cm, width - PAGE_MARGIN, 1.4 * cm)
        self.setFont("Helvetica", 7)
        self.setFillColor(TEXT_FAINT)
        self.drawString(
            PAGE_MARGIN, 1.0 * cm,
            "Metascholar Research Ethics Committee  ·  Confidential application record",
        )
        self.drawRightString(width - PAGE_MARGIN, 1.0 * cm, f"Page {page} of {total}")


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
