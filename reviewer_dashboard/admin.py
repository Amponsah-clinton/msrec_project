from django.contrib import admin

from .models import ReviewAssignment


@admin.register(ReviewAssignment)
class ReviewAssignmentAdmin(admin.ModelAdmin):
    # No in-app "Assign Reviewer" UI exists yet (still a stub link in
    # secretariat_dashboard's sidebar) -- this is the only way to create
    # assignments for now, so the Reviewer dashboard's My Reviews page
    # has something real to show.
    list_display = ["reviewer", "application", "status", "due_date", "coi_declared", "assigned_at", "assigned_by"]
    list_filter = ["status", "coi_declared"]
    search_fields = ["reviewer__email", "application__title", "application__reference_no"]
    autocomplete_fields = ["application", "reviewer", "assigned_by"]
