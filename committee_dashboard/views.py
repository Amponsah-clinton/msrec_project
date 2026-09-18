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
    return render(request, "dashboards/committee.html", {
        "notifications": notification_services.for_user(request.user, Notification.Audience.COMMITTEE, limit=6),
        "unread_count": notification_services.unread_count(request.user, Notification.Audience.COMMITTEE),
    })
