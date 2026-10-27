from django.urls import path

from . import views

app_name = "psa"

urlpatterns = [
    path("<str:token>/", views.client, name="client"),
    path("<str:token>/request-changes/", views.client_request_changes, name="request_changes"),
]
