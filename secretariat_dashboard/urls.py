from django.urls import path
from django.views.generic import TemplateView

app_name = "secretariat_dashboard"

urlpatterns = [
    path("", TemplateView.as_view(template_name="dashboards/secretariat.html"), name="home"),
]
