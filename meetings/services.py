"""Side effects around a Meeting -- sending invitation/update emails to
every participant and translating role into a bell Notification, kept
separate from views.py so more than one call site (schedule, reschedule,
cancel) can trigger the same email without duplicating it.
"""
from accounts.models import User
from notifications import services as notification_services
from notifications.emails import send_branded_email
from notifications.models import Notification

_NOTIFY_AUDIENCE = {
    User.Role.CHAIR: Notification.Audience.CHAIR,
    User.Role.COMMITTEE: Notification.Audience.COMMITTEE,
    User.Role.SECRETARIAT: Notification.Audience.SECRETARIAT,
    User.Role.ADMIN: Notification.Audience.ADMIN,
}


def _meeting_lines(meeting):
    when = f"{meeting.scheduled_at:%A, %d %B %Y} at {meeting.scheduled_at:%I:%M %p}"
    lines = [f"When: {when} ({meeting.duration_minutes} minutes)"]
    if meeting.mode in (meeting.Mode.IN_PERSON, meeting.Mode.HYBRID) and meeting.location:
        lines.append(f"Where: {meeting.location}")
    if meeting.mode in (meeting.Mode.VIRTUAL, meeting.Mode.HYBRID) and meeting.meeting_link:
        lines.append(f"Join link: {meeting.meeting_link}")
    if meeting.description:
        lines.append(meeting.description)
    return lines


def send_meeting_invites(meeting, *, participants=None, kind="invitation", cta_text=None, cta_url=None):
    """Emails every participant of `meeting` (or just `participants`, for
    a targeted resend) a branded notice, and posts one bell Notification
    per role represented so the relevant dashboards show it too. `kind`
    is either "invitation" (newly scheduled), "update" (rescheduled /
    details changed) or "cancellation".

    `cta_text`/`cta_url` add a button to the email -- used by
    applicant_dashboard.oversight.refer_to_committee to link straight to
    the application a deliberation meeting is about
    (committee_dashboard:protocol_detail), so an invited member can open
    and read it before the meeting instead of hunting for it after
    logging in. Optional and unused by plain (non-application) meetings.

    Returns the number of emails actually sent.
    """
    heading = {
        "invitation": f"You're invited: {meeting.title}",
        "update": f"Meeting updated: {meeting.title}",
        "cancellation": f"Meeting cancelled: {meeting.title}",
    }[kind]
    intro = {
        "invitation": "You have been added as a participant in the following meeting:",
        "update": "Details for a meeting you're part of have changed:",
        "cancellation": "The following meeting has been cancelled:",
    }[kind]

    rows = participants if participants is not None else list(meeting.participants.select_related("user"))

    sent = 0
    audiences_touched = set()
    for participant in rows:
        user = participant.user
        if not user or not user.email:
            continue
        paragraphs = [f"Hi {user.first_name or user.get_full_name() or 'there'},", intro]
        if kind != "cancellation":
            paragraphs.extend(_meeting_lines(meeting))
            paragraphs.append(f"Your role: {participant.get_role_at_meeting_display()}.")
            if cta_url:
                paragraphs.append(
                    "Please take a few minutes to review the material below before the meeting "
                    "so we can make the most of the time together."
                )
        ok = send_branded_email(
            subject=heading,
            to=user.email,
            heading=heading,
            paragraphs=paragraphs,
            cta_text=cta_text if kind != "cancellation" else None,
            cta_url=cta_url if kind != "cancellation" else None,
            preheader=heading,
        )
        if ok:
            sent += 1
        audience = _NOTIFY_AUDIENCE.get(user.role)
        if audience:
            audiences_touched.add(audience)

    for audience in audiences_touched:
        notification_services.notify(
            audience, heading,
            icon=Notification.Icon.INFO if kind != "cancellation" else Notification.Icon.WARN,
        )

    return sent
