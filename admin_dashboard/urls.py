from django.contrib.auth.decorators import login_required
from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "admin_dashboard"

urlpatterns = [
    path("", login_required(views.admin_required(TemplateView.as_view(template_name="dashboards/admin.html"))), name="home"),
    path("accounts/", views.accounts, name="accounts"),
]
