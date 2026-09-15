from django.urls import path
from django.views.generic import TemplateView

from accounts import views as account_views

from . import views

app_name = "pages"

urlpatterns = [
    path("", TemplateView.as_view(template_name="pages/index.html"), name="index"),
    path("about/", TemplateView.as_view(template_name="pages/about.html"), name="about"),
    path("applicants/", TemplateView.as_view(template_name="pages/applicants.html"), name="applicants"),
    path("ethics-review/", TemplateView.as_view(template_name="pages/ethics_review.html"), name="ethics_review"),
    path("resources/", TemplateView.as_view(template_name="pages/resources.html"), name="resources"),
    path("governance/", TemplateView.as_view(template_name="pages/governance.html"), name="governance"),
    path("board-committee/", TemplateView.as_view(template_name="pages/board_committee.html"), name="board_committee"),
    path("verify/", TemplateView.as_view(template_name="pages/verify.html"), name="verify"),
    path("contact/", views.contact, name="contact"),
    path("apply/", TemplateView.as_view(template_name="pages/apply.html"), name="apply"),
    path("login/", account_views.login_view, name="login"),
    path("signup/", account_views.signup, name="signup"),
    path("logout/", account_views.logout_view, name="logout"),
    path("account-status/", account_views.role_status, name="role_status"),
]
