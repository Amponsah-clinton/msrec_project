from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import RoleApprovalLog, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["-date_joined"]
    list_display = ["email", "full_name", "role", "reviewer_status", "committee_status", "is_active", "date_joined"]
    list_filter = ["role", "reviewer_status", "committee_status", "is_active", "is_staff"]
    search_fields = ["email", "first_name", "last_name", "institution"]
    readonly_fields = ["date_joined", "last_login"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", (
            {"fields": (
                "title", "first_name", "middle_name", "last_name", "phone",
                "country_residence", "highest_qualification",
            )}
        )),
        ("Institution", ({"fields": (
            "no_institution", "institution", "department", "position",
            "institution_country", "institution_address", "profile_url",
        )})),
        ("Signup documents", ({"fields": ("profile_photo_path",)})),
        ("Roles", ({"fields": (
            "role", "wants_reviewer", "reviewer_status", "reviewer_profile",
            "wants_committee", "committee_status", "committee_profile", "applicant_profile",
        )})),
        ("Permissions", ({"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")})),
        ("Dates", ({"fields": ("last_login", "date_joined")})),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "first_name", "last_name", "password1", "password2")}),
    )


@admin.register(RoleApprovalLog)
class RoleApprovalLogAdmin(admin.ModelAdmin):
    list_display = ["user", "role", "action", "acted_by", "created_at"]
    list_filter = ["role", "action"]
    readonly_fields = ["created_at"]
