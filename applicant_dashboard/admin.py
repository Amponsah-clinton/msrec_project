from django.contrib import admin

from .models import Application, TeamMember


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("reference_no", "applicant", "review_type", "status", "submitted_at", "created_at")
    list_filter = ("status", "review_type")
    search_fields = ("reference_no", "applicant__email", "applicant__first_name", "applicant__last_name")
    readonly_fields = ("reference_no", "form_data", "documents", "created_at", "updated_at")


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "applicant", "role", "status", "invited_at", "accepted_at")
    list_filter = ("status", "role")
    search_fields = ("full_name", "email", "applicant__email")
    readonly_fields = ("invite_token", "created_at", "updated_at")
