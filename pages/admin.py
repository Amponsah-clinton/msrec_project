from django.contrib import admin

from .models import Inquiry


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "reason", "status", "created_at", "replied_at")
    list_filter = ("status", "reason")
    search_fields = ("name", "email", "message")
    readonly_fields = ("created_at",)
