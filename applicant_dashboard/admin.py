from django.contrib import admin

from .models import Application, PostApprovalSubmission


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("reference_no", "applicant", "review_type", "status", "submitted_at", "created_at")
    list_filter = ("status", "review_type")
    search_fields = ("reference_no", "applicant__email", "applicant__first_name", "applicant__last_name")
    readonly_fields = ("reference_no", "form_data", "documents", "created_at", "updated_at")


@admin.register(PostApprovalSubmission)
class PostApprovalSubmissionAdmin(admin.ModelAdmin):
    """No dedicated Secretariat dashboard page exists yet for amendments /
    continuing reviews / progress reports / adverse events / deviations /
    closure requests -- this is where they're actually actioned today:
    move `status` along and leave a `secretariat_note` for the applicant.
    """
    list_display = ("application", "type", "status", "applicant", "submitted_at")
    list_filter = ("type", "status")
    search_fields = ("application__reference_no", "applicant__email")
    readonly_fields = ("application", "applicant", "type", "form_data", "submitted_at", "updated_at")
    fields = (
        "application", "applicant", "type", "form_data",
        "status", "secretariat_note", "decided_at", "submitted_at", "updated_at",
    )
