import hashlib
import hmac
import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from applicant_dashboard.models import Application
from pages.models import SiteSettings

from . import fees, paystack, services
from .models import Payment

logger = logging.getLogger(__name__)


@login_required
def pay(request, pk):
    application = get_object_or_404(
        Application, pk=pk, applicant=request.user, status=Application.Status.DRAFT
    )
    if not fees.requires_payment_for_application(application.review_type, application.applicant_category):
        # Nothing to pay for (fee-exempt pathway/category, or this
        # application never went through the payment gate) -- there's no
        # checkout to show.
        return redirect("applicant_dashboard:application_form")

    payment = services.current_pending_payment(application)
    if payment is None:
        payment = services.start_checkout(application, application.review_type, application.applicant_category)

    return render(request, "dashboards/applicant/application-pay.html", {
        "application": application,
        "payment": payment,
        "paystack_public_key": SiteSettings.get_solo().effective_paystack_public_key,
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


@csrf_exempt
@require_POST
def paystack_webhook(request):
    """Server-to-server reconciliation from Paystack.

    The in-page flow (application-pay.html -> verify above) depends on the
    applicant's browser staying open long enough to POST the reference back.
    If they close the tab, lose connection, or the popup callback never
    fires after a *successful* charge, that verify never runs -- leaving a
    real, paid charge stuck as a PENDING Payment with the application still
    a draft ("money taken but nothing happened").

    Paystack also calls this endpoint directly whenever a charge succeeds,
    independently of any browser, so the Payment is reconciled and the
    application submitted no matter what the applicant's browser did. The
    request is authenticated by Paystack's HMAC-SHA512 signature over the
    raw body, keyed with our secret key -- never by a login session.

    Configure the URL in the Paystack dashboard (Settings -> API Keys &
    Webhooks):  https://<your-domain>/payments/webhook/paystack/
    """
    signature = request.headers.get("X-Paystack-Signature", "")
    try:
        secret = paystack.secret_key() or ""
    except Exception:
        logger.exception("Paystack webhook: could not read secret key")
        return HttpResponse(status=500)

    expected = hmac.new(secret.encode(), request.body, hashlib.sha512).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected):
        # Not a genuine Paystack call (or wrong key) -- reject without
        # touching anything.
        return HttpResponse(status=401)

    try:
        event = json.loads(request.body.decode())
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)

    if event.get("event") == "charge.success":
        reference = (event.get("data") or {}).get("reference", "")
        payment = Payment.objects.filter(reference=reference).select_related("application").first()
        if payment is not None and payment.status != Payment.Status.SUCCESS:
            # verify_and_finalize re-checks with Paystack's verify API and is
            # race-safe against the browser verify firing at the same time.
            from applicant_dashboard.views import finalize_submission
            try:
                services.verify_and_finalize(
                    payment, on_success=lambda app: finalize_submission(app, None)
                )
            except Exception:
                logger.exception("Paystack webhook: finalize failed for %s", reference)
        elif payment is None:
            # Not an application fee -- it may be a workshop certificate fee.
            _reconcile_workshop_charge(reference)

    # Always acknowledge, so Paystack doesn't retry over an issue on our side
    # (a genuine unmatched reference is simply nothing for us to do).
    return HttpResponse(status=200)


def _reconcile_workshop_charge(reference):
    """Mark a workshop certificate-fee registration paid when Paystack
    confirms the charge server-to-server (mirrors workshop.views.pay_verify
    so the fee is captured even if the registrant's browser dropped out)."""
    from django.utils import timezone

    from workshop.models import WorkshopRegistration

    reg = WorkshopRegistration.objects.filter(payment_reference=reference).first()
    if reg is None or reg.payment_status == WorkshopRegistration.PaymentStatus.SUCCESS:
        return
    try:
        data = paystack.verify_transaction(reference)
    except paystack.PaystackError:
        logger.exception("Workshop webhook verify failed for %s", reference)
        return
    amount_ok = int(data.get("amount") or 0) == reg.amount_subunit
    currency_ok = (data.get("currency") or "").upper() == reg.currency.upper()
    if data.get("status") == "success" and amount_ok and currency_ok:
        reg.payment_status = WorkshopRegistration.PaymentStatus.SUCCESS
        reg.paid_at = timezone.now()
        reg.paystack_response = data
        reg.ensure_certificate_ref()  # traceable id, verifiable at /verify/
        reg.save(update_fields=["payment_status", "paid_at", "paystack_response", "certificate_ref"])
        # Payment confirmed server-side -- send the "registration received"
        # email + SMS now (covers the case where the browser dropped out
        # before the in-page verify ran).
        try:
            from workshop.views import _notify_registration_success
            _notify_registration_success(reg, reg.workshop)
        except Exception:
            logger.exception("Workshop webhook notify failed for %s", reference)
