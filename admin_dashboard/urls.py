from django.urls import path

from messaging import views as messaging_views

from . import views

app_name = "admin_dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/", views.accounts, name="accounts"),
    path("inquiries/", views.inquiries, name="inquiries"),
    path("applications/", views.applications, name="applications"),
    path("applications/counts/", views.applications_counts, name="applications_counts"),
    path("applications/pathway/<str:pathway>/", views.review_pathway, name="review_pathway"),
    path("applications/<int:pk>/", views.application_detail, name="application_detail"),
    path("finance/", views.finance, name="finance"),
    # Broader than admin_required (secretariat included, not just
    # admin/superuser) -- messaging.views.staff_messages enforces that
    # itself via messaging.access.is_staff_side, so it's routed here
    # unwrapped rather than through views.admin_required. Secretariat
    # gets the same view pair at its own URLs, with its own template
    # (see secretariat_dashboard/urls.py) -- one shared inbox
    # implementation, two branded dashboards.
    path("messages/", messaging_views.staff_messages, name="messages"),
    path("messages/<int:conversation_id>/poll/", messaging_views.staff_messages_poll, name="messages_poll"),
    path("messages/<int:conversation_id>/send/", messaging_views.staff_messages_send, name="messages_send"),
    path("reports/", views.reports_analytics, name="reports_analytics"),
    path("reports/export/", views.reports_analytics_export, name="reports_analytics_export"),
    path("access-security/", views.access_security, name="access_security"),
    path("profile-security/", views.profile_security, name="profile_security"),
    path("help-support/", views.help_support, name="help_support"),
    path("board-committee/", views.board_committee, name="board_committee"),
    path("committee/", views.committee_overview, name="committee_overview"),
    path("committee/appointments/", views.membership_appointments, name="membership_appointments"),
    path("committee/terms-expiry/", views.terms_expiry, name="terms_expiry"),
    path("committee/training/", views.training, name="committee_training"),
    path("committee/conflict-records/", views.conflict_records, name="conflict_records"),
    path("settings/", views.site_settings, name="settings"),
]
