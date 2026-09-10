from django.urls import path
from django.views.generic import TemplateView

app_name = "committee_dashboard"

urlpatterns = [
    path("", TemplateView.as_view(template_name="dashboards/committee.html"), name="home"),
]
