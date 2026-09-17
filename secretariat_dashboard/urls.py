from django.urls import path

from admin_dashboard import views as admin_dashboard_views
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
    path("meetings/schedule/", views.meetings_schedule, name="meetings_schedule"),
    path("meetings/save/", views.meeting_save, name="meeting_save"),
    path("meetings/<int:pk>/cancel/", views.meeting_cancel, name="meeting_cancel"),
    path("meetings/calendar/", views.meetings_calendar, name="meetings_calendar"),
    path("meetings/agenda/", views.meetings_agenda, name="meetings_agenda"),
    path("meetings/agenda/save/", views.agenda_item_save, name="agenda_item_save"),
    path("meetings/agenda/<int:pk>/delete/", views.agenda_item_delete, name="agenda_item_delete"),
    path("meetings/attendance/", views.meetings_attendance, name="meetings_attendance"),
    path("meetings/attendance/add/", views.attendance_add_participant, name="attendance_add_participant"),
    path("meetings/attendance/<int:pk>/mark/", views.attendance_mark, name="attendance_mark"),
    path("meetings/attendance/<int:pk>/remove/", views.attendance_remove_participant, name="attendance_remove_participant"),
    path("meetings/quorum/", views.meetings_quorum, name="meetings_quorum"),
    path("meetings/quorum/<int:pk>/update/", views.quorum_update, name="quorum_update"),
    path("meetings/minutes/", views.meetings_minutes, name="meetings_minutes"),
    path("meetings/minutes/save/", views.minutes_save, name="minutes_save"),
    path("meetings/minutes/<int:pk>/finalize/", views.minutes_finalize, name="minutes_finalize"),
    path("meetings/decisions/", views.meetings_decisions, name="meetings_decisions"),
    path("meetings/decisions/save/", views.decision_save, name="decision_save"),
    path("meetings/decisions/<int:pk>/delete/", views.decision_delete, name="decision_delete"),
    path("reports/", views.reports, name="reports"),
    path("reviewers/directory/", views.reviewer_directory, name="reviewer_directory"),
    path("reviewers/directory/counts/", views.reviewer_directory_counts, name="reviewer_directory_counts"),
    path("reviewers/assignment-history/", views.reviewer_assignment_history, name="reviewer_assignment_history"),
    path("reviewers/assignment/", views.reviewer_assignment, name="reviewer_assignment"),
    path("reviewers/assignment/counts/", views.reviewer_assignment_counts, name="reviewer_assignment_counts"),
    path("audit-logs/", views.audit_logs, name="audit_logs"),
    path("committee/members/", views.committee_members, name="committee_members"),
    path("committee/appointments/", views.committee_appointments, name="committee_appointments"),
    path("committee/terms-expiry/", views.committee_terms_expiry, name="committee_terms_expiry"),
    path("committee/training/", views.committee_training, name="committee_training"),
    path("committee/conflict-records/", views.committee_conflict_records, name="committee_conflict_records"),
    path(
        "users-access/", admin_dashboard_views.accounts,
        {"template_name": "dashboards/secretariat/accounts.html"}, name="users_access",
    ),
    path(
        "profile-security/", admin_dashboard_views.profile_security,
        {"template_name": "dashboards/secretariat/profile-security.html"}, name="profile_security",
    ),
]
