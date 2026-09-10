from django.urls import path
from django.views.generic import TemplateView

app_name = "reviewer_dashboard"

urlpatterns = [
    path("", TemplateView.as_view(template_name="dashboards/reviewer.html"), name="home"),
]
