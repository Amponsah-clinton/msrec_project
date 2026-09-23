from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render

from accounts.models import User
from notifications import services as notification_services
from notifications.models import Notification


def is_committee(user):
    # committee_status is the real permission here, not the primary `role`
    # (which only picks the default post-login dashboard, via
    # User.dashboard_url_name) -- same reasoning as reviewer_dashboard.
    # views.is_reviewer. An applicant-primary account whose Committee
    # request was approved (committee_status=APPROVED) must still pass
    # this even if `role` was never promoted to "committee" or was later
    # edited back (e.g. from the Accounts page's Edit modal, which lets
    # an admin change `role` independently of the approval statuses) --
    # otherwise an approved member can be locked out of the dashboard
    # their own approval was supposed to unlock.
    return user.is_authenticated and user.committee_status == User.RequestStatus.APPROVED


committee_required = user_passes_test(is_committee, login_url="pages:login")


@login_required
@committee_required
def home(request):
    from .meeting_views import home_context

    return render(request, "dashboards/committee.html", {
        "notifications": notification_services.for_user(request.user, Notification.Audience.COMMITTEE, limit=6),
        "unread_count": notification_services.unread_count(request.user, Notification.Audience.COMMITTEE),
        **home_context(request),
    })


# Notifications / Profile & Committee Appointment / Security live in
# account_views.py; re-exported so urls.py can keep using `views.<name>`.
from .account_views import certificate_download, notifications, profile, security  # noqa: E402,F401

# Meetings & Agenda live in meeting_views.py; same re-export.
from .meeting_views import (  # noqa: E402,F401
    agenda,
    agenda_note_save,
    meeting_rsvp,
    meetings_calendar,
    meetings_previous,
    meetings_upcoming,
)
