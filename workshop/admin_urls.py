from django.urls import path

from . import admin_views

app_name = "workshop_admin"

urlpatterns = [
    path("", admin_views.workshop_list, name="list"),
    path("<int:pk>/", admin_views.workshop_manage, name="manage"),
    path("<int:pk>/certificate-preview/", admin_views.cert_preview, name="cert_preview"),
]
