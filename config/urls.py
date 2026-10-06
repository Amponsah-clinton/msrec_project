"""URL configuration for the MSREC Django project."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from payments import views as payment_views

urlpatterns = [
    path("admin/", admin.site.urls),
    # Paystack server-to-server webhook (no login; HMAC-signed). Kept at the
    # project root so the URL configured in the Paystack dashboard is stable
    # and independent of the applicant dashboard's routes.
    path("payments/webhook/paystack/", payment_views.paystack_webhook, name="paystack_webhook"),
    path("", include("pages.urls")),
    path("dashboard/reviewer/", include("reviewer_dashboard.urls")),
    path("dashboard/applicant/", include("applicant_dashboard.urls")),
    path("dashboard/committee/", include("committee_dashboard.urls")),
    path("dashboard/chair/", include("chair_dashboard.urls")),
    path("dashboard/secretariat/", include("secretariat_dashboard.urls")),
    path("dashboard/institution/", include("institution_dashboard.urls")),
    path("hall-of-fame/", include("hall_of_fame.urls")),
    path("workshop/", include("workshop.urls")),
    path("admins/workshop/", include("workshop.admin_urls")),
    path("admins/", include("admin_dashboard.urls")),
    path("notifications/", include("notifications.urls")),
    path("assistant/", include("assistant.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
