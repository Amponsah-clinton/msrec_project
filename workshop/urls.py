from django.urls import path

from . import views

app_name = "workshop"

urlpatterns = [
    path("", views.register, name="register"),
    path("pay/<int:pk>/", views.pay, name="pay"),
    path("pay/<int:pk>/verify/", views.pay_verify, name="pay_verify"),
    path("thanks/", views.thanks, name="thanks"),
]
