from django.contrib import admin

from .models import Application


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("reference_no", "applicant", "review_type", "status", "submitted_at", "created_at")
    list_filter = ("status", "review_type")
    search_fields = ("reference_no", "applicant__email", "applicant__first_name", "applicant__last_name")
    readonly_fields = ("reference_no", "form_data", "documents", "created_at", "updated_at")
