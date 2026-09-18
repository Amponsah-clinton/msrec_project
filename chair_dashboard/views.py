from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render

from accounts.models import User
from notifications import services as notification_services
from notifications.models import Notification


def is_chair(user):
    return user.is_authenticated and user.role == User.Role.CHAIR


chair_required = user_passes_test(is_chair, login_url="pages:login")


@login_required
@chair_required
def home(request):
    return render(request, "dashboards/chair.html", {
        "notifications": notification_services.for_user(request.user, Notification.Audience.CHAIR, limit=6),
        "unread_count": notification_services.unread_count(request.user, Notification.Audience.CHAIR),
    })
