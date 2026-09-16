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
    path(
        "reviewers/messages/", messaging_views.staff_reviewer_messages,
        {"template_name": "dashboards/secretariat/reviewer-messages.html"}, name="reviewer_messages",
    ),
    path(
        "reviewers/messages/<int:conversation_id>/poll/", messaging_views.staff_reviewer_messages_poll,
        name="reviewer_messages_poll",
    ),
    path(
        "reviewers/messages/<int:conversation_id>/send/", messaging_views.staff_reviewer_messages_send,
        name="reviewer_messages_send",
    ),
    path("communications/email-templates/", views.email_templates, name="email_templates"),
    path("communications/email-templates/save/", views.email_template_save, name="email_template_save"),
    path("communications/email-templates/<int:pk>/delete/", views.email_template_delete, name="email_template_delete"),
    path("communications/email-templates/<int:pk>/preview/", views.email_template_preview, name="email_template_preview"),
    path("communications/notifications/", views.notifications_page, name="notifications_page"),
    path("communications/notifications/send/", views.notification_send, name="notification_send"),
    path("communications/announcements/", views.announcements, name="announcements"),
    path("communications/announcements/save/", views.announcement_save, name="announcement_save"),
    path("communications/announcements/<int:pk>/toggle/", views.announcement_toggle, name="announcement_toggle"),
    path("communications/announcements/<int:pk>/delete/", views.announcement_delete, name="announcement_delete"),
    path("communications/reminders/", views.reminders, name="reminders"),
    path("communications/reminders/save/", views.reminder_save, name="reminder_save"),
    path("communications/reminders/<int:pk>/cancel/", views.reminder_cancel, name="reminder_cancel"),
    path("communications/reminders/<int:pk>/send-now/", views.reminder_send_now, name="reminder_send_now"),
    path("reports/", views.reports, name="reports"),
    path("reviewers/directory/", views.reviewer_directory, name="reviewer_directory"),
    path("reviewers/directory/counts/", views.reviewer_directory_counts, name="reviewer_directory_counts"),
    path("reviewers/assignment-history/", views.reviewer_assignment_history, name="reviewer_assignment_history"),
    path("reviewers/assignment/", views.reviewer_assignment, name="reviewer_assignment"),
    path("reviewers/assignment/counts/", views.reviewer_assignment_counts, name="reviewer_assignment_counts"),
    path("audit-logs/", views.audit_logs, name="audit_logs"),
]
