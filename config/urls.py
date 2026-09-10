"""URL configuration for the MSREC Django project."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("pages.urls")),
    path("dashboard/reviewer/", include("reviewer_dashboard.urls")),
    path("dashboard/applicant/", include("applicant_dashboard.urls")),
    path("dashboard/committee/", include("committee_dashboard.urls")),
    path("dashboard/chair/", include("chair_dashboard.urls")),
    path("dashboard/secretariat/", include("secretariat_dashboard.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
