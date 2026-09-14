from django.urls import path

from messaging import views as messaging_views

from . import views

app_name = "admin_dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("accounts/", views.accounts, name="accounts"),
    path("inquiries/", views.inquiries, name="inquiries"),
    path("applications/", views.applications, name="applications"),
    path("applications/<int:pk>/", views.application_detail, name="application_detail"),
    path("finance/", views.finance, name="finance"),
    # Broader than admin_required (secretariat included, not just
    # admin/superuser) -- messaging.views.admin_messages enforces that
    # itself via messaging.access.is_staff_side, so it's routed here
    # unwrapped rather than through views.admin_required.
    path("messages/", messaging_views.admin_messages, name="messages"),
    path("messages/<int:conversation_id>/poll/", messaging_views.admin_messages_poll, name="messages_poll"),
    path("messages/<int:conversation_id>/send/", messaging_views.admin_messages_send, name="messages_send"),
]
