"""Admin workshop management (/admins/workshop/): the registrant list
(grouped into certificate / no-certificate / paid), the per-person and bulk
send actions (meeting link, certificate, materials), delete, plus the
Workshop Settings and Certificate Design editors.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from messaging.access import is_staff_side

from . import emails, storage
from .models import WorkshopCertificateTemplate, WorkshopRegistration, WorkshopSettings

logger = logging.getLogger(__name__)

staff_required = user_passes_test(is_staff_side, login_url="pages:login")


def _recipients(request):
    """The registrations a send-action targets: one (reg_id) or a group."""
    reg_id = request.POST.get("reg_id")
    if reg_id:
        return WorkshopRegistration.objects.filter(pk=reg_id)
    scope = request.POST.get("scope", "")
    qs = WorkshopRegistration.objects.all()
    if scope == "wants_cert":
        return qs.filter(wants_certificate=True)
    if scope == "paid":
        return qs.filter(payment_status=WorkshopRegistration.PaymentStatus.SUCCESS)
    if scope == "no_cert":
        return qs.filter(wants_certificate=False)
    return qs  # "all"


def _bulk(request, fn, ws, *, label):
    """Run a per-registration email fn across the targeted recipients and
    flash one combined result."""
    recipients = list(_recipients(request))
    if not recipients:
        messages.error(request, "No registrations matched.")
        return
    sent = skipped = 0
    last_reason = ""
    for reg in recipients:
        ok, reason = fn(reg, ws)
        if ok:
            sent += 1
        else:
            skipped += 1
            last_reason = reason
    if sent:
        messages.success(request, f"{label}: sent to {sent} registrant(s)." + (f" {skipped} skipped." if skipped else ""))
    else:
        messages.error(request, f"{label}: nothing sent. {last_reason}")


def _save_settings(request, ws):
    ws.workshop_title = request.POST.get("workshop_title", "").strip()[:200] or ws.workshop_title
    ws.workshop_tagline = request.POST.get("workshop_tagline", "").strip()[:300]
    ws.workshop_description = request.POST.get("workshop_description", "").strip()
    ws.banner_image_link = request.POST.get("banner_image_link", "").strip()
    ws.meeting_link = request.POST.get("meeting_link", "").strip()
    ws.materials_link = request.POST.get("materials_link", "").strip()
    ws.fee_currency = request.POST.get("fee_currency", "").strip()[:10] or "GHS"
    ws.registration_open = request.POST.get("registration_open") == "on"

    raw_fee = request.POST.get("certificate_fee", "").strip()
    if raw_fee:
        try:
            ws.certificate_fee = Decimal(raw_fee).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            messages.error(request, "Enter a valid certificate fee.")

    banner = request.FILES.get("banner_image")
    if banner:
        if not (banner.content_type or "").startswith("image/"):
            messages.error(request, "The banner must be an image file.")
        else:
            old = ws.banner_image_path
            path = storage.upload_banner(banner)
            if path:
                ws.banner_image_path = path
                if old and old != path:
                    storage.delete_object(old)
            else:
                messages.warning(request, "The banner image couldn't be uploaded right now.")

    materials = request.FILES.get("materials_file")
    if materials:
        old = ws.materials_file_path
        path = storage.upload_materials(materials)
        if path:
            ws.materials_file_path = path
            if old and old != path:
                storage.delete_object(old)
        else:
            messages.warning(request, "The materials file couldn't be uploaded right now.")

    ws.save()
    messages.success(request, "Workshop settings saved.")


def _save_cert_template(request):
    tpl = WorkshopCertificateTemplate.get_solo()
    tpl.title = request.POST.get("cert_title", "").strip()[:60] or "Certificate"
    tpl.title_tail = request.POST.get("cert_title_tail", "").strip()[:80]
    tpl.intro = request.POST.get("cert_intro", "").strip()[:200]
    tpl.body = request.POST.get("cert_body", "").strip()
    tpl.seal_caption = request.POST.get("cert_seal_caption", "").strip()[:24] or "WORKSHOP"
    tpl.signatory1_name = request.POST.get("sig1_name", "").strip()[:150]
    tpl.signatory1_title = request.POST.get("sig1_title", "").strip()[:150]
    tpl.signatory2_name = request.POST.get("sig2_name", "").strip()[:150]
    tpl.signatory2_title = request.POST.get("sig2_title", "").strip()[:150]

    for which, field in ((1, "sig1_signature"), (2, "sig2_signature")):
        f = request.FILES.get(field)
        if f:
            if not (f.content_type or "").startswith("image/"):
                messages.error(request, f"Signature {which} must be a (preferably transparent PNG) image.")
                continue
            path = storage.upload_signature(f, which=which)
            if path:
                if which == 1:
                    tpl.signatory1_signature_path = path
                else:
                    tpl.signatory2_signature_path = path
            else:
                messages.warning(request, f"Signature {which} couldn't be uploaded right now.")

    tpl.save()
    messages.success(request, "Certificate design saved.")


@login_required
@staff_required
def admin_workshop(request):
    ws = WorkshopSettings.get_solo()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_settings":
            _save_settings(request, ws)
        elif action == "save_cert_template":
            _save_cert_template(request)
        elif action == "send_meeting_link":
            _bulk(request, emails.send_meeting_link_email, ws, label="Meeting link")
        elif action == "send_certificate":
            _bulk(request, emails.send_certificate_email, ws, label="Certificate")
        elif action == "send_materials":
            _bulk(request, emails.send_materials_email, ws, label="Materials")
        elif action == "delete":
            reg = get_object_or_404(WorkshopRegistration, pk=request.POST.get("reg_id"))
            name = reg.name
            reg.delete()
            messages.success(request, f"Removed {name}'s registration.")
        else:
            messages.error(request, "That request could not be processed.")
        return redirect(f"{request.path}#{request.POST.get('tab', 'registrations')}")

    regs = list(WorkshopRegistration.objects.all())
    paid = [r for r in regs if r.is_paid]
    wants_cert = [r for r in regs if r.wants_certificate]
    no_cert = [r for r in regs if not r.wants_certificate]

    return render(request, "dashboards/admin/workshop.html", {
        "ws": ws,
        "cert_tpl": WorkshopCertificateTemplate.get_solo(),
        "regs": regs,
        "wants_cert": wants_cert,
        "no_cert": no_cert,
        "paid": paid,
        "counts": {
            "all": len(regs), "wants_cert": len(wants_cert),
            "no_cert": len(no_cert), "paid": len(paid),
        },
    })


@login_required
@staff_required
def admin_cert_preview(request):
    """A sample certificate PDF (dummy recipient) so an admin can see the
    current design without emailing anyone."""
    from .certificate import render_workshop_certificate_pdf

    sample = WorkshopRegistration(
        name="Jane A. Doe", institution="Sample University", email="sample@example.com",
        wants_certificate=True, payment_status=WorkshopRegistration.PaymentStatus.SUCCESS,
    )
    from django.utils import timezone
    sample.paid_at = timezone.now()
    sample.pk = 0
    try:
        pdf = render_workshop_certificate_pdf(sample)
    except Exception:
        logger.exception("Workshop certificate preview failed")
        messages.error(request, "Couldn't render the certificate preview.")
        return redirect("workshop_admin:home")
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="certificate-preview.pdf"'
    return resp
