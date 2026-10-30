"""Deadline alerts to the CEO: "this piece of work is due in N days".

About the work, not the money. An agreement carries an expected
completion date, and once that date is five, three and one day away the
CEO is told, so a delivery nobody has looked at lately gets noticed
before it slips rather than after.

Fired opportunistically from the PSA list, the page the people who run
these agreements open anyway -- the same arrangement, and for the same
reason, as reviewer_dashboard.reminders: there is no Celery or cron in
this project. Each milestone is sent once (recorded on the agreement), so
calling this on every page load is exactly as safe as calling it once, and
a `send_psa_deadline_alerts` command exists for anyone who does have a
scheduler and would rather not wait for someone to open a page.

Two details worth knowing:

  * Catching up. If nobody opened the list on the day a milestone fell
    due, the next run still sends it, and says how many days are actually
    left rather than repeating the milestone's number. One email goes per
    agreement per run, however many milestones were missed.
  * Moving the date. The record is keyed on the completion date, so
    pushing a deadline back re-arms all three alerts for the new date
    instead of staying quiet because the old one was already announced.
"""
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

# Days before the completion date that the CEO hears about it.
MILESTONES = (5, 3, 1)

# An alert is about work still to be delivered, so it follows agreements
# that are live: a draft isn't a commitment yet and a cancelled one has
# nothing left to deliver.
LIVE_STATUSES = ("sent", "changes", "signed")


def _state_for(agreement):
    """The alert record as it applies to the deadline now on the
    agreement. A date that has moved gets a clean record."""
    key = agreement.completion_date.isoformat()
    state = agreement.deadline_alerts or {}
    if state.get("for") != key or not isinstance(state.get("sent"), list):
        return {"for": key, "sent": []}
    return {"for": key, "sent": [m for m in state["sent"] if m in MILESTONES]}


def due_soon(today=None):
    """Live, unarchived agreements whose deadline is within the widest
    milestone -- the ones worth looking at this run."""
    from datetime import timedelta

    from .models import ServiceAgreement

    today = today or timezone.localdate()
    return (
        ServiceAgreement.objects.filter(
            status__in=LIVE_STATUSES,
            archived_at__isnull=True,
            completion_date__isnull=False,
            completion_date__gte=today,
            completion_date__lte=today + timedelta(days=max(MILESTONES)),
        )
        .select_related("created_by")
        .order_by("completion_date")
    )


def send_due_soon_alerts(today=None):
    """Alert the CEO about every agreement that has reached a milestone
    it hasn't been alerted on. Returns how many alerts were sent.

    Never raises: this runs off a page load, and a mail server having a
    bad afternoon must not take the agreements list down with it."""
    from . import emails

    today = today or timezone.localdate()
    sent = 0
    for a in due_soon(today):
        days_left = (a.completion_date - today).days
        state = _state_for(a)
        # Every milestone the deadline has passed under, including any
        # missed while nobody was looking.
        reached = [m for m in MILESTONES if m >= days_left]
        if not [m for m in reached if m not in state["sent"]]:
            continue
        try:
            delivered = emails.send_deadline_alert(a, days_left)
        except Exception:
            logger.exception("PSA deadline alert failed for %s", a.reference)
            continue
        if not delivered:
            # Left unmarked so the next run tries again rather than
            # swallowing the one alert that mattered.
            continue
        state["sent"] = sorted(set(state["sent"]) | set(reached), reverse=True)
        a.deadline_alerts = state
        a.save(update_fields=["deadline_alerts"])
        sent += 1
    return sent


def send_quietly(today=None):
    """send_due_soon_alerts for callers that must not fail -- the list
    view, which has its own job to do."""
    try:
        return send_due_soon_alerts(today)
    except Exception:
        logger.exception("PSA deadline alerts failed")
        return 0
