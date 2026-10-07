from django.urls import path

from . import views

app_name = "workshop"

urlpatterns = [
    path("", views.workshop_list, name="list"),
    # Fixed paths before the <slug> catch-all.
    path("pay/<int:pk>/", views.pay, name="pay"),
    path("pay/<int:pk>/verify/", views.pay_verify, name="pay_verify"),
    path("thanks/", views.thanks, name="thanks"),
    path("documents/<str:token>/", views.documents, name="documents"),
    path("documents/<str:token>/<str:kind>/", views.download_document, name="download_document"),
    path("<slug:slug>/", views.register, name="register"),
    path("<slug:slug>/certificate-sample/", views.cert_sample, name="cert_sample"),
]
