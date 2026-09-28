"""Quality Assurance over Reviewer/Committee assessments.

Shared by both reviewer_dashboard and committee_dashboard views -- a
Committee member is always also an approved Reviewer (accounts.models.
User.approve_role grants reviewer_status=APPROVED the moment a Committee
request is approved), so both dashboards' "Quality Assurance" section
reads the SAME underlying ReviewAssignment rows for request.user. There is
no separate Committee-side review-quality model.

Four ideas, one per QA nav sub-page:
  * Review Quality Check   -- completeness_issues() + consistency_issues()
    run against every one of the reviewer's own COMPLETED assignments,
    alongside the assessment's already-recorded checklist answers.
  * Pending QA Actions     -- open (action_required, unresolved)
    ReviewQANote rows raised by QA staff on the reviewer's work.
  * QA Feedback            -- every ReviewQANote ever raised on this
    reviewer's work, resolved or not (Pending QA Actions is the open
    subset of this).
  * My Review Performance  -- simple aggregate stats: completed/active/
    overdue counts, average turnaround, and how many assignments have
    ever needed a QA correction.
"""
from django.conf import settings
from django.db.models import Avg, F
from django.urls import reverse
from django.utils import timezone

from .models import ReviewAssignment, ReviewQANote


def is_qa_staff(user):
    """Who can raise/manage a QA note on somebody else's review: the
    Secretariat and Chair (the brief's "QA officer or committee chair")
    plus Admin oversight. There's no dedicated QA role in this project
    (accounts.models.User.Role) -- adding one would mean touching
    dashboard_url_name(), approve_role() and every is_x gate across every
    dashboard for a role that would only ever do one thing, so piggy-
    backing on these three existing staff roles is deliberate."""
    from accounts.models import User

    return user.is_authenticated and (
        user.is_superuser or user.role in (User.Role.ADMIN, User.Role.SECRETARIAT, User.Role.CHAIR)
    )


# ---------------------------------------------------------------------------
# Review Quality Check
# ---------------------------------------------------------------------------

def completed_assignments_for(user):
    return (
        ReviewAssignment.objects.filter(reviewer=user, status=ReviewAssignment.Status.COMPLETED)
        .select_related("application")
        .order_by("-completed_at")
    )


def completeness_issues(assignment):
    """What a Completed assessment is missing that it should have -- the
    brief's "Incomplete Review Alerts". A list of short human-readable
    strings; empty means clean. Checked here rather than blocked at
    submission time in review_application(), so an assignment completed
    before a rule existed still surfaces it retroactively."""
    issues = []
    if not assignment.recommendation:
        issues.append("No recommendation was recorded.")
    answered = {k: v for k, v in (assignment.checklist or {}).items() if v}
    missing_rows = [label for key, label in ReviewAssignment.CHECKLIST_ITEMS if not answered.get(key)]
    if missing_rows:
        noun = "item" if len(missing_rows) == 1 else "items"
        issues.append(f"{len(missing_rows)} checklist {noun} left unanswered.")
    if not assignment.review_notes.strip():
        issues.append("No overall review comments were recorded.")
    if (
        assignment.recommendation
        and assignment.recommendation != ReviewAssignment.Recommendation.APPROVE
        and not assignment.recommendation_reason.strip()
    ):
        issues.append("A recommendation other than Approve was given with no supporting reason.")
    if not assignment.confidentiality_confirmed:
        issues.append("The confidentiality declaration was not confirmed.")
    return issues


def consistency_issues(assignment):
    """Contradictions between the checklist, the concerns noted and the
    final recommendation -- the brief's "Review Consistency Check". Pure
    rule-based checks over already-recorded fields; not a score, and
    nothing here is persisted -- it's recomputed fresh every time."""
    issues = []
    needs_revision_rows = [
        label for key, label in ReviewAssignment.CHECKLIST_ITEMS
        if (assignment.checklist or {}).get(key) == "needs_revision"
    ]
    rec = assignment.recommendation
    Rec = ReviewAssignment.Recommendation
    if rec == Rec.APPROVE and needs_revision_rows:
        noun = "item" if len(needs_revision_rows) == 1 else "items"
        issues.append(
            f"Recommended Approve, but {len(needs_revision_rows)} checklist {noun} "
            "marked “Needs Revision”."
        )
    if rec == Rec.APPROVE and assignment.key_concerns.strip():
        issues.append("Recommended Approve, but key concerns were also recorded.")
    if rec in (Rec.MAJOR_REVISIONS, Rec.NOT_APPROVED) and not needs_revision_rows and not assignment.key_concerns.strip():
        issues.append(
            "Major Revisions / Not Approved was recommended with no checklist item or key "
            "concern flagged to justify it."
        )
    if assignment.coi_has_conflict and not assignment.coi_details.strip():
        issues.append("A conflict of interest was declared but no details were given.")
    return issues


def quality_summary(assignment):
    completeness = completeness_issues(assignment)
    consistency = consistency_issues(assignment)
    return {
        "assignment": assignment,
        "completeness_issues": completeness,
        "consistency_issues": consistency,
        "issue_count": len(completeness) + len(consistency),
        "is_clean": not completeness and not consistency,
    }


def quality_check_report(user):
    return [quality_summary(a) for a in completed_assignments_for(user)]


# ---------------------------------------------------------------------------
# Pending QA Actions / QA Feedback
# ---------------------------------------------------------------------------

def pending_qa_actions(user):
    return (
        ReviewQANote.objects.filter(
            assignment__reviewer=user, action_required=True, status=ReviewQANote.Status.OPEN,
        )
        .select_related("assignment", "assignment__application", "raised_by")
    )


def qa_feedback_history(user):
    return (
        ReviewQANote.objects.filter(assignment__reviewer=user)
        .select_related("assignment", "assignment__application", "raised_by")
    )


def pending_qa_count(user):
    return pending_qa_actions(user).count()


def resolve_qa_note(note, *, resolution_note, review_notes=None, key_concerns=None, recommendation_reason=None):
    """The reviewer's response to a Pending QA Action: records what they
    told the QA officer/Chair, and optionally revises the narrative parts
    of the underlying assessment -- review_notes / key_concerns /
    recommendation_reason. The checklist and recommendation choice itself
    stay as originally submitted on the Reviewer Assessment Form; this is
    for clarifying/correcting the write-up, not resubmitting the whole
    assessment."""
    assignment = note.assignment
    update_fields = []
    for field, value in (
        ("review_notes", review_notes),
        ("key_concerns", key_concerns),
        ("recommendation_reason", recommendation_reason),
    ):
        if value is not None and value != getattr(assignment, field):
            setattr(assignment, field, value)
            update_fields.append(field)
    if update_fields:
        assignment.save(update_fields=update_fields)

    note.status = ReviewQANote.Status.RESOLVED
    note.resolved_at = timezone.now()
    note.resolution_note = resolution_note
    note.save(update_fields=["status", "resolved_at", "resolution_note"])
    return note


# ---------------------------------------------------------------------------
# My Review Performance
# ---------------------------------------------------------------------------

def performance_summary(user):
    today = timezone.localdate()
    assignments = ReviewAssignment.objects.filter(reviewer=user).exclude(
        status=ReviewAssignment.Status.DECLINED
    )
    completed = assignments.filter(status=ReviewAssignment.Status.COMPLETED)
    active = assignments.filter(
        status__in=[ReviewAssignment.Status.NEW, ReviewAssignment.Status.ACCEPTED]
    )
    overdue = assignments.filter(status=ReviewAssignment.Status.ACCEPTED, due_date__lte=today)

    turnaround = completed.filter(completed_at__isnull=False).aggregate(
        avg_days=Avg(F("completed_at") - F("assigned_at"))
    )["avg_days"]
    avg_turnaround_days = round(turnaround.total_seconds() / 86400, 1) if turnaround else None

    correction_count = (
        ReviewQANote.objects.filter(assignment__reviewer=user, action_required=True)
        .values("assignment_id").distinct().count()
    )

    return {
        "completed_count": completed.count(),
        "active_count": active.count(),
        "overdue_count": overdue.count(),
        "avg_turnaround_days": avg_turnaround_days,
        "correction_count": correction_count,
        "pending_qa_count": pending_qa_count(user),
    }


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def notify_qa_note_raised(note):
    """Emails the reviewer the moment QA staff raise a note on their
    completed assignment -- fail_silently, same contract as every other
    email in this project; a mail problem never blocks the note being
    saved. Only a real action item gets its own email; pure feedback
    (action_required=False) is quieter and just waits to be read on the
    QA Feedback page, same as an in-app-only notice."""
    from notifications.emails import send_branded_email

    assignment = note.assignment
    ref = assignment.application.reference_no or assignment.application.title
    login_url = settings.SITE_URL.rstrip("/") + reverse("pages:login")
    if note.action_required:
        subject = f"MSREC — action needed on your review ({ref})"
        heading = "A Quality Assurance action is needed on your review"
        paragraphs = [
            f"Dear {assignment.reviewer.first_name or assignment.reviewer.full_name},",
            f"The Secretariat/Chair has reviewed your assessment of “{assignment.application.title}” "
            f"({ref}) and needs clarification, correction, or additional justification before it can proceed.",
        ]
    else:
        subject = f"MSREC — QA feedback on your review ({ref})"
        heading = "New Quality Assurance feedback on your review"
        paragraphs = [
            f"Dear {assignment.reviewer.first_name or assignment.reviewer.full_name},",
            f"The Secretariat/Chair has left feedback on your assessment of “{assignment.application.title}” "
            f"({ref}).",
        ]
    return send_branded_email(
        subject=subject,
        to=assignment.reviewer.email,
        heading=heading,
        paragraphs=paragraphs,
        quote_label="Their note",
        quote_text=note.message,
        cta_text="View in my dashboard",
        cta_url=login_url,
        preheader=subject,
    )


def notify_qa_note_resolved(note):
    """Tells whoever raised the note that the reviewer has responded --
    fail_silently, same contract as above. Silently no-ops if the raising
    account has since been deleted (raised_by is SET_NULL)."""
    if not note.raised_by:
        return False
    from notifications.emails import send_branded_email

    assignment = note.assignment
    ref = assignment.application.reference_no or assignment.application.title
    login_url = settings.SITE_URL.rstrip("/") + reverse("pages:login")
    return send_branded_email(
        subject=f"MSREC — {assignment.reviewer.full_name} responded to your QA note ({ref})",
        to=note.raised_by.email,
        heading="A reviewer has responded to your QA note",
        paragraphs=[
            f"Dear {note.raised_by.first_name or note.raised_by.full_name},",
            f"{assignment.reviewer.full_name} has responded to your Quality Assurance note on "
            f"“{assignment.application.title}” ({ref}).",
        ],
        quote_label="Their response",
        quote_text=note.resolution_note,
        cta_text="View in my dashboard",
        cta_url=login_url,
        preheader=f"{assignment.reviewer.full_name} responded to your QA note on {ref}.",
    )
