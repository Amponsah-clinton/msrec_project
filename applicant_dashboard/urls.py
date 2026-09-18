from django.contrib.auth.decorators import login_required
from django.urls import path
from django.views.generic import TemplateView

from messaging import views as messaging_views
from payments import views as payment_views

from . import views

app_name = "applicant_dashboard"

_urlpatterns = [
    path("", views.home, name="home"),
    path(
        "applications/new/",
        TemplateView.as_view(template_name="dashboards/applicant/application-new.html"),
        name="application_new",
    ),
    path(
        "applications/new/form/",
        views.application_form,
        name="application_form",
    ),
    path(
        "applications/drafts/",
        views.application_drafts,
        name="application_drafts",
    ),
    path(
        "applications/drafts/<int:pk>/delete/",
        views.delete_draft,
        name="application_draft_delete",
    ),
    path(
        "applications/autosave/",
        views.autosave_application,
        name="application_autosave",
    ),
    path(
        "applications/new/pay/<int:pk>/",
        payment_views.pay,
        name="application_pay",
    ),
    path(
        "applications/new/pay/<int:pk>/verify/",
        payment_views.verify,
        name="application_pay_verify",
    ),
    path(
        "applications/nav-counts/",
        views.nav_counts,
        name="application_nav_counts",
    ),
    path(
        "applications/submitted/",
        views.application_submitted,
        name="application_submitted",
    ),
    path(
        "applications/under-review/",
        views.application_under_review,
        name="application_under_review",
    ),
    path(
        "applications/revisions/",
        views.application_revisions,
        name="application_revisions",
    ),
    path(
        "applications/approved/",
        views.application_approved,
        name="application_approved",
    ),
    path(
        "applications/not-approved/",
        views.application_not_approved,
        name="application_not_approved",
    ),
    path(
        "applications/<int:pk>/",
        views.application_detail,
        name="application_detail",
    ),
    path(
        "post-approval/amendments/",
        views.postapproval_amendments,
        name="postapproval_amendments",
    ),
    path(
        "post-approval/continuing-reviews/",
        views.postapproval_continuing_reviews,
        name="postapproval_continuing_reviews",
    ),
    path(
        "post-approval/progress-reports/",
        views.postapproval_progress_reports,
        name="postapproval_progress_reports",
    ),
    path(
        "post-approval/adverse-events/",
        views.postapproval_adverse_events,
        name="postapproval_adverse_events",
    ),
    path(
        "post-approval/deviations/",
        views.postapproval_deviations,
        name="postapproval_deviations",
    ),
    path(
        "post-approval/closure/",
        views.postapproval_closure,
        name="postapproval_closure",
    ),
    path(
        "post-approval/<str:ptype>/new/",
        views.postapproval_new,
        name="postapproval_new",
    ),
    path(
        "documents/submitted/",
        views.documents_submitted,
        name="documents_submitted",
    ),
    path(
        "documents/decision-letters/",
        views.documents_decision_letters,
        name="documents_decision_letters",
    ),
    path(
        "documents/approval-letters/",
        views.documents_approval_letters,
        name="documents_approval_letters",
    ),
    path(
        "documents/certificates-receipts/",
        views.documents_certificates_receipts,
        name="documents_certificates_receipts",
    ),
    path(
        "applications/<int:pk>/letter/<str:kind>/",
        views.application_letter,
        name="application_letter",
    ),
    path("payments/fees/", views.payments_fees, name="payments_fees"),
    path(
        "payments/make/",
        views.payments_make,
        name="payments_make",
    ),
    path(
        "payments/history/",
        views.payments_history,
        name="payments_history",
    ),
    path(
        "payments/receipts/",
        views.payments_receipts,
        name="payments_receipts",
    ),
    path(
        "payments/receipts/<int:pk>/",
        views.payment_receipt,
        name="payment_receipt",
    ),
    path(
        "messages/",
        messaging_views.applicant_messages,
        name="messages",
    ),
    path(
        "messages/poll/",
        messaging_views.applicant_messages_poll,
        name="messages_poll",
    ),
    path(
        "messages/send/",
        messaging_views.applicant_messages_send,
        name="messages_send",
    ),
    path(
        "notifications/",
        views.notifications_page,
        name="notifications",
    ),
    path(
        "notifications/mark-read/",
        views.notifications_mark_read,
        name="notifications_mark_read",
    ),
    path(
        "notifications/feed/",
        views.notifications_feed,
        name="notifications_feed",
    ),
    path(
        "research-team/",
        views.research_team,
        name="research_team",
    ),
    path(
        "institution/",
        views.institution,
        name="institution",
    ),
    path(
        "profile-security/",
        views.profile_security,
        name="profile_security",
    ),
    path(
        "help/",
        TemplateView.as_view(template_name="dashboards/applicant/help-support.html"),
        name="help_support",
    ),
]

# Every applicant-dashboard page requires a signed-in account -- wrap each
# resolved view here rather than repeat login_required(...) on every path()
# above. (URLPattern.callback is set post-construction, so mutating it here
# is equivalent to having wrapped each TemplateView.as_view(...) by hand.)
urlpatterns = _urlpatterns
for _pattern in urlpatterns:
    _pattern.callback = login_required(_pattern.callback)

# Deliberately outside the login_required loop above: the link in a team
# invite email is opened by the invitee, who has no MSREC account to log
# into -- see views.team_invite_accept().
urlpatterns.append(
    path(
        "research-team/invite/<str:token>/accept/",
        views.team_invite_accept,
        name="team_invite_accept",
    )
)
