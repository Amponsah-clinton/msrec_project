from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render

from accounts.models import User
from notifications import services as notification_services
from notifications.models import Notification


def is_committee(user):
    return (
        user.is_authenticated
        and user.role == User.Role.COMMITTEE
        and user.committee_status == User.RequestStatus.APPROVED
    )


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
from .account_views import notifications, profile, security  # noqa: E402,F401

# Meetings & Agenda live in meeting_views.py; same re-export.
from .meeting_views import (  # noqa: E402,F401
    agenda,
    agenda_note_save,
    meeting_rsvp,
    meetings_calendar,
    meetings_previous,
    meetings_upcoming,
)
