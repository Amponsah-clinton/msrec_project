from django.contrib import admin

from .models import ServiceAgreement


@admin.register(ServiceAgreement)
class ServiceAgreementAdmin(admin.ModelAdmin):
    list_display = ("reference", "client_name", "service_title", "currency", "fee", "status", "created_at")
    list_filter = ("status", "payment_basis", "currency")
    search_fields = ("reference", "client_name", "client_email", "service_title")
    readonly_fields = ("reference", "token", "created_at", "updated_at")
