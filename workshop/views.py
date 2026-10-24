"""Public workshop pages: the Upcoming Workshops list, each workshop's
registration form, the Paystack checkout for certificate fees, and the
token-gated document downloads.
"""
import logging
import uuid
from decimal import Decimal

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from pages import institutions
from pages.models import SiteSettings

from . import dedupe
from .models import Workshop, WorkshopRegistration

logger = logging.getLogger(__name__)

# Who gets notified whenever someone registers for a workshop.
WORKSHOP_NOTIFY_EMAIL = "ceo@academicdigital.space"


def _notify_admin_of_registration(reg, ws):
    """Emails the workshop organiser the moment someone registers -- every
    registration, whether or not they want a certificate. Best-effort: never
    blocks or rolls back the registration."""
    try:
        from django.conf import settings
        from notifications.emails import send_branded_email

        manage_url = settings.SITE_URL.rstrip("/") + reverse(
            "workshop_admin:manage", kwargs={"pk": ws.pk}
        )
        contact = f"Email: {reg.email}" + (f" · Phone: {reg.phone}" if reg.phone else "")
        if reg.certificate_required_at_signup:
            extra = "Certificate: compulsory for this workshop"
        else:
            extra = "Wants certificate: " + ("Yes" if reg.wants_certificate else "No")
        # Say plainly when this isn't a registration yet, so the list isn't
        # read as more confirmed participants than there are.
        if reg.payment_outstanding:
            extra += (
                f" · AWAITING PAYMENT of {reg.currency} {reg.amount} "
                "— not a confirmed registration until it is paid"
            )
        if reg.comments:
            extra += f" · Comments: {reg.comments}"
        send_branded_email(
            subject=(
                f"Workshop registration awaiting payment — {reg.name}"
                if reg.payment_outstanding else f"New workshop registration — {reg.name}"
            ),
            to=WORKSHOP_NOTIFY_EMAIL,
            heading=(
                "Registration started — payment outstanding"
                if reg.payment_outstanding else "New workshop registration"
            ),
            paragraphs=[
                f"A new person has registered for {ws.title}.",
                f"Name: {reg.name}",
                f"Institution: {reg.institution}",
                contact,
                extra,
            ],
            cta_text="View registrations",
            cta_url=manage_url,
            preheader=f"{reg.name} registered for {ws.title}.",
        )
    except Exception:
        logger.exception("Workshop admin registration email failed for %s", reg.email)


def _active_institutions():
    return institutions.active()


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
        elif reg.wants_certificate:
            parts.append("Your certificate is included.")
        if ws.meeting_link:
            parts.append(f"Join: {ws.meeting_link}")
        sms.send_sms([reg.phone], " ".join(parts))
    except Exception:
        logger.exception("Workshop registration SMS failed for %s", reg.phone)


def _send_payment_link(reg, ws):
    """Best-effort: never blocks the redirect to checkout."""
    try:
        from . import emails
        emails.send_payment_required_email(reg, ws)
    except Exception:
        logger.exception("Workshop payment-link email failed for %s", reg.email)


def _register_institution(name):
    """Fold whatever the registrant typed into the Institution dropdown's
    "Other" box into the admin-managed list (pages.institutions)."""
    institutions.register([name])


def register(request, slug):
    ws = get_object_or_404(Workshop, slug=slug, is_published=True)

    if request.method == "POST":
        if not ws.registration_open:
            messages.error(request, "Registration for this workshop is closed.")
            return redirect("workshop:register", slug=ws.slug)

        name = request.POST.get("name", "").strip()
        institution = institutions.resolve_choice(
            request.POST.get("institution", ""), request.POST.get("institution_other", "")
        )
        email = request.POST.get("email", "").strip().lower()
        phone = request.POST.get("phone", "").strip()
        # Compulsory certificates: the form never asked, so nothing the
        # registrant posted can opt them out.
        cert_required = ws.certificate_required
        wants_certificate = cert_required or request.POST.get("wants_certificate") == "yes"
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
        if not cert_required and "wants_certificate" not in request.POST:
            errors.append("Please tell us whether you want a certificate.")
        if errors:
            for e in errors:
                messages.error(request, e)
            return render(request, "workshop/register.html", _register_context(ws, {
                "name": name, "institution": institution, "email": email,
                "phone": phone, "comments": comments,
            }), status=400)


        prefill = {
            "name": name, "institution": institution, "email": email,
            "phone": phone, "comments": comments,
        }

        # One registration per person per workshop. Scoped to this
        # workshop, so the same person registering for another one is
        # unaffected.
        clash, matched_on = dedupe.find_existing(ws, email=email, name=name)
        if clash is not None:
            return _already_registered(request, ws, clash, matched_on, prefill)

        # A certificate that costs something has to be paid for before the
        # registration counts -- whether the workshop compels it or they
        # chose it. A zero fee means there is nothing to pay either way.
        needs_payment = wants_certificate and ws.certificate_fee_payable

        # The row is written in its final state in one go, so that anything
        # reading it afterwards -- notably the organiser's notification --
        # sees the true payment state rather than a half-built row.
        try:
            with transaction.atomic():
                reg = WorkshopRegistration.objects.create(
                    workshop=ws, name=name[:200], institution=institution[:200], email=email,
                    phone=phone[:40], wants_certificate=wants_certificate,
                    certificate_required_at_signup=cert_required, comments=comments,
                    payment_status=(
                        WorkshopRegistration.PaymentStatus.PENDING if needs_payment
                        else WorkshopRegistration.PaymentStatus.NOT_REQUIRED
                    ),
                    amount=ws.certificate_fee if needs_payment else Decimal("0.00"),
                    currency=ws.fee_currency,
                    payment_reference=f"MSREC-WS-{uuid.uuid4().hex[:18]}" if needs_payment else "",
                )
        except IntegrityError:
            # Two submissions racing each other -- a double-click, or two
            # tabs -- can both pass the check above and arrive here
            # together. The database constraint is what actually guarantees
            # it; one of them loses, and is shown the row that won.
            clash, matched_on = dedupe.find_existing(ws, email=email, name=name)
            if clash is None:
                raise
            return _already_registered(request, ws, clash, matched_on, prefill)

        _register_institution(institution)
        # The organiser hears about every entry, flagged as awaiting payment
        # when it is -- so the list isn't read as more confirmed
        # participants than there are.
        _notify_admin_of_registration(reg, ws)

        if needs_payment:
            # They need a way back to the checkout if they close the page,
            # emailed and texted before the redirect, not after -- the
            # redirect is where they leave. No confirmation goes out yet:
            # they are not registered until this is paid.
            _send_payment_link(reg, ws)
            return redirect("workshop:pay", pk=reg.pk)

        _notify_registration_success(reg, ws)
        return redirect(f"{reverse('workshop:thanks')}?r={reg.pk}")

    return render(request, "workshop/register.html", _register_context(ws, {}))


def _already_registered(request, ws, clash, matched_on, prefill):
    """The "you're already on this list" page.

    Deliberately not a dead end. The live data showed people registering
    three times in four minutes because an unpaid registration left them
    with nowhere to go, so an email match offers that registration's
    checkout.

    A *name* match never does: a namesake is a different person, and
    handing them a payment link would show them someone else's
    registration. They get an explanation and the secretariat instead.
    """
    by_email = matched_on == dedupe.EMAIL
    return render(request, "workshop/register.html", _register_context(ws, prefill, duplicate={
        "matched_on": matched_on,
        "by_email": by_email,
        "name": clash.name,
        "registered_on": clash.created_at,
        # Only ever populated for an email match.
        "pay_url": (
            reverse("workshop:pay", kwargs={"pk": clash.pk})
            if by_email and clash.payment_outstanding else None
        ),
        "amount": clash.amount if by_email else None,
        "currency": clash.currency if by_email else None,
        "is_paid": clash.is_paid if by_email else False,
    }), status=409)


def _register_context(ws, prefill, duplicate=None):
    return {
        "ws": ws, "institutions": _active_institutions(), "prefill": prefill,
        "duplicate": duplicate,
    }


def pay(request, pk):
    reg = get_object_or_404(WorkshopRegistration, pk=pk)
    if not reg.payment_outstanding:
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


@require_POST
def decline_certificate(request, pk):
    """"I don't want a certificate after all" -- settles the fee at zero and
    completes the registration.

    Choosing a certificate commits you to paying for it, so there has to be
    a way to change that choice; otherwise the only way out is to register
    again without one, which is exactly what people did before this existed
    (the live data had someone registering twice two minutes apart, the
    second time opting out). Changing your selection is a different thing
    from selecting one and not paying.

    Only for a certificate the registrant chose. Where the workshop makes it
    compulsory there is nothing to decline, so that is refused.
    """
    reg = get_object_or_404(WorkshopRegistration, pk=pk)
    ws = reg.workshop

    if reg.certificate_required_at_signup:
        messages.error(request, "A certificate is part of this workshop and can't be removed.")
        return redirect("workshop:pay", pk=reg.pk)
    if reg.is_paid:
        return redirect(f"{reverse('workshop:thanks')}?r={reg.pk}")
    if not reg.payment_outstanding:
        return redirect(f"{reverse('workshop:thanks')}?r={reg.pk}")

    reg.wants_certificate = False
    reg.payment_status = WorkshopRegistration.PaymentStatus.NOT_REQUIRED
    reg.amount = Decimal("0.00")
    # The reference is kept: it was quoted to Paystack, so if a payment for
    # it ever does land, pay_verify can still find the row it belongs to.
    reg.save(update_fields=["wants_certificate", "payment_status", "amount"])

    _notify_registration_success(reg, ws)
    messages.success(
        request,
        "Your registration is confirmed without a certificate — there's nothing to pay.",
    )
    return redirect(f"{reverse('workshop:thanks')}?r={reg.pk}")


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
        if not reg.certificate_ready:
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
