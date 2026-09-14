from django.urls import path

from . import views

app_name = "secretariat_dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("applications/", views.applications, name="applications"),
    path("applications/<int:pk>/", views.application_detail, name="application_detail"),
    path("finance/", views.finance, name="finance"),
]
