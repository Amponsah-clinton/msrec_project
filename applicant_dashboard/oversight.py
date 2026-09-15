"""Shared staff-side application oversight helpers.

Both secretariat_dashboard and admin_dashboard offer the same "see every
submitted application, open one, move it through Start Review / Request
Revisions / Approve / Not Approve / Reopen" experience over the same
Application data -- they just gate it to different roles (secretariat_dashboard
via messaging.access.is_staff_side, admin_dashboard via its own stricter
admin_required). Keeping the tab/status/transition logic here means the two
can never drift out of sync with each other.
"""
from django.urls import reverse
from django.utils import timezone

from notifications.emails import send_branded_email

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


def apply_transition(application, action, *, comment=""):
    """Applies one of STATUS_ACTIONS to `application` and saves it.
    Returns (ok, message) -- ok=False (with an error message) if `action`
    isn't a recognized transition.

    `comment` is only meaningful for "request_revisions" -- the
    Secretariat's optional note on what the applicant needs to fix,
    shown on their Revisions Required page and included in the email
    apply_transition's caller sends (see secretariat_dashboard.views)."""
    transition = STATUS_ACTIONS.get(action)
    if not transition:
        return False, "That request could not be processed."

    new_status, note = transition
    application.status = new_status
    update_fields = ["status"]
    if new_status in (Application.Status.APPROVED, Application.Status.NOT_APPROVED):
        application.decided_at = timezone.now()
        update_fields.append("decided_at")
    if new_status == Application.Status.REVISIONS_REQUIRED:
        application.revision_comment = comment.strip()
        application.revision_requested_at = timezone.now()
        application.revision_count += 1
        update_fields += ["revision_comment", "revision_requested_at", "revision_count"]
    application.save(update_fields=update_fields)
    return True, note


def send_revisions_requested_email(request, application):
    """Tells the applicant their application needs changes -- called by
    both admin_dashboard and secretariat_dashboard right after
    apply_transition("request_revisions") succeeds, so the two staff
    sides can never end up with one notifying and the other not."""
    login_url = request.build_absolute_uri(reverse("pages:login"))
    paragraphs = [
        f"Hi {application.applicant.full_name},",
        f"MSREC has reviewed \"{application.title}\" ({application.reference_no}) and needs some changes "
        "before it can move forward.",
    ]
    if application.revision_comment:
        paragraphs.append(
            "You can fix and resend it any time — log in, open the application from Revisions Required, "
            "make the changes, and resubmit. No review fee is charged again on a resend."
        )
    else:
        paragraphs.append(
            "Log in to see the full application and message the Secretariat for details on what's needed, "
            "then resubmit once it's fixed — no review fee is charged again on a resend."
        )
    return send_branded_email(
        subject=f"Revisions requested — {application.reference_no}",
        to=application.applicant.email,
        heading="Revisions requested on your application",
        paragraphs=paragraphs,
        quote_label="What MSREC asked for" if application.revision_comment else "",
        quote_text=application.revision_comment,
        cta_text="Log in to MSREC",
        cta_url=login_url,
        preheader=f"Revisions requested on {application.reference_no}.",
    )


def status_counts(base_qs):
    return {
        key: (base_qs.count() if status is None else base_qs.filter(status=status).count())
        for key, status in STATUS_TABS.items()
    }
