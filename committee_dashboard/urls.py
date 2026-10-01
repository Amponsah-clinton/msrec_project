from django.urls import path

from . import document_views as dv
from . import minutes_views as mv
from . import protocol_views as pv
from . import qa_views as qv
from . import views

app_name = "committee_dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("notifications/", views.notifications, name="notifications"),
    path("profile/", views.profile, name="profile"),
    path("profile/certificate/", views.certificate_download, name="certificate_download"),
    path("security/", views.security, name="security"),
    path("meetings/", views.meetings_upcoming, name="meetings_upcoming"),
    path("meetings/calendar/", views.meetings_calendar, name="meetings_calendar"),
    path("meetings/previous/", views.meetings_previous, name="meetings_previous"),
    path("meetings/<int:pk>/rsvp/", views.meeting_rsvp, name="meeting_rsvp"),
    path("minutes/", mv.minutes, name="minutes"),
    path("minutes/<int:pk>/status/", mv.minutes_status, name="minutes_status"),
    path("agenda/", views.agenda, name="agenda"),
    path("agenda/items/<int:item_id>/note/", views.agenda_note_save, name="agenda_note_save"),

    # Protocol review -- protocol_views.py
    path("protocols/", pv.protocols, name="protocols"),
    path("protocols/<int:pk>/", pv.protocol_detail, name="protocol_detail"),
    path("recommendations/", pv.recommendations, name="recommendations"),
    path("conflicts/", pv.conflicts, name="conflicts"),
    path("conflicts/<int:pk>/declare/", pv.conflict_declare, name="conflict_declare"),
    path("deliberations/", pv.deliberations, name="deliberations"),
    path("deliberations/<int:pk>/", pv.deliberation_thread, name="deliberation_thread"),
    path("deliberations/<int:pk>/post/", pv.deliberation_post, name="deliberation_post"),
    path("deliberations/posts/<int:post_id>/delete/", pv.deliberation_delete, name="deliberation_delete"),

    # Quality Assurance -- qa_views.py (thin wrappers around reviewer_dashboard.qa)
    path("qa/quality-check/", qv.qa_quality_check, name="qa_quality_check"),
    path("qa/pending-actions/", qv.qa_pending_actions, name="qa_pending_actions"),
    path("qa/feedback/", qv.qa_feedback, name="qa_feedback"),
    path("qa/performance/", qv.qa_performance, name="qa_performance"),

    # Governance Documents -- document_views.py (reads the admin-managed policy library)
    path("my-documents/", dv.my_documents, name="my_documents"),
    path("documents/charter/", dv.documents, {"page": "charter"}, name="doc_charter"),
    path("documents/terms-of-reference/", dv.documents, {"page": "terms"}, name="doc_terms"),
    path("documents/sops/", dv.documents, {"page": "sops"}, name="doc_sops"),
    path("documents/policies/", dv.documents, {"page": "policies"}, name="doc_policies"),
]
