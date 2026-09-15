from django.urls import path

from . import views

app_name = "reviewer_dashboard"

urlpatterns = [
    path("", views.dashboard_home, name="home"),
    path("my-reviews/", views.my_reviews, name="my_reviews"),
    path("my-reviews/counts/", views.my_reviews_counts, name="my_reviews_counts"),
    path("notifications/", views.notifications, name="notifications"),
    path("profile/", views.profile_expertise, name="profile_expertise"),
    path("security/", views.security, name="security"),
]
