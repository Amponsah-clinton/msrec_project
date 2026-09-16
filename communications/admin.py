from django.contrib import admin

from .models import Announcement, EmailTemplate, Reminder


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "is_active", "updated_at")
    list_filter = ("category", "is_active")
    search_fields = ("name", "subject")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "audience", "is_pinned", "is_active", "created_at")
    list_filter = ("audience", "is_active", "is_pinned")
    search_fields = ("title", "body")


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ("title", "audience", "remind_at", "status")
    list_filter = ("audience", "status")
    search_fields = ("title", "message")
