from django.urls import path
from django.views.generic import TemplateView

app_name = "chair_dashboard"

urlpatterns = [
    path("", TemplateView.as_view(template_name="dashboards/chair.html"), name="home"),
]
