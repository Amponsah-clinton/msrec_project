"""Staff management of workshops (admin + secretariat): create workshops,
manage each one's registrations, settings, schedule and certificate design,
and approve participants to issue their documents.
"""
import logging
import uuid
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import IntegrityError, transaction
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

    from django.db.models import Count, Q, Sum

    PS = WorkshopRegistration.PaymentStatus
    paid_q = Q(registrations__payment_status=PS.SUCCESS)
    owed_q = Q(registrations__wants_certificate=True,
               registrations__payment_status__in=[PS.PENDING, PS.FAILED])
    workshops = list(Workshop.objects.annotate(
        reg_count=Count("registrations"),
        paid_count=Count("registrations", filter=paid_q),
        owed_count=Count("registrations", filter=owed_q),
        collected=Sum("registrations__amount", filter=paid_q),
    ))

    # Soonest upcoming first, then undated drafts, then the most recent past.
    now = timezone.now()
    far = now + timezone.timedelta(days=36500)
    upcoming = sorted((w for w in workshops if not w.is_past), key=lambda w: w.starts_at or far)
    past = sorted((w for w in workshops if w.is_past), key=lambda w: w.starts_at or now, reverse=True)
    workshops = upcoming + past
    from django.utils.timesince import timesince, timeuntil

    for w in workshops:
        w.collected = w.collected or Decimal("0.00")
        # A short "when" for the card's corner: In 5 days / Live now / Ended 3 weeks ago.
        if not w.starts_at:
            w.when_label = "No date yet"
        elif w.is_past:
            w.when_label = f"Ended {timesince(w.ends_at or w.starts_at, now, depth=1)} ago"
        elif w.starts_at <= now:
            w.when_label = "Happening now"
        else:
            w.when_label = f"In {timeuntil(w.starts_at, now, depth=1)}"
        # How far along the fee-paying group is, for the card's bar.
        payers = w.paid_count + w.owed_count
        w.paid_pct = round(100 * w.paid_count / payers) if payers else 0
        if not w.is_published:
            w.state = "draft"
        elif w.is_past:
            w.state = "past"
        elif w.registration_open:
            w.state = "open"
        else:
            w.state = "closed"

    return render(request, "dashboards/admin/workshop_list.html", {
        "workshops": workshops,
        "totals": {
            "all": len(workshops),
            "open": sum(1 for w in workshops if w.state == "open"),
            "upcoming": len(upcoming),
            "past": len(past),
            "draft": sum(1 for w in workshops if w.state == "draft"),
            "registrations": sum(w.reg_count for w in workshops),
            "collected": sum((w.collected for w in workshops), Decimal("0.00")),
            "owed": sum(w.owed_count for w in workshops),
            "currency": workshops[0].fee_currency if workshops else "GHS",
        },
        "dashboard": _dashboard(request),
    })


# ---------------------------------------------------------------------
# Manage one workshop
# ---------------------------------------------------------------------

def _recipients(request, ws, params=None):
    """Who an action (or an export) is about: one row, the rows ticked or
    found by a search (reg_ids), or else the group chip (scope). `params`
    defaults to the POST; exports pass request.GET."""
    params = request.POST if params is None else params
    reg_id = params.get("reg_id")
    qs = ws.registrations.all()
    if reg_id:
        # An explicit single row is honoured even if flagged -- that is a
        # deliberate choice by the admin about that one person.
        return qs.filter(pk=reg_id)
    # Every group below excludes repeat registrations. Without this a bulk
    # send mails one person once per duplicate row they have: the live data
    # had someone with three, so they would have had three copies of the
    # meeting link and three certificates.
    qs = qs.filter(is_duplicate=False)
    # Rows ticked in the table win over the group chip -- always narrowed to
    # this workshop, so a tampered id can't reach another workshop's people.
    picked = [p for p in (params.get("reg_ids") or "").split(",") if p.strip().isdigit()]
    if picked:
        # Ticked rows are explicit too, so they bypass the duplicate filter.
        return ws.registrations.filter(pk__in=picked)
    scope = params.get("scope", "")
    if scope == "duplicates":
        return ws.registrations.filter(is_duplicate=True)
    if scope == "wants_cert":
        return qs.filter(wants_certificate=True)
    if scope == "paid":
        return qs.filter(payment_status=WorkshopRegistration.PaymentStatus.SUCCESS)
    if scope == "unpaid":
        return qs.filter(
            wants_certificate=True,
            payment_status__in=[
                WorkshopRegistration.PaymentStatus.PENDING,
                WorkshopRegistration.PaymentStatus.FAILED,
            ],
        )
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


def _send_message(request, ws):
    """The composer: a message staff write themselves, by email, SMS or both,
    to one person, the rows ticked in the table, or the group chip picked."""
    from notifications import sms

    use_email = request.POST.get("send_email") == "on"
    use_sms = request.POST.get("send_sms") == "on"
    subject = request.POST.get("subject", "").strip()[:200]
    body = request.POST.get("body", "").strip()
    sms_body = request.POST.get("sms_body", "").strip()
    button = request.POST.get("button", "")

    if not (use_email or use_sms):
        messages.error(request, "Choose email, SMS or both.")
        return
    if use_email and not (subject and body):
        messages.error(request, "The email needs a subject and a message.")
        return
    if use_sms and not sms_body:
        messages.error(request, "Write the SMS text, or untick SMS.")
        return
    if use_sms and not sms.is_configured():
        messages.error(request, "SMS isn't set up (BMS_API_KEY is missing), so nothing was sent.")
        return

    recipients = list(_recipients(request, ws))
    if not recipients:
        messages.error(request, "No registrations matched.")
        return

    reached = set()
    emailed = email_failed = 0
    if use_email:
        for reg in recipients:
            if emails.send_custom_email(reg, ws, subject=subject, body=body, button=button):
                emailed += 1
                reached.add(reg.pk)
            else:
                email_failed += 1

    texted = no_phone = sms_failed = 0
    sms_error = ""
    if use_sms:
        # One API call per distinct text: a message without placeholders goes
        # to everyone in a single bulk send; a personalised one per person.
        batches = {}
        for reg in recipients:
            phone = sms.clean_phone(reg.phone)
            if not phone:
                no_phone += 1
                continue
            text = emails.fill_placeholders(sms_body, reg, ws)
            batches.setdefault(text, []).append((phone, reg.pk))
        for text, people in batches.items():
            result = sms.send_sms([phone for phone, _ in people], text)
            if result.get("ok"):
                texted += len(people)
                reached.update(pk for _, pk in people)
            else:
                sms_failed += len(people)
                sms_error = result.get("error") or ""

    if reached:
        ws.registrations.filter(pk__in=reached).update(message_sent_at=timezone.now())

    parts = []
    if use_email:
        parts.append(f"email to {emailed}" + (f" ({email_failed} failed — check email settings)" if email_failed else ""))
    if use_sms:
        line = f"SMS to {texted}"
        extra = []
        if no_phone:
            extra.append(f"{no_phone} without a valid Ghana number")
        if sms_failed:
            extra.append(f"{sms_failed} failed{': ' + sms_error if sms_error else ''}")
        parts.append(line + (f" ({'; '.join(extra)})" if extra else ""))
    summary = "Message sent: " + ", ".join(parts) + "."
    if reached:
        messages.success(request, summary)
    else:
        messages.error(request, summary.replace("Message sent", "Nothing sent"))


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
    was_required = ws.certificate_required
    ws.certificate_required = request.POST.get("certificate_required") == "on"
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

    if ws.certificate_required:
        if ws.certificate_fee_payable:
            messages.info(
                request,
                f"Certificates are now compulsory — everyone who registers is charged "
                f"{ws.fee_currency} {ws.certificate_fee} and the form no longer asks.",
            )
        else:
            messages.warning(
                request,
                "Certificates are compulsory but the fee is 0, so nobody will be charged. "
                "Set a certificate fee if payment should be compulsory too.",
            )
        if not was_required:
            stragglers = ws.registrations.filter(wants_certificate=False).count()
            if stragglers:
                messages.warning(
                    request,
                    f"{stragglers} earlier registrant(s) opted out of a certificate. They keep "
                    "that choice unless you require it for them from the Registrations tab.",
                )
    elif was_required:
        messages.info(
            request,
            "Certificates are optional again — new registrants choose, and those who opt out pay nothing. "
            "People who already paid keep their certificate.",
        )


def _require_certificates_for_existing(request, ws):
    """Bring registrants who opted out into a now-compulsory certificate:
    book them for one, raise the fee against them and email + text a payment
    link. Anyone who already paid, or already owes the fee, is left alone."""
    if not ws.certificate_required:
        messages.error(
            request,
            "Turn on “Certificate compulsory for everyone” in Settings first.",
        )
        return

    targets = list(_recipients(request, ws).filter(wants_certificate=False))
    if not targets:
        messages.error(request, "Everyone registered is already down for a certificate.")
        return

    free = not ws.certificate_fee_payable
    charged = emailed = 0
    for reg in targets:
        reg.wants_certificate = True
        reg.certificate_required_at_signup = True
        reg.currency = ws.fee_currency
        if free:
            # Nothing to pay -- they simply get a certificate.
            reg.payment_status = WorkshopRegistration.PaymentStatus.NOT_REQUIRED
            reg.amount = Decimal("0.00")
        else:
            reg.payment_status = WorkshopRegistration.PaymentStatus.PENDING
            reg.amount = ws.certificate_fee
            if not reg.payment_reference:
                reg.payment_reference = f"MSREC-WS-{uuid.uuid4().hex[:18]}"
            charged += 1
        reg.save(update_fields=[
            "wants_certificate", "certificate_required_at_signup", "currency",
            "payment_status", "amount", "payment_reference",
        ])
        if not free:
            ok, _ = emails.send_payment_required_email(reg, ws)
            if ok:
                emailed += 1

    if free:
        messages.success(
            request,
            f"{len(targets)} registrant(s) are now down for a certificate. The fee is 0, so there is "
            "nothing for them to pay.",
        )
    else:
        messages.success(
            request,
            f"{charged} registrant(s) now owe {ws.fee_currency} {ws.certificate_fee} for a certificate. "
            f"Payment link sent to {emailed}."
            + (" Check email settings for the rest." if emailed < charged else ""),
        )


def _set_duplicate_flag(request, ws, *, flagged):
    """Mark a registration as a repeat, or restore it as the real one.

    Both directions are needed because the flag is a judgement: an admin
    may spot two namesakes that are genuinely different people (restore),
    or a repeat this rule didn't catch -- someone who registered twice
    under two addresses (flag).

    Restoring is the direction that can fail: the database allows only one
    unflagged row per email per workshop, so restoring a second one is
    refused rather than silently breaking the guarantee.
    """
    reg = get_object_or_404(WorkshopRegistration, pk=request.POST.get("reg_id"), workshop=ws)
    if reg.is_duplicate == flagged:
        messages.info(request, f"{reg.name} was already {'flagged' if flagged else 'active'}.")
        return

    reg.is_duplicate = flagged
    try:
        # Its own savepoint: without one, the failed INSERT leaves the
        # request's transaction unusable and the messages/redirect below
        # blow up with TransactionManagementError instead of explaining
        # the problem.
        with transaction.atomic():
            reg.save(update_fields=["is_duplicate"])
    except IntegrityError:
        messages.error(
            request,
            f"{reg.name} can't be restored: another active registration on this workshop "
            f"already uses {reg.email}. Flag that one first if this is the right row.",
        )
        return

    if flagged:
        messages.success(
            request,
            f"{reg.name} is now marked as a repeat registration — excluded from counts and "
            "bulk sends. Nothing was deleted.",
        )
    else:
        messages.success(request, f"{reg.name} is active again and back in all counts and sends.")


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
        elif action == "mark_duplicate":
            _set_duplicate_flag(request, ws, flagged=True)
        elif action == "unmark_duplicate":
            _set_duplicate_flag(request, ws, flagged=False)
        elif action == "send_payment_link":
            _bulk(request, ws, emails.send_payment_required_email, label="Payment link")
        elif action == "send_message":
            _send_message(request, ws)
        elif action == "require_certificates":
            _require_certificates_for_existing(request, ws)
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

    from notifications import sms

    regs = list(ws.registrations.all())
    for r in regs:
        r.sms_ok = bool(sms.clean_phone(r.phone))
    # Every headline count is of real participants, so a flagged repeat
    # never inflates "Registered" or the outstanding-fee total.
    active = [r for r in regs if not r.is_duplicate]
    duplicates = [r for r in regs if r.is_duplicate]
    paid = [r for r in active if r.is_paid]
    wants_cert = [r for r in active if r.wants_certificate]
    unpaid = [r for r in active if r.payment_outstanding]
    return render(request, "dashboards/admin/workshop_manage.html", {
        "ws": ws,
        "regs": regs,
        "counts": {
            "all": len(active), "wants_cert": len(wants_cert),
            "no_cert": len(active) - len(wants_cert), "paid": len(paid),
            "unpaid": len(unpaid),
            # Confirmed participants: asking for a certificate is a
            # commitment to pay, so an outstanding fee is a held place, not
            # a registration. Kept separate from "all" so the send scopes
            # can still reach everyone, including those being chased.
            "confirmed": len(active) - len(unpaid),
            "duplicates": len(duplicates),
            "outstanding": sum((r.amount for r in unpaid), Decimal("0.00")),
        },
        "sms_configured": sms.is_configured(),
        "dashboard": _dashboard(request),
    })


@login_required
@staff_required
def registrations_export(request, pk):
    """CSV or PDF of the registrations the Registrations tab is showing:
    the same chip, search and ticks the send buttons use (see _recipients),
    so what's exported is exactly what was on screen."""
    from . import exports

    ws = get_object_or_404(Workshop, pk=pk)
    regs = _recipients(request, ws, request.GET).order_by("-created_at")
    label = (request.GET.get("label") or "").strip()[:160]
    if request.GET.get("format") == "pdf":
        who = request.user.get_full_name() or request.user.email
        return exports.pdf_response(ws, regs, label, prepared_by=who)
    return exports.csv_response(ws, regs)


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


# ---------------------------------------------------------------------
# Contacts: everyone who has ever registered for a workshop
# ---------------------------------------------------------------------

def _contact_filters(params):
    return {
        "q": (params.get("q") or "").strip(),
        "workshop": (params.get("workshop") or "").strip(),
        "paid": params.get("paid") or "",
        "phone": params.get("phone") or "",
        "repeat": params.get("repeat") or "",
        "sort": params.get("sort") or "recent",
    }


def _filtered_contacts(f, ids=None):
    """The contacts matching the page's filters -- the same list the table
    shows, the composer sends to and the exports write out. Filtered in
    Python because `history` is JSON (no portable JSON lookups on SQLite),
    and the list is small enough for that to be instant."""
    from notifications import sms
    from .models import WorkshopContact

    qs = WorkshopContact.objects.all()
    if ids:
        qs = qs.filter(pk__in=ids)
    out = []
    q = f["q"].lower()
    for c in qs:
        c.sms_ok = bool(sms.clean_phone(c.phone))
        if q and q not in " ".join([c.name, c.email, c.phone, c.institution, *c.other_emails, *c.other_phones]).lower():
            continue
        if f["workshop"] and not any(str(e.get("workshop_id")) == f["workshop"] for e in c.history):
            continue
        if f["paid"] == "yes" and not c.has_paid:
            continue
        if f["paid"] == "no" and c.has_paid:
            continue
        if f["phone"] == "yes" and not c.sms_ok:
            continue
        if f["phone"] == "no" and c.sms_ok:
            continue
        if f["repeat"] == "yes" and c.registration_count < 2:
            continue
        out.append(c)
    if f["sort"] == "name":
        out.sort(key=lambda c: c.name.lower())
    elif f["sort"] == "most":
        out.sort(key=lambda c: (-c.registration_count, c.name.lower()))
    elif f["sort"] == "oldest":
        out.sort(key=lambda c: c.first_registered_at or timezone.now())
    return out


def _picked_ids(params):
    return [p for p in (params.get("ids") or "").split(",") if p.strip().isdigit()]


def _send_contact_message(request, people):
    from notifications import sms
    from . import contacts as contact_list
    from .models import WorkshopContact

    use_email = request.POST.get("send_email") == "on"
    use_sms = request.POST.get("send_sms") == "on"
    subject = request.POST.get("subject", "").strip()[:200]
    body = request.POST.get("body", "").strip()
    sms_body = request.POST.get("sms_body", "").strip()

    if not (use_email or use_sms):
        messages.error(request, "Choose email, SMS or both.")
        return
    if use_email and not (subject and body):
        messages.error(request, "The email needs a subject and a message.")
        return
    if use_sms and not sms_body:
        messages.error(request, "Write the SMS text, or untick SMS.")
        return
    if use_sms and not sms.is_configured():
        messages.error(request, "SMS isn't set up (BMS_API_KEY is missing), so nothing was sent.")
        return
    if not people:
        messages.error(request, "Nobody matched.")
        return

    reached = set()
    emailed = email_failed = 0
    if use_email:
        for c in people:
            if contact_list.send_email(c, subject=subject, body=body):
                emailed += 1
                reached.add(c.pk)
            else:
                email_failed += 1

    texted = no_phone = sms_failed = 0
    sms_error = ""
    if use_sms:
        batches = {}
        for c in people:
            phone = sms.clean_phone(c.phone)
            if not phone:
                no_phone += 1
                continue
            batches.setdefault(contact_list.fill(sms_body, c), []).append((phone, c.pk))
        for text, group in batches.items():
            result = sms.send_sms([p for p, _ in group], text)
            if result.get("ok"):
                texted += len(group)
                reached.update(pk for _, pk in group)
            else:
                sms_failed += len(group)
                sms_error = result.get("error") or ""

    if reached:
        WorkshopContact.objects.filter(pk__in=reached).update(last_messaged_at=timezone.now())

    parts = []
    if use_email:
        parts.append(f"email to {emailed}" + (f" ({email_failed} failed — check email settings)" if email_failed else ""))
    if use_sms:
        extra = []
        if no_phone:
            extra.append(f"{no_phone} without a valid Ghana number")
        if sms_failed:
            extra.append(f"{sms_failed} failed{': ' + sms_error if sms_error else ''}")
        parts.append(f"SMS to {texted}" + (f" ({'; '.join(extra)})" if extra else ""))
    summary = ", ".join(parts) + "."
    if reached:
        messages.success(request, "Message sent: " + summary)
    else:
        messages.error(request, "Nothing sent: " + summary)


@login_required
@staff_required
def contacts(request):
    from notifications import sms
    from .models import WorkshopContact

    if request.method == "POST":
        f = _contact_filters(request.POST)
        action = request.POST.get("action")
        if action == "send_message":
            _send_contact_message(request, _filtered_contacts(f, _picked_ids(request.POST)))
        elif action == "delete_contact":
            c = get_object_or_404(WorkshopContact, pk=request.POST.get("contact_id"))
            messages.success(request, f"Removed {c.name} from the contact list.")
            c.delete()
        else:
            messages.error(request, "That request could not be processed.")
        back = request.POST.get("return_query", "")
        return redirect(reverse("workshop_admin:contacts") + (f"?{back}" if back else ""))

    f = _contact_filters(request.GET)
    people = _filtered_contacts(f)

    # Everything the per-person workshop modal shows, handed to the page as
    # JSON so opening it needs no extra request.
    live = {w.pk: w for w in Workshop.objects.only("pk", "ends_at", "starts_at")}
    now = timezone.now()

    def fmt(dt, pattern):
        return timezone.localtime(dt).strftime(pattern).replace(" 0", " ").lstrip("0") if dt else ""

    modal = {}
    for c in people:
        groups = []
        for g in c.workshop_groups:
            ws = live.get(g["workshop_id"])
            end = (ws.ends_at or ws.starts_at) if ws else g["date"]
            groups.append({
                "title": g["title"],
                "date": fmt(g["date"], "%a %d %b %Y"),
                "time": fmt(g["date"], "%I:%M %p").lstrip("0"),
                "registered": fmt(g["first"], "%d %b %Y"),
                "times": g["times"],
                "paid": g["paid"],
                "past": bool(end and end < now),
                "url": reverse("workshop_admin:manage", kwargs={"pk": ws.pk}) if ws else "",
            })
        modal[c.pk] = {
            "name": c.name, "institution": c.institution,
            "email": c.email, "phone": c.phone,
            "other_emails": c.other_emails, "other_phones": c.other_phones,
            "first": fmt(c.first_registered_at, "%d %b %Y"),
            "messaged": fmt(c.last_messaged_at, "%d %b %Y"),
            "sms_ok": c.sms_ok,
            "registrations": len(c.history or []),
            "workshops": groups,
        }

    everyone = list(WorkshopContact.objects.only("phone", "has_paid", "registration_count"))
    return render(request, "dashboards/admin/workshop_contacts.html", {
        "people": people,
        "modal": modal,
        "f": f,
        "query": request.GET.urlencode(),
        "workshops": Workshop.objects.order_by("-starts_at", "-created_at").only("pk", "title", "starts_at"),
        "stats": {
            "all": len(everyone),
            "sms": sum(1 for c in everyone if sms.clean_phone(c.phone)),
            "paid": sum(1 for c in everyone if c.has_paid),
            "repeat": sum(1 for c in everyone if c.registration_count > 1),
        },
        "filtered": any(f[k] for k in ("q", "workshop", "paid", "phone", "repeat")),
        "sms_configured": sms.is_configured(),
        "dashboard": _dashboard(request),
    })


@login_required
@staff_required
def contacts_export(request):
    """CSV of the contacts on screen (or just the ticked ones).
    ?kind=full -- every detail, for a spreadsheet.
    ?kind=sms  -- one row per reachable Ghana mobile number, in the
                  0XXXXXXXXX form bulk-SMS tools (mNotify/BMS) import."""
    import csv

    from notifications import sms

    f = _contact_filters(request.GET)
    people = _filtered_contacts(f, _picked_ids(request.GET))
    today = timezone.localdate().isoformat()

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    # A BOM so Excel opens names with accents (é, ɛ, ɔ ...) correctly.
    response.write("﻿")
    writer = csv.writer(response)

    def day(dt):
        return timezone.localtime(dt).strftime("%d %b %Y") if dt else ""

    if request.GET.get("kind") == "sms":
        response["Content-Disposition"] = f'attachment; filename="msrec-workshop-sms-list-{today}.csv"'
        writer.writerow(["Phone", "Name", "First Name"])
        seen = set()
        for c in people:
            phone = sms.clean_phone(c.phone)
            if phone and phone not in seen:
                seen.add(phone)
                writer.writerow([phone, c.name, c.first_name])
        return response

    response["Content-Disposition"] = f'attachment; filename="msrec-workshop-contacts-{today}.csv"'
    writer.writerow([
        "Name", "Email", "Phone", "SMS Number", "Institution", "Other Emails", "Other Phones",
        "Workshops Registered", "Workshops", "Paid a Certificate Fee",
        "First Registered", "Last Registered", "Last Messaged",
    ])
    for c in people:
        writer.writerow([
            c.name, c.email, c.phone, sms.clean_phone(c.phone), c.institution,
            "; ".join(c.other_emails), "; ".join(c.other_phones),
            c.registration_count, "; ".join(c.workshop_titles), "Yes" if c.has_paid else "No",
            day(c.first_registered_at), day(c.last_registered_at), day(c.last_messaged_at),
        ])
    return response
