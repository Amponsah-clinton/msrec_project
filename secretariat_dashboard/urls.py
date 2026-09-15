from django.urls import path

from messaging import views as messaging_views

from . import views

app_name = "secretariat_dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("applications/", views.applications, name="applications"),
    path("applications/counts/", views.applications_counts, name="applications_counts"),
    path("applications/reviewer-deadline/", views.set_reviewer_deadline, name="set_reviewer_deadline"),
    path("applications/<int:pk>/", views.application_detail, name="application_detail"),
    path("finance/", views.finance, name="finance"),
    # Same shared staff inbox as admin_dashboard's (messaging.access.
    # is_staff_side already treats Secretariat and Admin as one "staff
    # side" of a conversation) -- just this dashboard's own template, so
    # the sidebar/topbar stay Secretariat-branded.
    path(
        "messages/", messaging_views.staff_messages,
        {"template_name": "dashboards/secretariat/messages.html"}, name="messages",
    ),
    path("messages/<int:conversation_id>/poll/", messaging_views.staff_messages_poll, name="messages_poll"),
    path("messages/<int:conversation_id>/send/", messaging_views.staff_messages_send, name="messages_send"),
    path("reviewers/directory/", views.reviewer_directory, name="reviewer_directory"),
    path("reviewers/directory/counts/", views.reviewer_directory_counts, name="reviewer_directory_counts"),
    path("reviewers/assignment-history/", views.reviewer_assignment_history, name="reviewer_assignment_history"),
    path("reviewers/assignment/", views.reviewer_assignment, name="reviewer_assignment"),
    path("reviewers/assignment/counts/", views.reviewer_assignment_counts, name="reviewer_assignment_counts"),
]
