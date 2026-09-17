from django.contrib import admin

<<<<<<< HEAD
from .models import Application, PostApprovalSubmission
=======
from .models import Application, TeamMember
>>>>>>> 9e82dbf56602c998c6309bd331a8d3acee436cea


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("reference_no", "applicant", "review_type", "status", "submitted_at", "created_at")
    list_filter = ("status", "review_type")
    search_fields = ("reference_no", "applicant__email", "applicant__first_name", "applicant__last_name")
    readonly_fields = ("reference_no", "form_data", "documents", "created_at", "updated_at")


<<<<<<< HEAD
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
=======
@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "applicant", "role", "status", "invited_at", "accepted_at")
    list_filter = ("status", "role")
    search_fields = ("full_name", "email", "applicant__email")
    readonly_fields = ("invite_token", "created_at", "updated_at")
>>>>>>> 9e82dbf56602c998c6309bd331a8d3acee436cea
