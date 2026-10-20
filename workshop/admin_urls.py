from django.urls import path

from . import admin_views

app_name = "workshop_admin"

urlpatterns = [
    path("", admin_views.workshop_list, name="list"),
    path("contacts/", admin_views.contacts, name="contacts"),
    path("contacts/export/", admin_views.contacts_export, name="contacts_export"),
    path("<int:pk>/", admin_views.workshop_manage, name="manage"),
    path("<int:pk>/certificate-preview/", admin_views.cert_preview, name="cert_preview"),
]
