from django.urls import path

from . import views

app_name = "hall_of_fame"

urlpatterns = [
    # Member dashboard
    path("dashboard/", views.dashboard, name="dashboard"),
    path("nominate/", views.nominate, name="nominate"),
    path("resubmit/<int:pk>/", views.resubmit, name="resubmit"),
    path("certificate/", views.certificate_download, name="certificate"),
    path("letter/", views.letter_download, name="letter"),

    # Admin / Secretary review
    path("admin/", views.admin_nominations, name="admin_nominations"),
    path("admin/add/", views.admin_add_member, name="admin_add_member"),
    path("admin/<int:pk>/", views.admin_nomination_detail, name="admin_detail"),
    path("admin/<int:pk>/action/", views.admin_action, name="admin_action"),

    # Public
    path("", views.hall_of_fame_page, name="directory"),
    path("<int:pk>/", views.public_profile, name="profile"),
]
