from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from applicant_dashboard.models import Application

from . import fees, services
from .models import Payment


@login_required
def pay(request, pk):
    application = get_object_or_404(
        Application, pk=pk, applicant=request.user, status=Application.Status.DRAFT
    )
    if not fees.requires_payment(application.review_type):
        # Nothing to pay for (fee-exempt pathway, or this application never
        # went through the payment gate) -- there's no checkout to show.
        return redirect("applicant_dashboard:application_form")

    payment = services.current_pending_payment(application)
    if payment is None:
        payment = services.start_checkout(application, application.review_type)

    return render(request, "dashboards/applicant/application-pay.html", {
        "application": application,
        "payment": payment,
        "paystack_public_key": settings.PAYSTACK_PUBLIC_KEY,
        "verify_url": reverse("applicant_dashboard:application_pay_verify", kwargs={"pk": application.pk}),
    })


@login_required
@require_POST
def verify(request, pk):
    application = get_object_or_404(Application, pk=pk, applicant=request.user)
    reference = request.POST.get("reference", "").strip()
    payment = get_object_or_404(
        Payment, application=application, applicant=request.user, reference=reference
    )

    # Lazy import: applicant_dashboard.views already imports payments.fees
    # at module level, so importing payments.views -> applicant_dashboard.views
    # up front here would be circular. Finalizing a submission is squarely
    # applicant_dashboard's concern (assigns the reference number, notifies
    # the Secretariat) -- payments only triggers it once Paystack has
    # actually confirmed the charge.
    from applicant_dashboard.views import finalize_submission

    ok, reason = services.verify_and_finalize(
        payment, on_success=lambda app: finalize_submission(app, request)
    )

    if ok:
        return JsonResponse({
            "ok": True,
            "redirect": reverse("applicant_dashboard:application_submitted"),
        })

    messages.error(request, reason)
    return JsonResponse({"ok": False, "error": reason}, status=400)
