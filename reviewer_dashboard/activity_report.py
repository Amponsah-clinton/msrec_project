"""The Reviewer Activity Report: an on-demand A4 statement of a reviewer's
contribution to MSREC -- reviews completed, recommendations issued, response
and turnaround figures -- downloadable from their dashboard and My Documents
page (reviewer_dashboard.views.activity_report).

The wording wrapped around the figures, the letterhead artwork and the
signatory come from pages.models.ReviewerActivityReportTemplate (Site
Settings > Reviewer Activity Report), with {placeholders} filled from the
reviewer and their live statistics. The figures themselves are computed here
from the reviewer's ReviewAssignment records, so the report is always current;
nothing is stored. Layout re-uses the shared one-page A4 letter engine
(accounts/letters.py), with the statistics rendered as its tinted panels.
"""
from types import SimpleNamespace

from django.db.models import Count
from django.utils import timezone

from accounts import letters, membership
from applicant_dashboard.approval_documents import COMMITTEE_NAME, fill

from .models import ReviewAssignment

# Click-to-insert chips on the settings page, in this order.
PLACEHOLDERS = [
    ("recipient_name", "The reviewer's full name"),
    ("first_name", "The reviewer's first name"),
    ("role", "Ethics Reviewer, or the Committee position held"),
    ("a_role", "The role with “a” / “an” in front, e.g. “an Ethics Reviewer”"),
    ("ethics_id", "MSREC Ethics ID"),
    ("institution", "The reviewer's institution"),
    ("email", "The reviewer's email address"),
    ("member_since", "Date the reviewer was appointed"),
    ("reviews_completed", "Number of reviews completed"),
    ("total_assigned", "Total review assignments received"),
    ("committee_name", COMMITTEE_NAME),
    ("today", "Date the report is generated"),
]
PLACEHOLDER_KEYS = {key for key, _ in PLACEHOLDERS}


def unknown_placeholders(*texts):
    return letters.unknown_placeholders(PLACEHOLDER_KEYS, *texts)


def _template(template=None):
    if template is not None:
        return template
    from pages.models import ReviewerActivityReportTemplate
    return ReviewerActivityReportTemplate.get_solo()


def gather_stats(user):
    """Live review statistics for one reviewer, as a dict of figures plus
    ready-to-print (label, value) rows for the report's panels."""
    qs = ReviewAssignment.objects.filter(reviewer=user)
    Status = ReviewAssignment.Status

    total = qs.count()
    completed = qs.filter(status=Status.COMPLETED)
    completed_count = completed.count()
    accepted_open = qs.filter(status=Status.ACCEPTED).count()
    new_count = qs.filter(status=Status.NEW).count()
    declined = qs.filter(status=Status.DECLINED).count()

    today = timezone.localdate()
    overdue = qs.filter(status=Status.ACCEPTED, due_date__lt=today).count()

    # Response rate: of the assignments the reviewer has acted on (accepted
    # or declined), how many they accepted.
    responded = qs.exclude(status=Status.NEW).count()
    accepted_ever = total - new_count - declined
    response_rate = round(accepted_ever / responded * 100) if responded else None

    # On-time rate among completed reviews that had a due date.
    with_due = completed.filter(due_date__isnull=False, completed_at__isnull=False)
    with_due_count = with_due.count()
    on_time = sum(
        1 for a in with_due.only("completed_at", "due_date")
        if a.completed_at.date() <= a.due_date
    )
    on_time_rate = round(on_time / with_due_count * 100) if with_due_count else None

    # Recommendation mix among completed reviews.
    rec_counts = {
        row["recommendation"]: row["n"]
        for row in completed.exclude(recommendation="")
        .values("recommendation").annotate(n=Count("id"))
    }
    rec_label = dict(ReviewAssignment.Recommendation.choices)
    recommendation_rows = [
        (rec_label[key], str(rec_counts[key]))
        for key, _label in ReviewAssignment.Recommendation.choices
        if rec_counts.get(key)
    ]

    summary_rows = [
        ("Total assignments received", str(total)),
        ("Reviews completed", str(completed_count)),
        ("Reviews in progress", str(accepted_open)),
        ("Awaiting your response", str(new_count)),
    ]
    if declined:
        summary_rows.append(("Assignments declined", str(declined)))
    if overdue:
        summary_rows.append(("Currently overdue", str(overdue)))
    if response_rate is not None:
        summary_rows.append(("Acceptance rate", f"{response_rate}%"))
    if on_time_rate is not None:
        summary_rows.append(("Completed on or before due date", f"{on_time_rate}%"))

    return {
        "total_assigned": total,
        "reviews_completed": completed_count,
        "reviews_in_progress": accepted_open,
        "awaiting_response": new_count,
        "declined": declined,
        "overdue": overdue,
        "response_rate": response_rate,
        "on_time_rate": on_time_rate,
        "summary_rows": summary_rows,
        "recommendation_rows": recommendation_rows,
    }


def values(user, stats):
    _kind, role = membership.membership_role(user)
    article = "an" if role[:1].lower() in "aeiou" else "a"
    member_since = getattr(user, "membership_confirmed_at", None)
    return {
        "recipient_name": user.full_name,
        "first_name": user.first_name or user.full_name,
        "role": role,
        "a_role": f"{article} {role}",
        "ethics_id": getattr(user, "membership_ethics_id", None) or "",
        "institution": getattr(user, "institution", "") or "",
        "email": user.email,
        "member_since": letters.date_text(timezone.localtime(member_since)) if member_since else "—",
        "reviews_completed": str(stats["reviews_completed"]),
        "total_assigned": str(stats["total_assigned"]),
        "committee_name": COMMITTEE_NAME,
        "today": letters.date_text(timezone.localtime()),
    }


def report_content(user, template=None, *, stats=None):
    t = _template(template)
    if stats is None:
        stats = gather_stats(user)
    v = values(user, stats)

    body = [("text", fill(p, v)) for p in _paragraphs(t.report_body)]
    # One tinted panel per line: label is the stat name, the figure rides on
    # the same line. "plain" drops the coloured left rule -- these are a data
    # summary, not an alert.
    body.append(("box", ("Summary of Review Activity",
                         [[f"{label}:  {value}"] for label, value in stats["summary_rows"]],
                         {"plain": True})))
    if stats["recommendation_rows"]:
        body.append(("box", ("Recommendations Issued",
                             [[f"{label}:  {value}"] for label, value in stats["recommendation_rows"]],
                             {"plain": True})))

    return {
        "values": v,
        "doc_label": "Reviewer Activity Report",
        "ethics_id": v["ethics_id"],
        "date": timezone.now(),
        "flag": "ACTIVITY REPORT",
        "subject": fill(t.report_subject, v),
        "salutation": fill(t.salutation, v),
        "body": body,
        "closing": [fill(p, v) for p in _paragraphs(t.closing)],
        "sign_off": fill(t.sign_off, v),
        "signatory": letters.signatory(t),
    }


def _paragraphs(text):
    """Blank-line-separated paragraphs as single strings (keeping intra-
    paragraph wording), matching how the letter engine expects body text."""
    return [" ".join(lines) for lines in letters.text_blocks(text)] or [""]


def render_report_pdf(user, template=None, *, stats=None):
    t = _template(template)
    return letters.render(user, report_content(user, t, stats=stats), t)[0]


def report_filename(user):
    ref = (getattr(user, "membership_ethics_id", None) or str(user.pk)).replace("/", "-")
    return f"MSREC-Reviewer-Activity-Report-{ref}.pdf"


def sample_user():
    """A realistic stand-in for the Site Settings preview."""
    now = timezone.now()
    return SimpleNamespace(
        pk=0, full_name="Dr. Kwabena Osei", first_name="Kwabena", email="k.osei@example.com",
        position="Senior Lecturer", institution="Kwame Nkrumah University of Science and Technology",
        role="reviewer", committee_status="not_requested", committee_profile={},
        membership_ethics_id=f"MSREC/ER/{now.year}/0031",
        membership_confirmed_at=now.replace(year=now.year - 1),
    )


def sample_stats():
    """Stable figures for the settings preview (no DB access)."""
    return {
        "total_assigned": 28, "reviews_completed": 23, "reviews_in_progress": 2,
        "awaiting_response": 1, "declined": 2, "overdue": 0,
        "response_rate": 93, "on_time_rate": 91,
        "summary_rows": [
            ("Total assignments received", "28"),
            ("Reviews completed", "23"),
            ("Reviews in progress", "2"),
            ("Awaiting your response", "1"),
            ("Assignments declined", "2"),
            ("Acceptance rate", "93%"),
            ("Completed on or before due date", "91%"),
        ],
        "recommendation_rows": [
            ("Approve", "11"),
            ("Approve Subject to Minor Revisions", "7"),
            ("Major Revisions Required / Resubmission Required", "3"),
            ("Refer for Full Committee Review", "2"),
        ],
    }
