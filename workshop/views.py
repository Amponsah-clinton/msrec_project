"""Public workshop pages: the Upcoming Workshops list, each workshop's
registration form, the Paystack checkout for certificate fees, and the
token-gated document downloads.
"""
import logging
import uuid

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from pages.models import Institution, SiteSettings

from .models import Workshop, WorkshopRegistration

logger = logging.getLogger(__name__)

INSTITUTION_OTHER = "__other__"


def _active_institutions():
    return list(Institution.objects.filter(is_active=True))


def workshop_list(request):
    """The Upcoming Workshops page -- every published workshop, upcoming
    first, then past ones."""
    published = list(Workshop.objects.filter(is_published=True))
    upcoming = [w for w in published if not w.is_past]
    past = [w for w in published if w.is_past]
    # upcoming: soonest first; past: most recent first
    upcoming.sort(key=lambda w: (w.starts_at is None, w.starts_at or timezone.now()))
    past.sort(key=lambda w: (w.starts_at or w.created_at), reverse=True)
    return render(request, "workshop/list.html", {"upcoming": upcoming, "past": past})


def _notify_registration_success(reg, ws):
    try:
        from . import emails
        emails.send_registration_received_email(reg, ws)
    except Exception:
        logger.exception("Workshop registration email failed for %s", reg.email)
    _send_received_sms(reg, ws)


def _send_received_sms(reg, ws):
    try:
        from notifications import sms
        parts = [f"MSREC: You're registered for {ws.title}."]
        if reg.wants_certificate and reg.is_paid:
            parts.append("Certificate fee received.")
        if ws.meeting_link:
            parts.append(f"Join: {ws.meeting_link}")
        sms.send_sms([reg.phone], " ".join(parts))
    except Exception:
        logger.exception("Workshop registration SMS failed for %s", reg.phone)


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


def register(request, slug):
    ws = get_object_or_404(Workshop, slug=slug, is_published=True)

    if request.method == "POST":
        if not ws.registration_open:
            messages.error(request, "Registration for this workshop is closed.")
            return redirect("workshop:register", slug=ws.slug)

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
        if not phone:
            errors.append("Your phone number is required.")
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
            workshop=ws, name=name[:200], institution=institution[:200], email=email,
            phone=phone[:40], wants_certificate=wants_certificate, comments=comments,
        )
        _register_institution(institution)

        if wants_certificate:
            reg.payment_status = WorkshopRegistration.PaymentStatus.PENDING
            reg.amount = ws.certificate_fee
            reg.currency = ws.fee_currency
            reg.payment_reference = f"MSREC-WS-{uuid.uuid4().hex[:18]}"
            reg.save(update_fields=["payment_status", "amount", "currency", "payment_reference"])
            return redirect("workshop:pay", pk=reg.pk)

        reg.payment_status = WorkshopRegistration.PaymentStatus.NOT_REQUIRED
        reg.save(update_fields=["payment_status"])
        _notify_registration_success(reg, ws)
        return redirect(f"{reverse('workshop:thanks')}?r={reg.pk}")

    return render(request, "workshop/register.html", _register_context(ws, {}))


def _register_context(ws, prefill):
    return {"ws": ws, "institutions": _active_institutions(), "prefill": prefill}


def pay(request, pk):
    reg = get_object_or_404(WorkshopRegistration, pk=pk)
    if not reg.wants_certificate or reg.is_paid:
        return redirect(f"{reverse('workshop:thanks')}?r={reg.pk}")
    return render(request, "workshop/pay.html", {
        "reg": reg,
        "ws": reg.workshop,
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
        reg.ensure_certificate_ref()
        reg.save(update_fields=["payment_status", "paid_at", "paystack_response", "certificate_ref"])
        _notify_registration_success(reg, reg.workshop)
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
        reg = WorkshopRegistration.objects.filter(pk=rid).select_related("workshop").first()
    return render(request, "workshop/thanks.html", {
        "reg": reg,
        "ws": reg.workshop if reg else None,
    })


def cert_sample(request, slug):
    """A watermarked sample certificate for a workshop's public preview."""
    ws = get_object_or_404(Workshop, slug=slug, is_published=True)
    from .certificate import render_sample_certificate_pdf

    name = (request.GET.get("name") or "").strip()[:80] or "Your Name Here"
    try:
        pdf = render_sample_certificate_pdf(ws, name)
    except Exception:
        logger.exception("Workshop sample certificate failed")
        return HttpResponse("Couldn't render the sample certificate.", status=500)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = "inline; filename=sample-certificate.pdf"
    resp["X-Frame-Options"] = "SAMEORIGIN"
    resp["Cache-Control"] = "no-store"
    return resp


def _approved_or_404(token):
    reg = WorkshopRegistration.objects.filter(
        download_token=token, approved_at__isnull=False
    ).select_related("workshop").first()
    if reg is None or not token:
        raise Http404("No documents for this link.")
    return reg


def documents(request, token):
    reg = _approved_or_404(token)
    return render(request, "workshop/documents.html", {
        "reg": reg, "ws": reg.workshop, "token": token,
    })


def download_document(request, token, kind):
    reg = _approved_or_404(token)
    slug = "".join(c if c.isalnum() else "_" for c in (reg.name or "participant")).strip("_") or "participant"

    if kind == "letter":
        from .letter import render_confirmation_letter_pdf
        pdf = render_confirmation_letter_pdf(reg, reg.workshop)
        filename = f"{slug}_Confirmation_of_Participation.pdf"
    elif kind == "certificate":
        if not reg.is_paid:
            raise Http404("No certificate for this participant.")
        from .certificate import render_workshop_certificate_pdf
        pdf = render_workshop_certificate_pdf(reg, workshop=reg.workshop)
        reg.save(update_fields=["certificate_ref"])
        filename = f"{slug}_Certificate.pdf"
    else:
        raise Http404("Unknown document.")

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp["Cache-Control"] = "no-store"
    return resp
