"""Deadline reminder emails for open (not yet completed) review
assignments -- "left unattended by the reviewer with 3 days to go".

No Celery/cron in this project (same constraint communications.Reminder's
docstring explains), so send_due_soon_reminders() is opportunistic: it's
safe and cheap to call on every page load of a dashboard a reviewer -- or
a Committee member holding a review assignment, since _approved_reviewers()
pools both -- is likely to visit (reviewer_dashboard's own home,
Committee's dashboard, Secretariat's Reviewer Assignment page). Each
assignment is reminded at most once (deadline_reminder_sent_at), so
calling this from three different views is exactly as safe as calling it
from one -- whichever page loads first within the window sends it, and
every later call that day (or from another page) is a no-op for that
assignment.

A `send_review_deadline_reminders` management command also exists for
anyone who *does* have a scheduler available (cron, a platform's
scheduled-job feature) to call this directly rather than relying on
someone loading a page -- see that command for how to wire it up.
"""
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from notifications.emails import send_branded_email

from .models import ReviewAssignment

REMINDER_WINDOW_DAYS = 3


def _due_soon_qs():
    today = timezone.localdate()
    cutoff = today + timedelta(days=REMINDER_WINDOW_DAYS)
    return (
        ReviewAssignment.objects.filter(
            status__in=[ReviewAssignment.Status.NEW, ReviewAssignment.Status.ACCEPTED],
            due_date__isnull=False,
            due_date__gte=today,
            due_date__lte=cutoff,
            deadline_reminder_sent_at__isnull=True,
        )
        .select_related("application", "reviewer")
    )


def _login_url(request=None):
    if request is not None:
        return request.build_absolute_uri(reverse("pages:login"))
    return f"{settings.SITE_URL.rstrip('/')}{reverse('pages:login')}"


def _send_reminder_email(assignment, *, login_url):
    reviewer = assignment.reviewer
    application = assignment.application
    days_left = (assignment.due_date - timezone.localdate()).days
    when = "today" if days_left == 0 else ("tomorrow" if days_left == 1 else f"in {days_left} days")

    return send_branded_email(
        subject=f"Reminder: your review is due {when} — {application.reference_no or application.title}",
        to=reviewer.email,
        heading="Your review is due soon",
        paragraphs=[
            f"Hi {reviewer.full_name},",
            f"Your review of \"{application.title}\" ({application.reference_no or 'reference pending'}) "
            f"is due {when} ({assignment.due_date:%d %b %Y}), and hasn't been submitted yet.",
            "Log in to My Reviews to accept it (if you haven't already) and submit your assessment "
            "before the deadline.",
        ],
        cta_text="Go to My Reviews",
        cta_url=login_url,
        preheader=f"Your review is due {when}.",
    )


def send_due_soon_reminders(request=None):
    """Emails every reviewer whose open assignment is due within
    REMINDER_WINDOW_DAYS days and hasn't been reminded about it yet.
    Returns the number sent -- callers in the opportunistic "just call
    this on page load" case ignore it; the management command reports it.

    Marks deadline_reminder_sent_at *before* attempting the send (not
    after) so a slow/failing SMTP connection can never cause the same
    reviewer to be emailed twice for one assignment on a retry -- the
    email itself already degrades gracefully (send_branded_email's
    fail_silently=True just logs and returns False on failure)."""
    login_url = _login_url(request)
    sent = 0
    for assignment in _due_soon_qs():
        assignment.deadline_reminder_sent_at = timezone.now()
        assignment.save(update_fields=["deadline_reminder_sent_at"])
        if _send_reminder_email(assignment, login_url=login_url):
            sent += 1
    return sent
