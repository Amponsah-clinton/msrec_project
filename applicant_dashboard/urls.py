from django.urls import path
from django.views.generic import TemplateView

app_name = "applicant_dashboard"

urlpatterns = [
    path("", TemplateView.as_view(template_name="dashboards/applicant.html"), name="home"),
    path(
        "applications/new/",
        TemplateView.as_view(template_name="dashboards/applicant/application-new.html"),
        name="application_new",
    ),
    path(
        "applications/drafts/",
        TemplateView.as_view(template_name="dashboards/applicant/application-drafts.html"),
        name="application_drafts",
    ),
    path(
        "applications/submitted/",
        TemplateView.as_view(template_name="dashboards/applicant/application-submitted.html"),
        name="application_submitted",
    ),
    path(
        "applications/under-review/",
        TemplateView.as_view(template_name="dashboards/applicant/application-under-review.html"),
        name="application_under_review",
    ),
    path(
        "applications/revisions/",
        TemplateView.as_view(template_name="dashboards/applicant/application-revisions.html"),
        name="application_revisions",
    ),
    path(
        "applications/approved/",
        TemplateView.as_view(template_name="dashboards/applicant/application-approved.html"),
        name="application_approved",
    ),
    path(
        "applications/not-approved/",
        TemplateView.as_view(template_name="dashboards/applicant/application-not-approved.html"),
        name="application_not_approved",
    ),
    path(
        "post-approval/amendments/",
        TemplateView.as_view(template_name="dashboards/applicant/postapproval-amendments.html"),
        name="postapproval_amendments",
    ),
    path(
        "post-approval/continuing-reviews/",
        TemplateView.as_view(template_name="dashboards/applicant/postapproval-continuing-reviews.html"),
        name="postapproval_continuing_reviews",
    ),
    path(
        "post-approval/progress-reports/",
        TemplateView.as_view(template_name="dashboards/applicant/postapproval-progress-reports.html"),
        name="postapproval_progress_reports",
    ),
    path(
        "post-approval/adverse-events/",
        TemplateView.as_view(template_name="dashboards/applicant/postapproval-adverse-events.html"),
        name="postapproval_adverse_events",
    ),
    path(
        "post-approval/deviations/",
        TemplateView.as_view(template_name="dashboards/applicant/postapproval-deviations.html"),
        name="postapproval_deviations",
    ),
    path(
        "post-approval/closure/",
        TemplateView.as_view(template_name="dashboards/applicant/postapproval-closure.html"),
        name="postapproval_closure",
    ),
]
