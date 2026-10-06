"""Public /workshop pages: the registration form, and -- for anyone who
asks for a certificate -- the Paystack checkout that collects the fee.
"""
import logging
import uuid

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from pages.models import Institution, SiteSettings

from .models import WorkshopRegistration, WorkshopSettings

logger = logging.getLogger(__name__)

INSTITUTION_OTHER = "__other__"


def _active_institutions():
    return list(Institution.objects.filter(is_active=True))


def register(request):
    ws = WorkshopSettings.get_solo()

    if request.method == "POST":
        if not ws.registration_open:
            messages.error(request, "Workshop registration is closed right now.")
            return redirect("workshop:register")

        name = request.POST.get("name", "").strip()
        institution = request.POST.get("institution", "").strip()
        if institution == INSTITUTION_OTHER:
            institution = request.POST.get("institution_other", "").strip()
        email = request.POST.get("email", "").strip().lower()
        phone = request.POST.get("phone", "").strip()
        wants_certificate = request.POST.get("wants_certificate") == "yes"
        comments = request.POST.get("comments", "").strip()

        errors = []
        if not name:
            errors.append("Your name is required.")
        if not institution:
            errors.append("Please choose your institution.")
        if not email:
            errors.append("Your email is required.")
        if "wants_certificate" not in request.POST:
            errors.append("Please tell us whether you want a certificate.")
        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "workshop/register.html", _register_context(ws, {
                "name": name, "institution": institution, "email": email,
                "phone": phone, "comments": comments,
            }), status=400)

        reg = WorkshopRegistration.objects.create(
            name=name[:200], institution=institution[:200], email=email,
            phone=phone[:40], wants_certificate=wants_certificate, comments=comments,
        )

        # New institution typed in "Other" -> fold into the shared list so
        # the next person can pick it (same idea as account signup).
        _register_institution(institution)

        if wants_certificate:
            # Payment is mandatory for a certificate: the registration is NOT
            # treated as complete, and NO confirmation email is sent, until
            # the fee is actually paid. The record is created as PENDING only
            # so the Paystack charge has something to reconcile against; the
            # "registration received" email goes out from pay_verify / the
            # webhook once payment succeeds.
            reg.payment_status = WorkshopRegistration.PaymentStatus.PENDING
            reg.amount = ws.certificate_fee
            reg.currency = ws.fee_currency
            reg.payment_reference = f"MSREC-WS-{uuid.uuid4().hex[:18]}"
            reg.save(update_fields=["payment_status", "amount", "currency", "payment_reference"])
            return redirect("workshop:pay", pk=reg.pk)

        # Free registration (no certificate): complete immediately and
        # confirm by email (carries the meeting link when one is set).
        reg.payment_status = WorkshopRegistration.PaymentStatus.NOT_REQUIRED
        reg.save(update_fields=["payment_status"])
        _send_received_email(reg, ws)
        return redirect(f"{reverse('workshop:thanks')}?r={reg.pk}")

    return render(request, "workshop/register.html", _register_context(ws, {}))


def _register_context(ws, prefill):
    return {
        "ws": ws,
        "institutions": _active_institutions(),
        "prefill": prefill,
    }


def _send_received_email(reg, ws):
    """Best-effort confirmation email -- a mail hiccup never blocks the flow."""
    try:
        from . import emails
        emails.send_registration_received_email(reg, ws)
    except Exception:
        logger.exception("Workshop registration email failed for %s", reg.email)


def _register_institution(name):
    from django.db import transaction
    name = (name or "").strip()
    if not name:
        return
    try:
        with transaction.atomic():
            if not Institution.objects.filter(name__iexact=name).exists():
                Institution.objects.create(name=name[:200], is_active=True)
    except Exception:
        logger.exception("Could not auto-add workshop institution %r", name)


def pay(request, pk):
    reg = get_object_or_404(WorkshopRegistration, pk=pk)
    if not reg.wants_certificate:
        return redirect(f"{reverse('workshop:thanks')}?r={reg.pk}")
    if reg.is_paid:
        return redirect(f"{reverse('workshop:thanks')}?r={reg.pk}")

    ws = WorkshopSettings.get_solo()
    return render(request, "workshop/pay.html", {
        "reg": reg,
        "ws": ws,
        "paystack_public_key": SiteSettings.get_solo().effective_paystack_public_key,
        "verify_url": reverse("workshop:pay_verify", kwargs={"pk": reg.pk}),
    })


@require_POST
def pay_verify(request, pk):
    reg = get_object_or_404(WorkshopRegistration, pk=pk)
    reference = request.POST.get("reference", "").strip()
    if not reference or reference != reg.payment_reference:
        return JsonResponse({"ok": False, "error": "Payment reference mismatch."}, status=400)

    from payments import paystack

    if reg.is_paid:
        return JsonResponse({"ok": True, "redirect": f"{reverse('workshop:thanks')}?r={reg.pk}"})

    try:
        data = paystack.verify_transaction(reference)
    except paystack.PaystackError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    amount_ok = int(data.get("amount") or 0) == reg.amount_subunit
    currency_ok = (data.get("currency") or "").upper() == reg.currency.upper()
    if data.get("status") == "success" and amount_ok and currency_ok:
        reg.payment_status = WorkshopRegistration.PaymentStatus.SUCCESS
        reg.paid_at = timezone.now()
        reg.paystack_response = data
        reg.save(update_fields=["payment_status", "paid_at", "paystack_response"])
        # Now that payment has succeeded, the registration is complete --
        # send the confirmation email (with the meeting link if set).
        _send_received_email(reg, WorkshopSettings.get_solo())
        return JsonResponse({"ok": True, "redirect": f"{reverse('workshop:thanks')}?r={reg.pk}"})

    reg.payment_status = WorkshopRegistration.PaymentStatus.FAILED
    reg.paystack_response = data
    reg.save(update_fields=["payment_status", "paystack_response"])
    reason = data.get("gateway_response") or "Payment was not successful. Please try again."
    return JsonResponse({"ok": False, "error": reason}, status=400)


def thanks(request):
    reg = None
    rid = request.GET.get("r")
    if rid:
        reg = WorkshopRegistration.objects.filter(pk=rid).first()
    return render(request, "workshop/thanks.html", {
        "reg": reg,
        "ws": WorkshopSettings.get_solo(),
    })
