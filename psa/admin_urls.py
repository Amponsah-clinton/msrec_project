from django.urls import path

from . import views

app_name = "psa_admin"

# Names carry a psa_ prefix: the Secretariat sidebar highlights entries by
# bare URL name, and "list" is already the Workshops page's.
urlpatterns = [
    path("", views.psa_list, name="psa_list"),
    path("new/", views.psa_new, name="psa_new"),
    path("export/", views.psa_export, name="psa_export"),
    path("export/signed-pdfs/", views.psa_pdf_zip, name="psa_pdf_zip"),
    path("letterhead/", views.psa_letterhead, name="psa_letterhead"),
    path("letterhead/preview/", views.psa_letterhead_preview, name="psa_letterhead_preview"),
    path("letterhead/<str:kind>/image/", views.psa_letterhead_image, name="psa_letterhead_image"),
    path("<int:pk>/", views.psa_detail, name="psa_detail"),
    path("<int:pk>/edit/", views.psa_edit, name="psa_edit"),
    path("<int:pk>/pdf/", views.psa_pdf, name="psa_pdf"),
    path("<int:pk>/send/", views.psa_send, name="psa_send"),
    path("<int:pk>/resend/", views.psa_resend, name="psa_resend"),
    path("<int:pk>/payments/add/", views.psa_payment_add, name="psa_payment_add"),
    path("<int:pk>/payments/<int:payment_pk>/receipt/", views.psa_receipt, name="psa_receipt"),
    path("<int:pk>/payment-link/", views.psa_payment_link, name="psa_payment_link"),
    path("<int:pk>/payment-link/<int:req_pk>/resend/", views.psa_payment_link_resend,
         name="psa_payment_link_resend"),
    path("<int:pk>/payment-link/<int:req_pk>/cancel/", views.psa_payment_link_cancel,
         name="psa_payment_link_cancel"),
    path("<int:pk>/cancel/", views.psa_cancel, name="psa_cancel"),
    path("<int:pk>/delete/", views.psa_delete, name="psa_delete"),
]
