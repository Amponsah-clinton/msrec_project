from django.contrib import admin

from .models import InstitutionSecretary


@admin.register(InstitutionSecretary)
class InstitutionSecretaryAdmin(admin.ModelAdmin):
    list_display = ("user", "is_activated", "invited_at", "activated_at", "created_by")
    search_fields = ("user__email", "user__first_name", "user__last_name", "user__institution")
    raw_id_fields = ("user", "created_by")
