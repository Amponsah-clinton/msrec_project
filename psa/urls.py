from django.urls import path

from . import views

app_name = "psa"

urlpatterns = [
    path("<str:token>/", views.client, name="client"),
]
