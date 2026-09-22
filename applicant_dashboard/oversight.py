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

from accounts.models import AuditLog, User
from notifications.emails import send_branded_email

from .models import Application

# tab key -> Application.Status ("all" has no filter, so it maps to None)
STATUS_TABS = {
    "all": None,
    "submitted": Application.Status.SUBMITTED,
    "under_review": Application.Status.UNDER_REVIEW,
    "with_committee": Application.Status.WITH_COMMITTEE,
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


def apply_transition(application, action, *, comment="", actor=None, request=None):
    """Applies one of STATUS_ACTIONS to `application` and saves it.
    Returns (ok, message) -- ok=False (with an error message) if `action`
    isn't a recognized transition.

    `comment` is only meaningful for "request_revisions" -- the
    Secretariat's note on what the applicant needs to fix, shown on their
    Revisions Required page and included in the email apply_transition's
    caller sends (see secretariat_dashboard.views). Required: a
    revisions-required email with nothing to act on ("MSREC reviewed your
    application and it needs changes") leaves the applicant guessing, so
    this is rejected before any state changes rather than silently sent.

    `actor` is whichever staff user (Secretariat or Admin -- both call
    this same helper) made the decision, purely for the audit trail;
    omitting it just skips logging rather than erroring, so existing
    callers that predate the audit log don't need updating.

    `request` is only used to build the login link in the email sent to
    any reviewer whose open assignment gets auto-withdrawn below (see
    _withdraw_open_assignments) -- omitting it just skips that email."""
    transition = STATUS_ACTIONS.get(action)
    if not transition:
        return False, "That request could not be processed."
    if action == "request_revisions" and not comment.strip():
        return False, "Describe what the applicant needs to change before sending a revision request."

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
    if actor is not None:
        AuditLog.record(actor, f"application.{action}", target=application)

    # A reviewer's still-open (not yet completed) assignment stops making
    # sense the moment the application leaves review this way -- sent back
    # to the applicant for revisions, or already decided -- so it's cleared
    # here rather than left dangling on that reviewer's My Reviews list for
    # a study that isn't actually awaiting their input anymore. Referring
    # to Committee deliberately does NOT go through here (see
    # refer_to_committee below): a reviewer's in-progress assessment is
    # still live input the Committee wants, not stale work.
    if new_status in (Application.Status.REVISIONS_REQUIRED, Application.Status.APPROVED, Application.Status.NOT_APPROVED):
        _withdraw_open_assignments(application, request=request, reason=note)

    return True, note


def _withdraw_open_assignments(application, *, request=None, reason=""):
    """Deletes every New/Accepted ReviewAssignment on `application` --
    exactly what the Secretariat's own manual Withdraw does (see
    secretariat_dashboard.views.reviewer_assignment's "withdraw" branch),
    just triggered automatically by a status change that makes an open
    assignment stale instead of a deliberate click. A Completed or
    Declined assignment is left alone -- there's nothing "open" about
    either, and a completed one is exactly what the Secretariat is acting
    on right now."""
    from reviewer_dashboard.models import ReviewAssignment

    open_assignments = list(
        ReviewAssignment.objects.filter(
            application=application,
            status__in=[ReviewAssignment.Status.NEW, ReviewAssignment.Status.ACCEPTED],
        ).select_related("reviewer")
    )
    for assignment in open_assignments:
        AuditLog.record(
            None, "review_assignment.auto_withdrawn", target=application,
            description=f"{assignment.reviewer.full_name}'s open assignment was cleared -- {reason}",
        )
        if request is not None:
            login_url = request.build_absolute_uri(reverse("pages:login"))
            send_branded_email(
                subject=f"Review assignment withdrawn — {application.reference_no or application.title}",
                to=assignment.reviewer.email,
                heading="A review assignment was withdrawn",
                paragraphs=[
                    f"Hi {assignment.reviewer.full_name},",
                    f"You've been withdrawn from reviewing \"{application.title}\" "
                    f"({application.reference_no or 'reference pending'}) -- no action is needed from you, "
                    "and it no longer appears on your My Reviews list.",
                ],
                cta_text="Log in to MSREC",
                cta_url=login_url,
                preheader="One of your review assignments was withdrawn.",
            )
        assignment.delete()


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


def send_decision_email(request, application, action):
    """Tells the applicant MSREC's final decision -- called by both
    admin_dashboard and secretariat_dashboard right after
    apply_transition("approve"/"not_approve") succeeds, same "one shared
    helper so both staff sides can never drift" pattern as
    send_revisions_requested_email above. `action` is the same
    STATUS_ACTIONS key apply_transition was just called with; anything
    else is a no-op (returns False) since only these two are decisions."""
    login_url = request.build_absolute_uri(reverse("pages:login"))
    if action == "approve":
        subject = f"Application approved — {application.reference_no}"
        heading = "Your application has been approved"
        paragraphs = [
            f"Hi {application.applicant.full_name},",
            f"Congratulations — MSREC has approved \"{application.title}\" ({application.reference_no}). "
            "Your ethics approval documents are available on your Applicant dashboard.",
            "Any post-approval obligations (progress reports, amendments, adverse events) can also be "
            "submitted from there for the lifetime of the study.",
        ]
        preheader = f"{application.reference_no} has been approved."
    elif action == "not_approve":
        subject = f"Application decision — {application.reference_no}"
        heading = "Decision on your application"
        paragraphs = [
            f"Hi {application.applicant.full_name},",
            f"MSREC has reviewed \"{application.title}\" ({application.reference_no}) and is unable to "
            "approve it in its current form.",
            "Log in to your Applicant dashboard for the Committee's full reasoning, and contact the "
            "Secretariat if you have questions about next steps.",
        ]
        preheader = f"A decision has been recorded on {application.reference_no}."
    else:
        return False
    return send_branded_email(
        subject=subject,
        to=application.applicant.email,
        heading=heading,
        paragraphs=paragraphs,
        cta_text="View My Application",
        cta_url=login_url,
        preheader=preheader,
    )


def refer_to_committee(request, application, *, member_ids, platform, meeting_link, scheduled_at,
                        duration_minutes=90, info="", actor=None):
    """Schedules a deliberation meeting for `application` and invites the
    chosen Committee members to it -- the Secretariat's "set up a
    Committee meeting" action, called by both admin_dashboard and
    secretariat_dashboard's application_detail views (same shared-helper
    pattern as send_revisions_requested_email/send_decision_email above,
    so the two staff sides can never drift).

    Deliberately NOT a STATUS_ACTIONS entry / apply_transition() call --
    every other transition there is a pure status flip, but this one also
    creates real rows (a meetings.Meeting, its AgendaItem linking it to
    this application, and one MeetingParticipant per chosen member) and
    needs caller-supplied meeting details apply_transition's flat
    (status, note) shape has no room for.

    A member becomes able to see this application the moment their
    MeetingParticipant row exists (see committee_dashboard.protocol_views.
    _protocol_rows, which derives a member's visible protocols entirely
    from "am I a participant on a meeting whose agenda includes this
    application" -- no separate "assignment" concept to maintain here).
    The invitation email links straight to that page (committee_dashboard:
    protocol_detail) so a member can actually open and read the
    application before the meeting, not just be told a meeting exists.

    Returns (ok, message, meeting-or-None).
    """
    from meetings.models import AgendaItem, Meeting, MeetingParticipant
    from meetings.services import send_meeting_invites

    members = list(User.objects.filter(
        pk__in=member_ids, role=User.Role.COMMITTEE, committee_status=User.RequestStatus.APPROVED,
    ))
    if not members:
        return False, "Choose at least one Committee member to invite.", None
    if not scheduled_at:
        return False, "Choose a meeting date and time.", None

    label = application.reference_no or application.title or f"Application #{application.pk}"
    description = f'Committee deliberation on "{application.title}" ({label}), via {platform or "the link below"}.'
    if info:
        description += f"\n\n{info}"

    meeting = Meeting.objects.create(
        title=f"Deliberation — {label}"[:200],
        meeting_type=Meeting.MeetingType.FULL_COMMITTEE,
        description=description,
        scheduled_at=scheduled_at,
        duration_minutes=duration_minutes or 90,
        mode=Meeting.Mode.VIRTUAL if meeting_link else Meeting.Mode.IN_PERSON,
        meeting_link=meeting_link,
        chair=actor if actor is not None and actor.role == User.Role.CHAIR else None,
        created_by=actor,
    )
    AgendaItem.objects.create(
        meeting=meeting, application=application,
        title=f"Deliberate: {label}"[:255],
        description=info,
    )
    for member in members:
        MeetingParticipant.objects.create(
            meeting=meeting, user=member,
            role_at_meeting=MeetingParticipant.ParticipantRole.MEMBER, is_voting=True,
        )

    application.status = Application.Status.WITH_COMMITTEE
    application.save(update_fields=["status"])

    if actor is not None:
        AuditLog.record(
            actor, "application.referred_to_committee", target=application,
            description=(
                f"Referred to {len(members)} committee member(s) for deliberation "
                f"on {meeting.scheduled_at:%d %b %Y at %I:%M %p}."
            ),
        )

    review_url = request.build_absolute_uri(
        reverse("committee_dashboard:protocol_detail", kwargs={"pk": application.pk})
    )
    emailed = send_meeting_invites(
        meeting, kind="invitation", cta_text="Review the Application", cta_url=review_url,
    )
    plural = "s" if len(members) != 1 else ""
    note = f"Referred to {len(members)} committee member{plural} for deliberation."
    note += f" {emailed} notified by email." if emailed else " (the invitation emails couldn't be sent)."
    return True, note, meeting


def status_counts(base_qs):
    counts = {
        key: (base_qs.count() if status is None else base_qs.filter(status=status).count())
        for key, status in STATUS_TABS.items()
    }
    # "Revised" isn't a status -- it's "has been resubmitted at least once",
    # true at whatever status the application is currently sitting at (back
    # in New after a fix, or already moved on to Under Review/Approved/etc).
    # So it's tracked as an extra tag alongside `tab`, not a STATUS_TABS
    # entry, and counted separately here rather than via status=.
    counts["revised"] = base_qs.filter(resubmitted_at__isnull=False).count()
    return counts


def filter_tags_for(application):
    """The full set of tab keys `application` should show up under on the
    Applications list -- its current-status tab, plus "revised" if it's
    ever been resubmitted after a revision request. A card can match more
    than one filter tab at once (e.g. a resubmitted application now Under
    Review is both "under_review" and "revised")."""
    tags = [STATUS_TO_TAB.get(application.status, "all")]
    if application.resubmitted_at:
        tags.append("revised")
    return tags
