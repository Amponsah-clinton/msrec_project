from django.urls import path

from . import views

app_name = "psa_admin"

# Names carry a psa_ prefix: the Secretariat sidebar highlights entries by
# bare URL name, and "list" is already the Workshops page's.
urlpatterns = [
    path("", views.psa_list, name="psa_list"),
    path("new/", views.psa_new, name="psa_new"),
    path("export/", views.psa_export, name="psa_export"),
    path("<int:pk>/", views.psa_detail, name="psa_detail"),
    path("<int:pk>/edit/", views.psa_edit, name="psa_edit"),
    path("<int:pk>/send/", views.psa_send, name="psa_send"),
    path("<int:pk>/resend/", views.psa_resend, name="psa_resend"),
    path("<int:pk>/cancel/", views.psa_cancel, name="psa_cancel"),
    path("<int:pk>/delete/", views.psa_delete, name="psa_delete"),
]
