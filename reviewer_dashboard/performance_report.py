"""Reviewer Activity and Performance Report PDF.

Generates a structured tabular report (distinct from the letter-style
activity_report.py) that matches the MSREC Reviewer Activity and Performance
Report specification. One unique report reference (MSREC/RR/YEAR/XXXX) is
minted per download and stored in ReviewerPerformanceReport.

Layout: platypus A4, same colour palette as pdf.py, _ReportCanvas for
"Page X of Y" footers with the report ref and system-generated statement.
"""
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)
import reportlab.pdfgen.canvas as rl_canvas

# Same colour tokens as pdf.py / static/dashboard/css/style.css
NAVY = colors.HexColor("#1b2a4a")
TEAL = colors.HexColor("#159a96")
TEAL_LIGHT = colors.HexColor("#e4f6f5")
GREEN = colors.HexColor("#1fa971")
GREEN_LIGHT = colors.HexColor("#e7f7f0")
ORANGE = colors.HexColor("#e07a1f")
ORANGE_LIGHT = colors.HexColor("#fdf0e2")
RED = colors.HexColor("#e0483f")
RED_LIGHT = colors.HexColor("#fdeceb")
GRAY = colors.HexColor("#6b7280")
GRAY_LIGHT = colors.HexColor("#eef1f5")
TEXT_MAIN = colors.HexColor("#1f2733")
TEXT_SUB = colors.HexColor("#5b6472")
TEXT_FAINT = colors.HexColor("#9aa2af")
BORDER = colors.HexColor("#e6e9ef")
WHITE = colors.white

PAGE_MARGIN = 2 * cm
COMMITTEE_NAME = "Metascholar Research Ethics Committee"


# ---------------------------------------------------------------------------
# Canvas with deferred "Page X of Y" footer
# ---------------------------------------------------------------------------

class _ReportCanvas(rl_canvas.Canvas):
    def __init__(self, *args, **kwargs):
        self._report_ref = kwargs.pop("report_ref", "")
        super().__init__(*args, **kwargs)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total):
        self.saveState()
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.6)
        self.line(PAGE_MARGIN, 1.45 * cm, A4[0] - PAGE_MARGIN, 1.45 * cm)
        self.setFont("Helvetica", 7)
        self.setFillColor(TEXT_FAINT)
        left = (
            f"{self._report_ref}  ·  "
            "This document was electronically generated from the "
            "Metascholar Research Ethics Committee Management System."
        )
        self.drawString(PAGE_MARGIN, 1.0 * cm, left)
        self.drawRightString(A4[0] - PAGE_MARGIN, 1.0 * cm, f"Page {self._pageNumber} of {total}")
        self.restoreState()


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _styles():
    return {
        "eyebrow": ParagraphStyle(
            "eyebrow", fontName="Helvetica-Bold", fontSize=8, leading=10,
            textColor=TEXT_FAINT, spaceAfter=2,
        ),
        "doc_title": ParagraphStyle(
            "doc_title", fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=NAVY,
        ),
        "section_title": ParagraphStyle(
            "section_title", fontName="Helvetica-Bold", fontSize=11.5, leading=14,
            textColor=NAVY, spaceBefore=16, spaceAfter=8,
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
            "body_muted", fontName="Helvetica-Oblique", fontSize=9, leading=13, textColor=TEXT_FAINT,
        ),
        "table_head": ParagraphStyle(
            "table_head", fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=WHITE,
        ),
        "table_cell": ParagraphStyle(
            "table_cell", fontName="Helvetica", fontSize=9, leading=13, textColor=TEXT_MAIN,
        ),
        "table_cell_muted": ParagraphStyle(
            "table_cell_muted", fontName="Helvetica", fontSize=9, leading=13, textColor=TEXT_SUB,
        ),
        "meta_right": ParagraphStyle(
            "meta_right", fontName="Helvetica", fontSize=9, leading=13, textColor=TEXT_SUB, alignment=2,
        ),
        "summary": ParagraphStyle(
            "summary", fontName="Helvetica", fontSize=10, leading=15.5, textColor=TEXT_MAIN,
            spaceBefore=4, spaceAfter=4,
        ),
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def gather_stats(user, period_start=None, period_end=None):
    """Full performance statistics for the structured report."""
    from .models import ReviewAssignment
    Status = ReviewAssignment.Status

    qs = ReviewAssignment.objects.filter(reviewer=user).select_related(
        "application", "application__applicant"
    )
    if period_start:
        qs = qs.filter(assigned_at__date__gte=period_start)
    if period_end:
        qs = qs.filter(assigned_at__date__lte=period_end)

    total = qs.count()
    completed_qs = qs.filter(status=Status.COMPLETED)
    completed_count = completed_qs.count()
    pending_count = qs.filter(status=Status.ACCEPTED).count()
    declined_count = qs.filter(status=Status.DECLINED).count()

    today = timezone.localdate()

    # Deadline performance — only completed assignments with a due date
    with_due = completed_qs.filter(due_date__isnull=False, completed_at__isnull=False)
    within_deadline = 0
    delayed = 0
    total_days = 0
    count_with_days = 0

    for a in with_due:
        if a.completed_at.date() <= a.due_date:
            within_deadline += 1
        else:
            delayed += 1

    # Average completion time across all completed reviews (assigned → completed)
    for a in completed_qs.filter(completed_at__isnull=False):
        days = (a.completed_at.date() - a.assigned_at.date()).days
        total_days += days
        count_with_days += 1

    avg_days = round(total_days / count_with_days, 1) if count_with_days else None

    # On-time rate
    with_due_count = within_deadline + delayed
    on_time_rate = round(within_deadline / with_due_count * 100) if with_due_count else None

    # All assignments ordered for the detailed table
    assignments = list(qs.order_by("assigned_at"))

    return {
        "total": total,
        "completed": completed_count,
        "pending": pending_count,
        "declined": declined_count,
        "within_deadline": within_deadline,
        "delayed": delayed,
        "avg_days": avg_days,
        "on_time_rate": on_time_rate,
        "assignments": assignments,
    }


# ---------------------------------------------------------------------------
# Reference number
# ---------------------------------------------------------------------------

def _mint_report_ref(reviewer, generated_by, period_start, period_end):
    """Create a ReviewerPerformanceReport record and assign a unique ref."""
    from .models import ReviewerPerformanceReport
    record = ReviewerPerformanceReport.objects.create(
        reviewer=reviewer,
        generated_by=generated_by,
        period_start=period_start,
        period_end=period_end,
        report_ref="PENDING",
    )
    year = record.generated_at.year
    seq = ReviewerPerformanceReport.objects.filter(
        generated_at__year=year, id__lte=record.id
    ).count()
    record.report_ref = f"MSREC/RR/{year}/{seq:04d}"
    record.save(update_fields=["report_ref"])
    return record


# ---------------------------------------------------------------------------
# PDF builder
# ---------------------------------------------------------------------------

def render_report_pdf(user, generated_by=None, period_start=None, period_end=None):
    """Generate the PDF and mint a unique report ref.

    Returns (pdf_bytes, ReviewerPerformanceReport).
    """
    from accounts import membership

    now = timezone.localtime()
    effective_end = period_end or now.date()
    stats = gather_stats(user, period_start, period_end)

    # Determine reporting period label
    first_assigned = None
    if stats["assignments"]:
        first_assigned = stats["assignments"][0].assigned_at.date()
    p_start = period_start or first_assigned
    period_label = (
        f"{p_start.strftime('%d %b %Y')} – {effective_end.strftime('%d %b %Y')}"
        if p_start else f"Up to {effective_end.strftime('%d %b %Y')}"
    )

    # Reviewer info
    _kind, role_label = membership.membership_role(user)
    ethics_id = getattr(user, "membership_ethics_id", None) or "—"
    institution = getattr(user, "institution", "") or "—"

    record = _mint_report_ref(user, generated_by, period_start, effective_end)
    report_ref = record.report_ref
    generated_str = now.strftime("%d %b %Y, %I:%M %p")

    styles = _styles()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=PAGE_MARGIN, bottomMargin=2.2 * cm,
        leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        title=f"Reviewer Activity and Performance Report — {user.full_name}",
    )

    story = []
    w = doc.width

    # ---- Header ----
    hdr = Table(
        [[
            [Paragraph("MSREC", ParagraphStyle("on", fontName="Helvetica-Bold", fontSize=11, textColor=NAVY)),
             Paragraph(COMMITTEE_NAME, ParagraphStyle("os", fontName="Helvetica", fontSize=8, textColor=TEXT_FAINT))],
            [Paragraph(report_ref, styles["meta_right"]),
             Paragraph(f"Generated: {generated_str}", styles["meta_right"])],
        ]],
        colWidths=[w * 0.55, w * 0.45],
    )
    hdr.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.4, color=NAVY, spaceAfter=12))
    story.append(Paragraph("REVIEWER ACTIVITY AND PERFORMANCE REPORT", styles["eyebrow"]))
    story.append(Spacer(1, 2))
    story.append(Paragraph(user.full_name, styles["doc_title"]))
    story.append(Spacer(1, 14))

    # ---- Reviewer Information ----
    story.append(Paragraph("Reviewer Information", styles["section_title"]))
    info_data = [
        [Paragraph("Full Name", styles["label"]), Paragraph(user.full_name or "—", styles["value"])],
        [Paragraph("MSREC Reviewer ID", styles["label"]), Paragraph(ethics_id, styles["value"])],
        [Paragraph("Institutional Affiliation", styles["label"]), Paragraph(institution, styles["value"])],
        [Paragraph("Reviewer Role", styles["label"]), Paragraph(role_label, styles["value"])],
        [Paragraph("Email Address", styles["label"]), Paragraph(user.email or "—", styles["value"])],
        [Paragraph("Reporting Period", styles["label"]), Paragraph(period_label, styles["value"])],
    ]
    info_table = Table(info_data, colWidths=[w * 0.35, w * 0.65])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
    ]))
    story.append(info_table)

    # ---- Review Activity Summary ----
    story.append(Paragraph("Review Activity Summary", styles["section_title"]))

    def _val(v, suffix=""):
        return "—" if v is None else f"{v}{suffix}"

    summary_data = [
        [Paragraph("Performance Indicator", styles["table_head"]), Paragraph("Value", styles["table_head"])],
        [Paragraph("Total Reviews Assigned", styles["table_cell"]), Paragraph(str(stats["total"]), styles["value"])],
        [Paragraph("Completed Reviews", styles["table_cell"]), Paragraph(str(stats["completed"]), styles["value"])],
        [Paragraph("Pending Reviews (In Progress)", styles["table_cell"]), Paragraph(str(stats["pending"]), styles["value"])],
        [Paragraph("Declined Assignments", styles["table_cell"]), Paragraph(str(stats["declined"]), styles["value"])],
        [Paragraph("Reviews Completed Within Deadline", styles["table_cell"]), Paragraph(str(stats["within_deadline"]), styles["value"])],
        [Paragraph("Delayed Reviews", styles["table_cell"]), Paragraph(str(stats["delayed"]), styles["value"])],
        [Paragraph("Average Review Completion Time", styles["table_cell"]), Paragraph(_val(stats["avg_days"], " days"), styles["value"])],
        [Paragraph("On-Time Completion Rate", styles["table_cell"]), Paragraph(_val(stats["on_time_rate"], "%"), styles["value"])],
    ]
    row_bg = []
    for i in range(1, len(summary_data)):
        if i % 2 == 0:
            row_bg.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f7f8fa")))

    summary_table = Table(summary_data, colWidths=[w * 0.72, w * 0.28], repeatRows=1)
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
        *row_bg,
    ]))
    story.append(summary_table)

    # ---- Detailed Review Record ----
    story.append(Paragraph("Detailed Review Record", styles["section_title"]))

    if stats["assignments"]:
        Status = __import__("reviewer_dashboard.models", fromlist=["ReviewAssignment"]).ReviewAssignment.Status

        detail_data = [[
            Paragraph("No.", styles["table_head"]),
            Paragraph("Protocol ID", styles["table_head"]),
            Paragraph("Application Title", styles["table_head"]),
            Paragraph("Assigned", styles["table_head"]),
            Paragraph("Deadline", styles["table_head"]),
            Paragraph("Completed", styles["table_head"]),
            Paragraph("Status / Performance", styles["table_head"]),
        ]]

        for idx, a in enumerate(stats["assignments"], 1):
            app = a.application
            ref = getattr(app, "reference_no", None) or "—"
            title = (getattr(app, "title", None) or "—")[:60]
            if len(getattr(app, "title", "") or "") > 60:
                title += "…"
            assigned_str = a.assigned_at.strftime("%d %b %Y") if a.assigned_at else "—"
            deadline_str = a.due_date.strftime("%d %b %Y") if a.due_date else "—"
            completed_str = a.completed_at.strftime("%d %b %Y") if a.completed_at else "—"

            if a.status == Status.COMPLETED:
                if a.due_date and a.completed_at and a.completed_at.date() > a.due_date:
                    perf = "Completed / Delayed"
                    perf_color = ORANGE
                else:
                    perf = "Completed / Met Deadline"
                    perf_color = GREEN
            elif a.status == Status.DECLINED:
                perf = "Declined"
                perf_color = RED
            elif a.status == Status.ACCEPTED:
                if a.due_date and a.due_date < timezone.localdate():
                    perf = "In Progress / Overdue"
                    perf_color = ORANGE
                else:
                    perf = "In Progress"
                    perf_color = TEAL
            else:
                perf = "New / Pending Response"
                perf_color = GRAY

            detail_data.append([
                Paragraph(str(idx), styles["table_cell"]),
                Paragraph(ref, styles["table_cell"]),
                Paragraph(title, styles["table_cell"]),
                Paragraph(assigned_str, styles["table_cell_muted"]),
                Paragraph(deadline_str, styles["table_cell_muted"]),
                Paragraph(completed_str, styles["table_cell_muted"]),
                Paragraph(perf, ParagraphStyle("perf", parent=styles["table_cell"], textColor=perf_color,
                                               fontName="Helvetica-Bold")),
            ])

        col_w = [0.6 * cm, 2.8 * cm, w - 0.6 * cm - 2.8 * cm - 2.0 * cm - 2.0 * cm - 2.0 * cm - 3.6 * cm,
                 2.0 * cm, 2.0 * cm, 2.0 * cm, 3.6 * cm]
        detail_row_bg = []
        for i in range(1, len(detail_data)):
            if i % 2 == 0:
                detail_row_bg.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f7f8fa")))

        detail_table = Table(detail_data, colWidths=col_w, repeatRows=1)
        detail_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
            *detail_row_bg,
        ]))
        story.append(detail_table)
    else:
        story.append(Paragraph("No review assignments found for the selected period.", styles["body_muted"]))

    # ---- Performance Summary Statement ----
    story.append(Paragraph("Performance Summary Statement", styles["section_title"]))

    s = stats
    on_time_str = f"{s['on_time_rate']}%" if s["on_time_rate"] is not None else "N/A"
    avg_str = f"{s['avg_days']} days" if s["avg_days"] is not None else "N/A"

    summary_text = (
        f"During the reporting period, {user.full_name} received <b>{s['total']}</b> review "
        f"assignment{'s' if s['total'] != 1 else ''}, of which <b>{s['completed']}</b> "
        f"{'were' if s['completed'] != 1 else 'was'} completed, <b>{s['pending']}</b> "
        f"remained in progress, and <b>{s['declined']}</b> {'were' if s['declined'] != 1 else 'was'} declined. "
        f"Of the completed reviews, <b>{s['within_deadline']}</b> "
        f"{'were' if s['within_deadline'] != 1 else 'was'} submitted within the assigned review period, "
        f"representing an on-time completion rate of <b>{on_time_str}</b>. "
        f"The average review completion time was <b>{avg_str}</b>."
    )
    story.append(Paragraph(summary_text, styles["summary"]))

    # ---- Report Authentication ----
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=0.6, color=BORDER, spaceAfter=8))
    auth_lines = [
        f"<b>Report Reference:</b> {report_ref}",
        f"<b>Generated:</b> {generated_str}",
        f"<b>Reviewer:</b> {user.full_name}  ·  {ethics_id}",
    ]
    for line in auth_lines:
        story.append(Paragraph(line, styles["body_muted"]))

    doc.build(
        story,
        canvasmaker=lambda *a, **k: _ReportCanvas(*a, report_ref=report_ref, **k),
    )
    return buffer.getvalue(), record


def report_filename(record):
    ref = record.report_ref.replace("/", "-")
    return f"{ref}.pdf"
