"""Staff management of workshops (admin + secretariat): create workshops,
manage each one's registrations, settings, schedule and certificate design,
and approve participants to issue their documents.
"""
import logging
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from messaging.access import is_staff_side

from . import emails, storage
from .models import Workshop, WorkshopRegistration

logger = logging.getLogger(__name__)

staff_required = user_passes_test(is_staff_side, login_url="pages:login")


def _dashboard(request):
    """Which sidebar to show -- a Secretariat (non-admin) user gets the
    Secretariat sidebar even on these shared pages; everyone else the admin."""
    u = request.user
    from accounts.models import User
    if not u.is_superuser and u.role == User.Role.SECRETARIAT:
        return "secretariat"
    return "admin"


def _parse_dt(value):
    value = (value or "").strip()
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


# ---------------------------------------------------------------------
# Workshop list + create
# ---------------------------------------------------------------------

@login_required
@staff_required
def workshop_list(request):
    if request.method == "POST" and request.POST.get("action") == "create":
        title = request.POST.get("title", "").strip()
        if not title:
            messages.error(request, "Give the workshop a title.")
            return redirect("workshop_admin:list")
        ws = Workshop.objects.create(title=title[:200])
        messages.success(request, f'"{ws.title}" created. Set its details below.')
        return redirect("workshop_admin:manage", pk=ws.pk)

    workshops = list(Workshop.objects.all())
    for w in workshops:
        w.reg_count = w.registrations.count()
    return render(request, "dashboards/admin/workshop_list.html", {
        "workshops": workshops,
        "dashboard": _dashboard(request),
    })


# ---------------------------------------------------------------------
# Manage one workshop
# ---------------------------------------------------------------------

def _recipients(request, ws):
    reg_id = request.POST.get("reg_id")
    qs = ws.registrations.all()
    if reg_id:
        return qs.filter(pk=reg_id)
    scope = request.POST.get("scope", "")
    if scope == "wants_cert":
        return qs.filter(wants_certificate=True)
    if scope == "paid":
        return qs.filter(payment_status=WorkshopRegistration.PaymentStatus.SUCCESS)
    if scope == "no_cert":
        return qs.filter(wants_certificate=False)
    return qs


def _bulk(request, ws, fn, *, label):
    recipients = list(_recipients(request, ws))
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
    ws.title = request.POST.get("title", "").strip()[:200] or ws.title
    ws.tagline = request.POST.get("tagline", "").strip()[:300]
    ws.description = request.POST.get("description", "").strip()
    ws.location = request.POST.get("location", "").strip()[:255]
    ws.banner_image_link = request.POST.get("banner_image_link", "").strip()
    ws.meeting_link = request.POST.get("meeting_link", "").strip()
    ws.materials_link = request.POST.get("materials_link", "").strip()
    ws.fee_currency = request.POST.get("fee_currency", "").strip()[:10] or "GHS"
    ws.is_published = request.POST.get("is_published") == "on"
    ws.registration_closed = request.POST.get("registration_closed") == "on"
    ws.starts_at = _parse_dt(request.POST.get("starts_at"))
    ws.ends_at = _parse_dt(request.POST.get("ends_at"))
    ws.registration_closes_at = _parse_dt(request.POST.get("registration_closes_at"))

    raw_size = (request.POST.get("title_font_size") or "").strip()
    if raw_size.isdigit():
        ws.title_font_size = max(14, min(int(raw_size), 72))

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
            path = storage.upload_banner(banner, workshop_id=ws.pk)
            if path:
                ws.banner_image_path = path
                if old and old != path:
                    storage.delete_object(old)
            else:
                messages.warning(request, "The banner image couldn't be uploaded right now.")

    materials = request.FILES.get("materials_file")
    if materials:
        old = ws.materials_file_path
        path = storage.upload_materials(materials, workshop_id=ws.pk)
        if path:
            ws.materials_file_path = path
            if old and old != path:
                storage.delete_object(old)
        else:
            messages.warning(request, "The materials file couldn't be uploaded right now.")

    ws.save()
    messages.success(request, "Workshop settings saved.")


def _save_cert(request, ws):
    ws.cert_title_tail = request.POST.get("cert_title_tail", "").strip()[:80] or "of Participation"
    ws.cert_intro = request.POST.get("cert_intro", "").strip()[:200] or "This is to certify that"
    ws.cert_body = request.POST.get("cert_body", "").strip()
    ws.cert_seal_caption = request.POST.get("cert_seal_caption", "").strip()[:24] or "WORKSHOP"
    ws.cert_sig1_name = request.POST.get("sig1_name", "").strip()[:150]
    ws.cert_sig1_title = request.POST.get("sig1_title", "").strip()[:150]
    ws.cert_sig2_name = request.POST.get("sig2_name", "").strip()[:150]
    ws.cert_sig2_title = request.POST.get("sig2_title", "").strip()[:150]
    ws.cert_show_body = request.POST.get("cert_show_body") == "on"
    ws.cert_show_seal = request.POST.get("cert_show_seal") == "on"
    ws.cert_show_second_signature = request.POST.get("cert_show_second_signature") == "on"
    ws.cert_show_verification = request.POST.get("cert_show_verification") == "on"

    for which, field in ((1, "sig1_signature"), (2, "sig2_signature")):
        f = request.FILES.get(field)
        if f:
            if not (f.content_type or "").startswith("image/"):
                messages.error(request, f"Signature {which} must be an image.")
                continue
            path = storage.upload_signature(f, workshop_id=ws.pk, which=which)
            if path:
                if which == 1:
                    ws.cert_sig1_signature_path = path
                else:
                    ws.cert_sig2_signature_path = path
            else:
                messages.warning(request, f"Signature {which} couldn't be uploaded right now.")

    ws.save()
    messages.success(request, "Certificate design saved.")


@login_required
@staff_required
def workshop_manage(request, pk):
    ws = get_object_or_404(Workshop, pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_settings":
            _save_settings(request, ws)
        elif action == "save_cert":
            _save_cert(request, ws)
        elif action == "send_meeting_link":
            _bulk(request, ws, emails.send_meeting_link_email, label="Meeting link")
        elif action == "send_materials":
            _bulk(request, ws, emails.send_materials_email, label="Materials")
        elif action == "send_certificate":
            _bulk(request, ws, emails.send_certificate_email, label="Certificate")
        elif action == "approve_send":
            from . import approval
            _bulk(request, ws, approval.approve_and_send, label="Documents (certificate + letter)")
        elif action == "delete_registration":
            reg = get_object_or_404(WorkshopRegistration, pk=request.POST.get("reg_id"), workshop=ws)
            name = reg.name
            reg.delete()
            messages.success(request, f"Removed {name}'s registration.")
        elif action == "delete_workshop":
            title = ws.title
            ws.delete()
            messages.success(request, f'Workshop "{title}" and its registrations were deleted.')
            return redirect("workshop_admin:list")
        else:
            messages.error(request, "That request could not be processed.")
        return redirect(f"{reverse('workshop_admin:manage', kwargs={'pk': ws.pk})}#{request.POST.get('tab', 'registrations')}")

    regs = list(ws.registrations.all())
    paid = [r for r in regs if r.is_paid]
    wants_cert = [r for r in regs if r.wants_certificate]
    return render(request, "dashboards/admin/workshop_manage.html", {
        "ws": ws,
        "regs": regs,
        "counts": {
            "all": len(regs), "wants_cert": len(wants_cert),
            "no_cert": len(regs) - len(wants_cert), "paid": len(paid),
        },
        "dashboard": _dashboard(request),
    })


@login_required
@staff_required
def cert_preview(request, pk):
    ws = get_object_or_404(Workshop, pk=pk)
    from .certificate import render_workshop_certificate_pdf

    sample_name = (request.POST.get("sample_name") or request.GET.get("sample_name") or "").strip() or "Jane A. Doe"
    sample = WorkshopRegistration(
        workshop=ws, name=sample_name, institution="Sample University", email="sample@example.com",
        wants_certificate=True, payment_status=WorkshopRegistration.PaymentStatus.SUCCESS,
    )
    sample.paid_at = timezone.now()
    sample.pk = 0

    preview_ws = ws
    if request.method == "POST":
        # Preview unsaved edits (signature images come from the saved workshop).
        preview_ws = Workshop(
            pk=ws.pk, title=ws.title,
            cert_title_tail=request.POST.get("cert_title_tail", "").strip()[:80] or "of Participation",
            cert_intro=request.POST.get("cert_intro", "").strip()[:200] or "This is to certify that",
            cert_body=request.POST.get("cert_body", "").strip(),
            cert_seal_caption=request.POST.get("cert_seal_caption", "").strip()[:24] or "WORKSHOP",
            cert_sig1_name=request.POST.get("sig1_name", "").strip()[:150],
            cert_sig1_title=request.POST.get("sig1_title", "").strip()[:150],
            cert_sig2_name=request.POST.get("sig2_name", "").strip()[:150],
            cert_sig2_title=request.POST.get("sig2_title", "").strip()[:150],
            cert_sig1_signature_path=ws.cert_sig1_signature_path,
            cert_sig2_signature_path=ws.cert_sig2_signature_path,
            cert_show_body=request.POST.get("cert_show_body") == "on",
            cert_show_seal=request.POST.get("cert_show_seal") == "on",
            cert_show_second_signature=request.POST.get("cert_show_second_signature") == "on",
            cert_show_verification=request.POST.get("cert_show_verification") == "on",
        )

    try:
        pdf = render_workshop_certificate_pdf(sample, workshop=preview_ws)
    except Exception:
        logger.exception("Workshop certificate preview failed")
        return HttpResponse("Couldn't render the certificate preview.", status=500)
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="certificate-preview.pdf"'
    resp["X-Frame-Options"] = "SAMEORIGIN"
    return resp
