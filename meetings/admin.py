from django.contrib import admin

from .models import AgendaItem, Decision, Meeting, MeetingMinutes, MeetingParticipant


@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "meeting_type", "scheduled_at", "status", "quorum_required")
    list_filter = ("status", "meeting_type", "mode")
    search_fields = ("title", "description")


admin.site.register(MeetingParticipant)
admin.site.register(AgendaItem)
admin.site.register(MeetingMinutes)
admin.site.register(Decision)
