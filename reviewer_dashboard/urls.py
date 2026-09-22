from django.urls import path

from . import views

app_name = "reviewer_dashboard"

urlpatterns = [
    path("", views.dashboard_home, name="home"),
    path("my-reviews/", views.my_reviews, name="my_reviews"),
    path("my-reviews/counts/", views.my_reviews_counts, name="my_reviews_counts"),
    path("my-reviews/respond/", views.respond_to_assignment, name="respond_to_assignment"),
    path("my-reviews/<int:assignment_id>/review/", views.review_application, name="review_application"),
    path("my-reviews/<int:assignment_id>/review/pdf/", views.review_application_pdf, name="review_application_pdf"),
    path("my-reviews/<int:assignment_id>/application-pdf/", views.review_application_info_pdf, name="review_application_info_pdf"),
    path("my-reviews/<int:assignment_id>/certificate/", views.certificate_download, name="certificate_download"),
    path("coi/pending/", views.coi_pending, name="coi_pending"),
    path("coi/previous/", views.coi_previous, name="coi_previous"),
    path("committee-meetings/", views.committee_meetings, name="committee_meetings"),
    path("committee-meetings/documents/", views.meeting_documents, name="meeting_documents"),
    path("policies/sops/", views.policy_sops, name="policy_sops"),
    path("policies/guidance/", views.policy_guidance, name="policy_guidance"),
    path("policies/ethics/", views.policy_ethics, name="policy_ethics"),
    path("notifications/", views.notifications, name="notifications"),
    path("profile/", views.profile_expertise, name="profile_expertise"),
    path("security/", views.security, name="security"),
    path("security/sessions/", views.all_sessions, name="all_sessions"),
]
