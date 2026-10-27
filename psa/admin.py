from django.contrib import admin

from .models import Payment, ServiceAgreement


@admin.register(ServiceAgreement)
class ServiceAgreementAdmin(admin.ModelAdmin):
    list_display = ("reference", "client_name", "service_title", "currency", "fee", "status", "created_at")
    list_filter = ("status", "payment_basis", "currency")
    search_fields = ("reference", "client_name", "client_email", "service_title")
    readonly_fields = ("reference", "token", "created_at", "updated_at")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """The ledger is write-once (psa.models.Payment), so entries are shown
    here but never edited or removed -- a correction is a new entry."""

    list_display = ("agreement", "amount", "paid_on", "method", "recorded_by", "recorded_at")
    list_filter = ("method", "paid_on")
    search_fields = ("agreement__reference", "agreement__client_name", "note")
    autocomplete_fields = ("agreement",)
    readonly_fields = ("recorded_at",)

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return self.readonly_fields
        return [f.name for f in self.model._meta.fields]

    def has_delete_permission(self, request, obj=None):
        return False
