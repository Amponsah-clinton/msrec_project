from django.urls import path
from django.views.generic import TemplateView

app_name = "applicant_dashboard"

urlpatterns = [
    path("", TemplateView.as_view(template_name="dashboards/applicant.html"), name="home"),
]
