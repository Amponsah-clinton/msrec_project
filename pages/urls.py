from django.urls import path
from django.views.generic import TemplateView

from accounts import views as account_views

from . import file_proxy, views

app_name = "pages"

urlpatterns = [
    path("", views.index, name="index"),
    # Every Storage module's public_url()/create_signed_url() points
    # here instead of a raw Supabase URL -- see pages/file_proxy.py.
    # Root-mounted (not under any one dashboard's prefix) since every
    # app's downloads/images go through this one endpoint.
    path("files/<str:token>/", file_proxy.serve, name="file_proxy"),
    path("about/", TemplateView.as_view(template_name="pages/about.html"), name="about"),
    path("applicants/", TemplateView.as_view(template_name="pages/applicants.html"), name="applicants"),
    path("ethics-review/", TemplateView.as_view(template_name="pages/ethics_review.html"), name="ethics_review"),
    path("resources/", views.resources, name="resources"),
    path("governance/", TemplateView.as_view(template_name="pages/governance.html"), name="governance"),
    path("board-committee/", views.board_committee, name="board_committee"),
    path("verify/", TemplateView.as_view(template_name="pages/verify.html"), name="verify"),
    path("terms-of-use/", TemplateView.as_view(template_name="pages/terms_of_use.html"), name="terms"),
    path("privacy-notice/", TemplateView.as_view(template_name="pages/privacy_notice.html"), name="privacy"),
    path("contact/", views.contact, name="contact"),
    path("apply/", TemplateView.as_view(template_name="pages/apply.html"), name="apply"),
    path("fees/", views.fees_schedule, name="fees"),
    path("login/", account_views.login_view, name="login"),
    path("signup/", account_views.signup, name="signup"),
    path("logout/", account_views.logout_view, name="logout"),
    path("forgot-password/", account_views.forgot_password, name="forgot_password"),
    path("reset-password/", account_views.reset_password, name="reset_password"),
    path("account-status/", account_views.role_status, name="role_status"),
]
