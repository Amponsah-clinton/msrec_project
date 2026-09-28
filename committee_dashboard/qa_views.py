"""Quality Assurance for the Committee dashboard.

Thin wrappers around reviewer_dashboard.qa's business logic -- a Committee
member is always also an approved Reviewer (accounts.models.User.
approve_role), so request.user has the same ReviewAssignment/ReviewQANote
rows either dashboard reads; only the template (and its nav/branding)
differs from reviewer_dashboard.views' equivalent four views.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from reviewer_dashboard import qa
from reviewer_dashboard.models import ReviewQANote

from .views import committee_required


@login_required
@committee_required
def qa_quality_check(request):
    report = qa.quality_check_report(request.user)
    return render(request, "dashboards/committee/qa-quality-check.html", {
        "report": report,
        "clean_count": sum(1 for row in report if row["is_clean"]),
        "flagged_count": sum(1 for row in report if not row["is_clean"]),
    })


@login_required
@committee_required
def qa_pending_actions(request):
    if request.method == "POST":
        note = get_object_or_404(
            ReviewQANote, pk=request.POST.get("note_id"), assignment__reviewer=request.user,
            action_required=True, status=ReviewQANote.Status.OPEN,
        )
        resolution_note = request.POST.get("resolution_note", "").strip()
        if not resolution_note:
            messages.error(request, "Describe how you addressed this before submitting.")
        else:
            qa.resolve_qa_note(
                note, resolution_note=resolution_note,
                review_notes=request.POST.get("review_notes"),
                key_concerns=request.POST.get("key_concerns"),
                recommendation_reason=request.POST.get("recommendation_reason"),
            )
            qa.notify_qa_note_resolved(note)
            messages.success(request, "Your response has been submitted.")
        return redirect("committee_dashboard:qa_pending_actions")

    return render(request, "dashboards/committee/qa-pending-actions.html", {
        "notes": list(qa.pending_qa_actions(request.user).order_by("-created_at")),
    })


@login_required
@committee_required
def qa_feedback(request):
    notes = list(qa.qa_feedback_history(request.user).order_by("-created_at"))
    return render(request, "dashboards/committee/qa-feedback.html", {
        "notes": notes,
        "open_count": sum(1 for n in notes if n.status == ReviewQANote.Status.OPEN),
        "resolved_count": sum(1 for n in notes if n.status == ReviewQANote.Status.RESOLVED),
    })


@login_required
@committee_required
def qa_performance(request):
    return render(request, "dashboards/committee/qa-performance.html", {
        "stats": qa.performance_summary(request.user),
    })
