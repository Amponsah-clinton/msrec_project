from django.urls import path

from . import admin_views

app_name = "workshop_admin"

urlpatterns = [
    path("", admin_views.admin_workshop, name="home"),
    path("certificate-preview/", admin_views.admin_cert_preview, name="cert_preview"),
]
