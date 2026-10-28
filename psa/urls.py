from django.urls import path

from . import views

app_name = "psa"

urlpatterns = [
    # Payment links come before the agreement link: both live under
    # /psa/, and "pay" would otherwise be read as an agreement token.
    path("pay/<str:token>/", views.pay, name="pay"),
    path("pay/<str:token>/verify/", views.pay_verify, name="pay_verify"),
    path("pay/<str:token>/receipt/", views.pay_receipt, name="receipt"),
    path("<str:token>/", views.client, name="client"),
    path("<str:token>/pdf/", views.client_pdf, name="client_pdf"),
    path("<str:token>/request-changes/", views.client_request_changes, name="request_changes"),
]
