from django.urls import path

from . import views

app_name = "institution_dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("applications/", views.applications, name="applications"),
    path("committee-members/", views.committee_members, name="committee_members"),
    path("reviewers/", views.reviewers, name="reviewers"),
    path("other-institutions/", views.other_institutions, name="other_institutions"),
    # Public activation link from the invite email (no login_required -- the
    # account has no usable password until this page sets one).
    path("activate/<str:token>/", views.activate, name="activate"),
]
