from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("reference", "applicant", "application", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency")
    search_fields = ("reference", "applicant__email", "application__reference_no")
    readonly_fields = ("reference", "paystack_response", "created_at")
