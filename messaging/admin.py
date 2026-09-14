from django.contrib import admin

from .models import Conversation, ConversationRead, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("sender", "body", "created_at")
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("applicant", "created_at")
    search_fields = ("applicant__email", "applicant__first_name", "applicant__last_name")
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "sender", "created_at")
    list_filter = ("created_at",)
    search_fields = ("body", "sender__email")


admin.site.register(ConversationRead)
