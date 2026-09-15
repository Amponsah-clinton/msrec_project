from django.urls import path

from . import views

app_name = "reviewer_dashboard"

urlpatterns = [
    path("", views.dashboard_home, name="home"),
    path("my-reviews/", views.my_reviews, name="my_reviews"),
    path("my-reviews/counts/", views.my_reviews_counts, name="my_reviews_counts"),
    path("my-reviews/respond/", views.respond_to_assignment, name="respond_to_assignment"),
    path("my-reviews/<int:assignment_id>/review/", views.review_application, name="review_application"),
    path("notifications/", views.notifications, name="notifications"),
    path("profile/", views.profile_expertise, name="profile_expertise"),
    path("security/", views.security, name="security"),
]
