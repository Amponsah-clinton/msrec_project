from django.urls import path

from . import views

app_name = "secretariat_dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("applications/", views.applications, name="applications"),
    path("applications/counts/", views.applications_counts, name="applications_counts"),
    path("applications/<int:pk>/", views.application_detail, name="application_detail"),
    path("finance/", views.finance, name="finance"),
    path("reviewers/directory/", views.reviewer_directory, name="reviewer_directory"),
    path("reviewers/directory/counts/", views.reviewer_directory_counts, name="reviewer_directory_counts"),
    path("reviewers/assignment-history/", views.reviewer_assignment_history, name="reviewer_assignment_history"),
    path("reviewers/assignment/", views.reviewer_assignment, name="reviewer_assignment"),
    path("reviewers/assignment/counts/", views.reviewer_assignment_counts, name="reviewer_assignment_counts"),
]
