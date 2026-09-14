from django.contrib import admin

from .models import Notification, NotificationRead


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("audience", "icon", "message", "created_at")
    list_filter = ("audience", "icon")
    search_fields = ("message",)


admin.site.register(NotificationRead)
