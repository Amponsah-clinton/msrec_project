"""Shared staff-side application oversight helpers.

Both secretariat_dashboard and admin_dashboard offer the same "see every
submitted application, open one, move it through Start Review / Request
Revisions / Approve / Not Approve / Reopen" experience over the same
Application data -- they just gate it to different roles (secretariat_dashboard
via messaging.access.is_staff_side, admin_dashboard via its own stricter
admin_required). Keeping the tab/status/transition logic here means the two
can never drift out of sync with each other.
"""
from django.utils import timezone

from .models import Application

# tab key -> Application.Status ("all" has no filter, so it maps to None)
STATUS_TABS = {
    "all": None,
    "submitted": Application.Status.SUBMITTED,
    "under_review": Application.Status.UNDER_REVIEW,
    "revisions": Application.Status.REVISIONS_REQUIRED,
    "approved": Application.Status.APPROVED,
    "not_approved": Application.Status.NOT_APPROVED,
}

STATUS_TO_TAB = {status: key for key, status in STATUS_TABS.items() if status}

STATUS_ACTIONS = {
    "start_review": (Application.Status.UNDER_REVIEW, "Marked as under review."),
    "request_revisions": (Application.Status.REVISIONS_REQUIRED, "Revisions requested from the applicant."),
    "approve": (Application.Status.APPROVED, "Application approved."),
    "not_approve": (Application.Status.NOT_APPROVED, "Application marked not approved."),
    "reopen": (Application.Status.SUBMITTED, "Reopened for screening."),
}


def staff_queryset():
    # Drafts are the applicant's private working copy -- staff only ever
    # see an application once it's actually been submitted.
    return Application.objects.exclude(status=Application.Status.DRAFT).select_related("applicant")


def apply_transition(application, action):
    """Applies one of STATUS_ACTIONS to `application` and saves it.
    Returns (ok, message) -- ok=False (with an error message) if `action`
    isn't a recognized transition."""
    transition = STATUS_ACTIONS.get(action)
    if not transition:
        return False, "That request could not be processed."

    new_status, note = transition
    application.status = new_status
    update_fields = ["status"]
    if new_status in (Application.Status.APPROVED, Application.Status.NOT_APPROVED):
        application.decided_at = timezone.now()
        update_fields.append("decided_at")
    application.save(update_fields=update_fields)
    return True, note


def status_counts(base_qs):
    return {
        key: (base_qs.count() if status is None else base_qs.filter(status=status).count())
        for key, status in STATUS_TABS.items()
    }
