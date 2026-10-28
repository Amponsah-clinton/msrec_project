"""PSA pages.

Staff (Admin + Secretariat, under /admins/psa/): the list with search,
filters and CSV export; the create/edit form; one agreement's page with
its actions (send, resend, cancel, delete).

Client (public, /psa/<token>/): the agreement as sent, where the client
confirms their details and signs -- and, once signed, their copy. Also
/psa/pay/<token>/, where they settle what is owing against it.
"""
import csv
import ipaddress
import logging
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from messaging.access import is_staff_side

from . import emails
from .forms import (parse_agreement, parse_change_request, parse_client, parse_payment,
                    parse_payment_request, parse_signature)
from .models import CURRENCIES, ChangeRequest, Payment, PaymentRequest, ServiceAgreement

logger = logging.getLogger(__name__)

staff_required = user_passes_test(is_staff_side, login_url="pages:login")

PER_PAGE = 20
Status = ServiceAgreement.Status

# The text fields the staff form round-trips, so a failed save shows the
# form again exactly as it was typed.
FORM_FIELDS = (
    "agreement_date", "client_name", "client_email", "client_address",
    "start_date", "completion_date", "service_title", "currency", "fee", "payment_basis",
    "payment_basis_other", "deposit", "payment_schedule",
)

SORTS = {
    "newest": ("-created_at",),
    "oldest": ("created_at",),
    "client": ("client_name", "-created_at"),
    "fee_high": ("-fee", "-created_at"),
    "fee_low": ("fee", "-created_at"),
    "agreement_date": ("-agreement_date", "-created_at"),
    # On the `owing` annotation added by _filtered.
    "owing_high": ("-owing", "-created_at"),
    "owing_low": ("owing", "-created_at"),
    # Nulls last either way: an agreement with no deadline isn't the most
    # urgent thing on the list, nor the least.
    "deadline_soon": (F("completion_date").asc(nulls_last=True), "-created_at"),
    "deadline_late": (F("completion_date").desc(nulls_last=True), "-created_at"),
}

MONEY = DecimalField(max_digits=14, decimal_places=2)
ZERO = Value(Decimal("0.00"), output_field=MONEY)

PAY_CHOICES = [
    ("owing", "Still owing"), ("unpaid", "Nothing paid"), ("part", "Part paid"),
    ("settled", "Paid in full"), ("over", "Overpaid"),
]

# The money filter: what each choice means as a filter on the annotations.
PAY_FILTERS = {
    "owing": Q(fee__isnull=False, owing__gt=0),          # anything still due
    "unpaid": Q(fee__isnull=False, paid_total=0),
    "part": Q(fee__isnull=False, paid_total__gt=0, owing__gt=0),
    "settled": Q(fee__isnull=False, owing=0),
    "over": Q(owing__lt=0),
}


def _dashboard(request):
    """Which sidebar to show: a Secretariat (non-admin) user gets the
    Secretariat sidebar on these shared pages; everyone else the admin."""
    from accounts.models import User
    u = request.user
    if not u.is_superuser and u.role == User.Role.SECRETARIAT:
        return "secretariat"
    return "admin"


def _role_label(user):
    from accounts.models import User
    if user.is_superuser or user.role == User.Role.ADMIN:
        return "Administrator"
    return "Secretariat"


# ---------------------------------------------------------------------
# List, search, filter, export
# ---------------------------------------------------------------------

def _with_money(qs):
    """Add `paid_total` (the deposit plus the ledger) and `owing` (fee less
    that) to every row, so the list can show, sort and filter on what's
    owing without a query per agreement. A subquery rather than a join, so
    the other filters can't multiply the rows the sum runs over.

    The deposit counts as received, the same way ServiceAgreement.
    amount_paid does -- it is the amount taken upfront, so an agreement
    with a deposit and no entries yet is part paid, not unpaid.
    `_ledger_total` is the entries on their own, for showing the two
    apart. `owing` treats a missing fee as zero -- nothing is owed until a
    fee is agreed -- and the templates read `a.amount_owing`, which is
    None in that case, rather than the annotation.
    """
    entries = Coalesce(Subquery(
        Payment.objects.filter(agreement=OuterRef("pk"))
        .values("agreement").annotate(t=Sum("amount")).values("t"),
        output_field=MONEY,
    ), ZERO)
    paid = Coalesce(F("deposit"), ZERO) + entries
    return qs.annotate(
        _ledger_total=entries,
        paid_total=paid,
        owing=Coalesce(F("fee"), ZERO) - paid,
    )


def _filters(params):
    f = {
        "q": (params.get("q") or "").strip(),
        "status": params.get("status") or "",
        "basis": params.get("basis") or "",
        "currency": params.get("currency") or "",
        "date_from": params.get("date_from") or "",
        "date_to": params.get("date_to") or "",
        "pay": params.get("pay") or "",
        "sort": params.get("sort") or "newest",
    }
    if f["pay"] not in PAY_FILTERS:
        f["pay"] = ""
    if f["status"] not in Status.values:
        f["status"] = ""
    if f["basis"] not in ServiceAgreement.Basis.values:
        f["basis"] = ""
    if f["currency"] not in dict(CURRENCIES):
        f["currency"] = ""
    if f["sort"] not in SORTS:
        f["sort"] = "newest"
    return f


def _filtered(f):
    from .forms import _date

    qs = _with_money(ServiceAgreement.objects.select_related("created_by", "company_signed_by"))
    if f["q"]:
        for word in f["q"].split():
            qs = qs.filter(
                Q(reference__icontains=word) | Q(client_name__icontains=word)
                | Q(client_email__icontains=word) | Q(client_phone__icontains=word)
                | Q(service_title__icontains=word)
            )
    if f["status"]:
        qs = qs.filter(status=f["status"])
    if f["basis"]:
        qs = qs.filter(payment_basis=f["basis"])
    if f["currency"]:
        qs = qs.filter(currency=f["currency"])
    start, end = _date(f["date_from"]), _date(f["date_to"])
    if start:
        qs = qs.filter(agreement_date__gte=start)
    if end:
        qs = qs.filter(agreement_date__lte=end)
    if f["pay"]:
        qs = qs.filter(PAY_FILTERS[f["pay"]])
    return qs.order_by(*SORTS[f["sort"]])


@login_required
@staff_required
def psa_list(request):
    f = _filters(request.GET)
    matching = _filtered(f)
    paginator = Paginator(matching, PER_PAGE)
    page = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    counts = dict(ServiceAgreement.objects.values_list("status").annotate(n=Count("pk")))
    signed_value = list(
        ServiceAgreement.objects.filter(status=Status.SIGNED, fee__isnull=False)
        .values("currency").annotate(total=Sum("fee")).order_by("currency")
    )
    # What clients still owe, per currency. Live agreements only: a draft
    # isn't an obligation yet and a cancelled one no longer is.
    outstanding = list(
        _with_money(ServiceAgreement.objects.filter(
            status__in=(Status.SENT, Status.CHANGES, Status.SIGNED), fee__isnull=False))
        .filter(owing__gt=0).values("currency").annotate(total=Sum("owing")).order_by("currency")
    )
    return render(request, "psa/admin_list.html", {
        "page": page,
        "page_range": paginator.get_elided_page_range(page.number, on_each_side=1, on_ends=1),
        "matching_count": paginator.count,
        "f": f,
        "query": params.urlencode(),
        "filtered": any(f[k] for k in ("q", "status", "basis", "currency", "date_from", "date_to", "pay")),
        "stats": {
            "all": sum(counts.values()),
            "draft": counts.get(Status.DRAFT, 0),
            "sent": counts.get(Status.SENT, 0),
            "changes": counts.get(Status.CHANGES, 0),
            "signed": counts.get(Status.SIGNED, 0),
            "cancelled": counts.get(Status.CANCELLED, 0),
        },
        "signed_value": signed_value,
        "outstanding": outstanding,
        "statuses": Status.choices,
        "bases": ServiceAgreement.Basis.choices,
        "currencies": CURRENCIES,
        "pay_filters": PAY_CHOICES,
        "methods": Payment.Method.choices,
        "today": timezone.localdate(),
        "dashboard": _dashboard(request),
    })


@login_required
@staff_required
def psa_export(request):
    """CSV of every agreement matching the list's filters (not only the
    page on screen)."""
    rows = _filtered(_filters(request.GET)).prefetch_related("change_requests", "payments")
    today = timezone.localdate().isoformat()
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="metascholar-psa-{today}.csv"'
    # A BOM so Excel reads names with accents (é, ɛ, ɔ ...) correctly.
    response.write("﻿")
    writer = csv.writer(response)

    def when(dt):
        return timezone.localtime(dt).strftime("%d %b %Y %H:%M") if dt else ""

    def day(d):
        return d.strftime("%d %b %Y") if d else ""

    writer.writerow([
        "Reference", "Status", "Agreement Date", "Client Name", "Client Email", "Client Phone",
        "Client Address", "Service / Project Title", "Deliverables", "Start Date",
        "Expected Completion", "Currency", "Agreed Fee", "Payment Basis", "Deposit / Upfront",
        "Balance After Deposit", "Payment Schedule", "Total Received (Deposit + Payments)",
        "Payments Since Deposit", "Amount Owing", "Payment Status",
        "Payments Recorded", "Last Payment On", "Signed for Metascholar By", "Company Signed On",
        "Client Signed On", "First Sent", "Times Sent", "Client First Opened", "Created By",
        "Created On", "Change Requests", "Open Change Request",
    ])
    for a in rows:
        requests = list(a.change_requests.all())   # newest first
        open_req = next((r for r in requests if not r.resolved_at), None)
        payments = list(a.payments.all())          # newest first
        writer.writerow([
            a.reference, a.get_status_display(), day(a.agreement_date), a.client_name,
            a.client_email, a.client_phone, a.client_address, a.service_title,
            " | ".join(f"{i}. {d}" for i, d in enumerate(a.deliverable_list(), start=1)),
            day(a.start_date), day(a.completion_date), a.currency,
            a.fee if a.fee is not None else "", a.payment_basis_label, a.deposit,
            a.balance if a.balance is not None else "", a.payment_schedule,
            a.amount_paid, a.ledger_total, a.amount_owing if a.amount_owing is not None else "",
            a.payment_state_label, len(payments),
            day(payments[0].paid_on) if payments else "",
            a.company_signatory_name, when(a.company_signed_at), when(a.client_signed_at),
            when(a.sent_at), a.send_count, when(a.viewed_at),
            a.created_by.full_name if a.created_by else "", when(a.created_at),
            len(requests),
            f"{open_req.get_section_display()}: {open_req.message}" if open_req else "",
        ])
    return response


# ---------------------------------------------------------------------
# Create / edit
# ---------------------------------------------------------------------

def _values_from(a):
    def iso(d):
        return d.isoformat() if d else ""
    return {
        "agreement_date": iso(a.agreement_date), "client_name": a.client_name,
        "client_email": a.client_email,
        "client_address": a.client_address, "start_date": iso(a.start_date),
        "completion_date": iso(a.completion_date), "service_title": a.service_title,
        "currency": a.currency, "fee": f"{a.fee:.2f}" if a.fee is not None else "",
        "payment_basis": a.payment_basis, "payment_basis_other": a.payment_basis_other,
        "deposit": f"{a.deposit:.2f}" if a.deposit else "",
        "payment_schedule": a.payment_schedule, "deliverables": a.deliverable_list(),
    }


def _balance_display(values):
    """Balance due for the form's first paint, so it's right before (and
    without) the page's script; psa-form.js keeps it current after that."""
    from .forms import _money
    fee, deposit = _money(values.get("fee")), _money(values.get("deposit"))
    if not fee or deposit is False:
        return ""
    deposit = deposit or 0
    if deposit > fee:
        return "Deposit is more than the fee"
    return f"{values.get('currency') or 'GHS'} {fee - deposit:,.2f}"


def _form(request, a, values, errors=None, status=200):
    return render(request, "psa/admin_form.html", {
        "a": a,
        "v": values,
        "balance": _balance_display(values),
        "open_request": a.open_change_request if a and a.status == Status.CHANGES else None,
        "errors": errors or {},
        "currencies": CURRENCIES,
        "bases": ServiceAgreement.Basis.choices,
        "signer_name": request.user.full_name,
        "signer_role": _role_label(request.user),
        "today": timezone.localdate(),
        "dashboard": _dashboard(request),
    }, status=status)


@login_required
@staff_required
def psa_new(request):
    if request.method == "POST":
        return _save(request, None)
    return _form(request, None, {
        "agreement_date": timezone.localdate().isoformat(), "currency": "GHS", "deliverables": [],
    })


@login_required
@staff_required
def psa_edit(request, pk):
    a = get_object_or_404(ServiceAgreement, pk=pk)
    if not a.is_editable:
        messages.error(request, f"{a.reference} is {a.get_status_display().lower()} and can no longer be changed.")
        return redirect("psa_admin:psa_detail", pk=a.pk)
    if request.method == "POST":
        return _save(request, a)
    return _form(request, a, _values_from(a))


def _save(request, a):
    sending = request.POST.get("action") == "send"
    # What staff wrote back to the client about their requested changes.
    note = request.POST.get("client_note", "").strip()[:2000]
    cleaned, errors = parse_agreement(request.POST, sending=sending)

    kind, signature, sig_error = parse_signature(request.POST, "company")
    has_signature = bool(signature) or bool(a and a.is_company_signed)
    if sig_error:
        errors["company_signature"] = sig_error
    elif sending and not has_signature:
        errors["company_signature"] = "Sign for Metascholar Limited before sending."

    if errors:
        values = {k: request.POST.get(k, "") for k in FORM_FIELDS}
        values["deliverables"] = cleaned["deliverables"]
        values["client_note"] = note
        messages.error(request, "Please fix the highlighted fields." if len(errors) > 1 else next(iter(errors.values())))
        return _form(request, a, values, errors, status=400)

    creating = a is None
    unseen_request = False
    with transaction.atomic():
        if creating:
            a = ServiceAgreement(created_by=request.user)
        else:
            # Re-read under a lock: the client may have signed while this
            # form was open, and a signed agreement must not change.
            a = ServiceAgreement.objects.select_for_update().get(pk=a.pk)
            if not a.is_editable:
                messages.error(request, f"{a.reference} was {a.get_status_display().lower()} in the meantime, so your changes weren't saved.")
                return redirect("psa_admin:psa_detail", pk=a.pk)
            # The client asked for changes after this form was opened: keep
            # the edits, but don't send -- that would close a request this
            # person hasn't read.
            unseen_request = (
                sending and a.status == Status.CHANGES
                and request.POST.get("seen_status") != Status.CHANGES
            )
        for field, value in cleaned.items():
            setattr(a, field, value)
        if signature:
            # The company's side is filled in automatically: whoever signs,
            # in their role, today.
            a.company_signature_kind = kind
            a.company_signature = signature
            a.company_signatory_name = request.user.full_name
            a.company_signatory_role = _role_label(request.user)
            a.company_signed_by = request.user
            a.company_signed_at = timezone.now()
        a.save()

    if unseen_request:
        messages.warning(
            request,
            f"Your changes are saved, but {a.client_name} asked for changes while you were editing, "
            "so nothing was sent. Read their request below, then send it back when it's ready.",
        )
        return redirect("psa_admin:psa_edit", pk=a.pk)
    if not sending:
        messages.success(request, f"{a.reference} {'saved as a draft' if creating or a.status == Status.DRAFT else 'updated'}.")
        if a.status == Status.SENT:
            messages.info(request, "The client's link already shows these changes. Use Resend if you'd like them to get a fresh email.")
        elif a.status == Status.CHANGES:
            messages.info(request, "The client can't sign until you send it back to them.")
        return redirect("psa_admin:psa_detail", pk=a.pk)
    return _send(request, a, reminder=False, note=note)


def _send(request, a, *, reminder, note=""):
    """Email the client their link and mark the agreement as with them.
    Going back after a change request closes that request, recording what
    staff replied."""
    now = timezone.now()
    with transaction.atomic():
        a = ServiceAgreement.objects.select_for_update().get(pk=a.pk)
        updated = a.status == Status.CHANGES
        if updated:
            a.change_requests.filter(resolved_at__isnull=True).update(
                resolved_at=now, resolved_by=request.user, response=note,
            )
        a.status = Status.SENT
        a.sent_at = a.sent_at or now
        a.last_sent_at = now
        a.send_count += 1
        a.save(update_fields=["status", "sent_at", "last_sent_at", "send_count", "updated_at"])
    # Emailed once the link is live again, so the client can sign straight away.
    ok = emails.send_to_client(a, reminder=reminder, updated=updated, note=note)
    if ok:
        verb = "sent back" if updated else ("resent" if reminder else "sent")
        messages.success(request, f"{a.reference} {verb} to {a.client_email}.")
    else:
        messages.warning(
            request,
            f"{a.reference} is ready for the client, but the email to {a.client_email} couldn't be sent. "
            "Check the email settings, or copy the client link below and share it directly.",
        )
    return redirect("psa_admin:psa_detail", pk=a.pk)


# ---------------------------------------------------------------------
# One agreement + actions
# ---------------------------------------------------------------------

@login_required
@staff_required
def psa_detail(request, pk):
    a = get_object_or_404(ServiceAgreement.objects.select_related("created_by", "company_signed_by"), pk=pk)
    change_requests = list(a.change_requests.select_related("resolved_by"))
    return render(request, "psa/admin_detail.html", {
        "a": a,
        "open_request": next((r for r in change_requests if not r.resolved_at), None),
        "change_requests": change_requests,
        "payments": list(a.payments.select_related("recorded_by")),
        "methods": Payment.Method.choices,
        "today": timezone.localdate(),
        "client_link": a.client_url() if a.status != Status.DRAFT else "",
        "dashboard": _dashboard(request),
    })


# ---------------------------------------------------------------------
# Payments received (the ledger)
# ---------------------------------------------------------------------

def _back(request, a):
    """Where the payment dialog was opened from -- the list (keeping its
    filters and page) or the agreement itself."""
    target = request.POST.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
            target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(target)
    return redirect("psa_admin:psa_detail", pk=a.pk)


# A second identical entry this soon after the first is a double-submit,
# not a second payment -- and a wrong entry can't be taken back.
DUPLICATE_WINDOW = timedelta(minutes=2)


@login_required
@staff_required
@require_POST
def psa_payment_add(request, pk):
    """Record money received against an agreement, or given back.

    Written once: there is no edit or delete for an entry, so everything
    is checked before it goes in and a mistake is corrected by a further
    entry (see psa.models.Payment).
    """
    a = get_object_or_404(ServiceAgreement, pk=pk)
    if not a.can_record_payment:
        messages.error(request, f"{a.reference} has no agreed fee yet, so there's nothing to record against it.")
        return _back(request, a)

    with transaction.atomic():
        # Locked while the refund and total are worked out, so two people
        # recording at once can't both be measured against the same total.
        a = ServiceAgreement.objects.select_for_update().get(pk=a.pk)
        cleaned, errors = parse_payment(request.POST, a)
        if errors:
            messages.error(request, next(iter(errors.values())))
            return _back(request, a)

        twin = a.payments.filter(
            amount=cleaned["amount"], paid_on=cleaned["paid_on"], method=cleaned["method"],
            note=cleaned["note"], recorded_at__gte=timezone.now() - DUPLICATE_WINDOW,
        ).first()
        if twin:
            messages.warning(request, (
                f"That entry is already on {a.reference} — recorded a moment ago, so nothing was added twice. "
                "If it really is a second payment of the same amount, add a note that tells them apart."
            ))
            return _back(request, a)

        payment = Payment.objects.create(agreement=a, recorded_by=request.user, **cleaned)
        a.save(update_fields=["updated_at"])   # the list's "last touched"
        owing, paid = a.amount_owing, a.amount_paid

    if payment.is_refund:
        messages.success(request, f"{a.currency} {payment.abs_amount:,.2f} refunded on {a.reference} recorded.")
    else:
        messages.success(request, f"{a.currency} {payment.amount:,.2f} received on {a.reference} recorded.")
    if owing is not None and owing <= 0:
        messages.info(request, (
            f"{a.reference} is paid in full ({a.currency} {paid:,.2f} of {a.currency} {a.fee:,.2f})."
            if owing == 0 else
            f"{a.reference} is now overpaid by {a.currency} {-owing:,.2f}. "
            "Record a refund if the difference goes back to the client."
        ))
    else:
        messages.info(request, f"{a.currency} {owing:,.2f} still owing on {a.reference}.")
    return _back(request, a)


@login_required
@staff_required
@require_POST
def psa_resend(request, pk):
    a = get_object_or_404(ServiceAgreement, pk=pk)
    if a.status != Status.SENT:
        messages.error(request, "Only an agreement awaiting the client can be resent.")
        return redirect("psa_admin:psa_detail", pk=a.pk)
    return _send(request, a, reminder=True)


@login_required
@staff_required
@require_POST
def psa_send(request, pk):
    """Send from the agreement's own page: a finished draft, or one the
    client asked to change, sent back as it stands with a reply (the form's
    "Save & send" does the same after editing)."""
    a = get_object_or_404(ServiceAgreement, pk=pk)
    if a.status not in (Status.DRAFT, Status.CHANGES):
        return redirect("psa_admin:psa_detail", pk=a.pk)
    missing = parse_agreement(_as_post(a), sending=True)[1]
    if missing or not a.is_company_signed:
        messages.error(request, "Finish the agreement and sign it for Metascholar Limited before sending.")
        return redirect("psa_admin:psa_edit", pk=a.pk)
    note = request.POST.get("client_note", "").strip()[:2000]
    if a.status == Status.CHANGES and not note:
        messages.error(request, "Tell the client why the agreement stands as it is before sending it back unchanged.")
        return redirect("psa_admin:psa_detail", pk=a.pk)
    return _send(request, a, reminder=False, note=note)


def _as_post(a):
    from django.http import QueryDict
    q = QueryDict(mutable=True)
    for k, v in _values_from(a).items():
        if k == "deliverables":
            q.setlist(k, v)
        else:
            q[k] = v
    return q


@login_required
@staff_required
@require_POST
def psa_cancel(request, pk):
    with transaction.atomic():
        a = get_object_or_404(ServiceAgreement.objects.select_for_update(), pk=pk)
        if not a.is_editable:
            messages.error(request, f"{a.reference} is {a.get_status_display().lower()} and can't be cancelled.")
            return redirect("psa_admin:psa_detail", pk=a.pk)
        a.status = Status.CANCELLED
        a.cancelled_at = timezone.now()
        a.save(update_fields=["status", "cancelled_at", "updated_at"])
    messages.success(request, f"{a.reference} cancelled. The client's link no longer accepts a signature.")
    return redirect("psa_admin:psa_detail", pk=a.pk)


@login_required
@staff_required
@require_POST
def psa_delete(request, pk):
    a = get_object_or_404(ServiceAgreement, pk=pk)
    if a.status not in (Status.DRAFT, Status.CANCELLED):
        messages.error(request, "Only drafts and cancelled agreements can be deleted. Signed agreements are kept as records.")
        return redirect("psa_admin:psa_detail", pk=a.pk)
    ref = a.reference
    a.delete()
    messages.success(request, f"{ref} deleted.")
    return redirect("psa_admin:psa_list")


# ---------------------------------------------------------------------
# Client side
# ---------------------------------------------------------------------

def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    raw = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def _client_page(request, a, *, values=None, errors=None, change_values=None,
                 change_errors=None, status=200):
    resp = render(request, "psa/client.html", {
        "a": a,
        "v": values or {
            "client_name": a.client_name, "client_phone": a.client_phone,
            "client_address": a.client_address,
        },
        "errors": errors or {},
        "sections": ChangeRequest.Section.choices,
        "cv": change_values or {},
        "change_errors": change_errors or {},
        "open_request": a.open_change_request if a.status == Status.CHANGES else None,
        # Back from a change request: what they asked and what we replied.
        "last_reply": (
            a.change_requests.filter(resolved_at__isnull=False).first()
            if a.status == Status.SENT else None
        ),
    }, status=status)
    # The link is the key to the agreement: keep it out of caches and out
    # of the Referer sent to any third-party asset.
    resp["Cache-Control"] = "no-store"
    resp["Referrer-Policy"] = "same-origin"
    resp["X-Robots-Tag"] = "noindex, nofollow"
    return resp


def client(request, token):
    a = get_object_or_404(ServiceAgreement, token=token)
    if a.status == Status.DRAFT:
        raise Http404("No agreement at this link.")

    if request.method == "POST":
        with transaction.atomic():
            a = ServiceAgreement.objects.select_for_update().get(pk=a.pk)
            if a.status != Status.SENT:
                # Already signed (a double-click or a second tab), or
                # withdrawn while the page was open.
                return redirect("psa:client", token=a.token)
            cleaned, errors = parse_client(request.POST)
            if errors:
                return _client_page(request, a, values=request.POST, errors=errors, status=400)
            for field, value in cleaned.items():
                setattr(a, field, value)
            a.status = Status.SIGNED
            a.client_signed_at = timezone.now()
            a.client_signed_ip = _client_ip(request)
            a.client_user_agent = request.META.get("HTTP_USER_AGENT", "")[:300]
            a.save()

        # Built once, attached to both emails.
        attachment = emails.signed_pdf(a)
        emails.send_client_copy(a, attachment)
        emails.send_signed_to_staff(a, attachment)
        _notify_staff(a, f"{a.client_name} signed service agreement {a.reference}.", icon="success")
        messages.success(request, "Thank you — the agreement is signed. We've emailed you a copy.")
        return redirect("psa:client", token=a.token)

    if a.status == Status.SENT and not a.viewed_at:
        a.viewed_at = timezone.now()
        a.save(update_fields=["viewed_at"])
    return _client_page(request, a)


@require_POST
def client_request_changes(request, token):
    """The client flags something to fix instead of signing. Signing locks
    until staff send the agreement back."""
    a = get_object_or_404(ServiceAgreement, token=token)
    if a.status == Status.DRAFT:
        raise Http404("No agreement at this link.")
    with transaction.atomic():
        a = ServiceAgreement.objects.select_for_update().get(pk=a.pk)
        if a.status != Status.SENT:
            # Already signed, already flagged (a second tab), or withdrawn.
            return redirect("psa:client", token=a.token)
        data, errors = parse_change_request(request.POST)
        if errors:
            return _client_page(request, a, change_values=data, change_errors=errors, status=400)
        req = ChangeRequest.objects.create(agreement=a, client_ip=_client_ip(request), **data)
        a.status = Status.CHANGES
        a.save(update_fields=["status", "updated_at"])

    emails.send_changes_requested_to_staff(a, req)
    emails.send_change_request_receipt(a, req)
    _notify_staff(a, f"{a.client_name} asked for changes to service agreement {a.reference}.", icon="warn")
    messages.success(
        request,
        "Thank you — your request has been sent to Metascholar Limited. "
        "We'll email you as soon as the updated agreement is ready to sign.",
    )
    return redirect("psa:client", token=a.token)


def _notify_staff(a, message, *, icon):
    """A dashboard notification for Admin and the Secretariat. Best effort."""
    try:
        from notifications.models import Notification
        from notifications.services import notify
        notify(
            Notification.Audience.SECRETARIAT, message[:255], icon=icon,
            link_url_name="psa_admin:psa_detail", link_kwargs={"pk": a.pk},
        )
    except Exception:
        logger.exception("PSA notification failed for %s", a.reference)


# ---------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------

def _pdf_response(a, *, inline=False):
    from . import pdf
    resp = HttpResponse(pdf.render(a), content_type="application/pdf")
    disposition = "inline" if inline else "attachment"
    resp["Content-Disposition"] = f'{disposition}; filename="{pdf.filename(a)}"'
    resp["Cache-Control"] = "no-store"
    return resp


@login_required
@staff_required
def psa_pdf(request, pk):
    """The agreement as a PDF (?inline=1 to open it in the browser)."""
    a = get_object_or_404(ServiceAgreement, pk=pk)
    return _pdf_response(a, inline=request.GET.get("inline") == "1")


PDF_ZIP_LIMIT = 200


@login_required
@staff_required
def psa_pdf_zip(request):
    """Every signed agreement matching the list's filters, as PDFs in one
    .zip -- the clients' signed responses, ready to file."""
    import zipfile
    from io import BytesIO

    from . import pdf
    from .models import PsaSettings

    back = reverse("psa_admin:psa_list") + (f"?{request.GET.urlencode()}" if request.GET else "")
    signed = list(_filtered(_filters(request.GET)).filter(status=Status.SIGNED)[:PDF_ZIP_LIMIT + 1])
    if not signed:
        messages.error(request, "None of the agreements matching these filters have been signed yet.")
        return redirect(back)
    if len(signed) > PDF_ZIP_LIMIT:
        messages.error(request, f"That's more than {PDF_ZIP_LIMIT} signed agreements. Narrow the filters "
                                "(for example by agreement date) and download them in batches.")
        return redirect(back)

    letterhead_settings = PsaSettings.get_solo()   # read once for the whole batch
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for a in signed:
            zf.writestr(pdf.filename(a), pdf.render(a, letterhead_settings))
    resp = HttpResponse(buffer.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = (
        f'attachment; filename="metascholar-signed-agreements-{timezone.localdate().isoformat()}.zip"'
    )
    return resp


def client_pdf(request, token):
    """The client's own copy, once both parties have signed."""
    a = get_object_or_404(ServiceAgreement, token=token)
    if a.status != Status.SIGNED:
        raise Http404("The PDF is available once the agreement is signed.")
    resp = _pdf_response(a)
    resp["X-Robots-Tag"] = "noindex, nofollow"
    return resp


# ---------------------------------------------------------------------
# Letterhead (PSA > Letterhead)
# ---------------------------------------------------------------------

@login_required
@staff_required
def psa_letterhead(request):
    from . import letterhead, pdf
    from .models import PsaSettings

    s = PsaSettings.get_solo()
    if request.method == "POST":
        kind = request.POST.get("kind")
        if kind not in ("header", "footer"):
            messages.error(request, "That request couldn't be processed.")
            return redirect("psa_admin:psa_letterhead")
        if request.POST.get("action") == "remove":
            setattr(s, f"{kind}_image", None)
            setattr(s, f"{kind}_type", "")
            setattr(s, f"{kind}_width", 0)
            setattr(s, f"{kind}_height", 0)
            s.updated_by = request.user
            s.save()
            messages.success(request, f"Letterhead {kind} removed. Agreement PDFs use the plain {kind} again.")
            return redirect("psa_admin:psa_letterhead")

        upload = request.FILES.get("image")
        if not upload:
            messages.error(request, f"Choose an image for the {kind}.")
            return redirect("psa_admin:psa_letterhead")
        if upload.size > letterhead.MAX_UPLOAD:
            messages.error(request, "That image is too large. Keep it under 12 MB.")
            return redirect("psa_admin:psa_letterhead")
        try:
            data, content_type, width, height = letterhead.process(upload.read(), kind)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("psa_admin:psa_letterhead")
        setattr(s, f"{kind}_image", data)
        setattr(s, f"{kind}_type", content_type)
        setattr(s, f"{kind}_width", width)
        setattr(s, f"{kind}_height", height)
        s.updated_by = request.user
        s.save()
        w_mm, h_mm, full = letterhead.printed_size(width, height, kind)
        note = (f"It prints across the full page width, {h_mm} mm tall." if full else
                f"It's taller than the {letterhead.LIMIT_MM[kind]:.0f} mm allowed for a {kind}, so it prints "
                f"scaled down to {w_mm} × {h_mm} mm, centred.")
        messages.success(request, f"Letterhead {kind} saved ({width} × {height} px). {note}")
        if width < letterhead.SHARP_WIDTH:
            messages.warning(request, f"At {width} px wide it may look slightly soft in print. "
                                      f"Artwork {letterhead.MAX_WIDTH} px wide prints sharpest.")
        return redirect("psa_admin:psa_letterhead")

    header, footer = pdf.letterhead(s)
    top, _, bottom = pdf.frame_bounds(header, footer)
    page_w_mm, page_h_mm = pdf.PAGE_W / pdf.mm, pdf.PAGE_H / pdf.mm
    parts = {}
    for kind in ("header", "footer"):
        width, height = getattr(s, f"{kind}_width"), getattr(s, f"{kind}_height")
        size = letterhead.printed_size(width, height, kind) if getattr(s, f"{kind}_image") else None
        parts[kind] = {
            "set": bool(size),
            "width": width, "height": height, "mm": size,
            # Where it sits on the A4 preview, as % of the page.
            "pct_h": round(100 * size[1] / page_h_mm, 3) if size else 0,
            "pct_w": round(100 * size[0] / page_w_mm, 3) if size else 0,
            "limit_mm": round(letterhead.LIMIT_MM[kind]),
            "ideal_px": round(letterhead.MAX_WIDTH * letterhead.LIMIT_MM[kind] / page_w_mm),
            "soft": bool(size) and width < letterhead.SHARP_WIDTH,
        }
    return render(request, "psa/admin_letterhead.html", {
        "s": s,
        "parts": parts,
        "text_top_pct": round(100 * (top / pdf.mm) / page_h_mm, 3),
        "text_bottom_pct": round(100 * (bottom / pdf.mm) / page_h_mm, 3),
        "text_top_mm": round(top / pdf.mm, 1), "text_bottom_mm": round(bottom / pdf.mm, 1),
        "dashboard": _dashboard(request),
    })


@login_required
@staff_required
def psa_letterhead_image(request, kind):
    from .models import PsaSettings
    if kind not in ("header", "footer"):
        raise Http404
    s = PsaSettings.get_solo()
    data = s.image(kind)
    if not data:
        raise Http404
    resp = HttpResponse(data, content_type=getattr(s, f"{kind}_type") or "image/png")
    resp["Cache-Control"] = "private, no-cache"
    return resp


@login_required
@staff_required
def psa_letterhead_preview(request):
    """A sample agreement printed with the current letterhead."""
    from . import pdf
    resp = HttpResponse(pdf.render(pdf.sample_agreement()), content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="letterhead-preview.pdf"'
    resp["Cache-Control"] = "no-store"
    return resp


# ---------------------------------------------------------------------
# Payment links
# ---------------------------------------------------------------------
#
# What makes a link safe to email:
#
#   * The URL is the secret. `token` is 32 random bytes, so the page
#     cannot be reached by guessing or by walking primary keys, and it is
#     served no-store with a same-origin referrer so it stays out of
#     caches and out of any third party's logs.
#   * The amount is read from the PaymentRequest row on every request.
#     The browser never says what to charge, so a tampered form or a
#     doctored popup cannot change the figure.
#   * Only Paystack's own servers, asked with the secret key, can turn a
#     request into money (_finalise below). The browser's "it worked"
#     callback is a prompt to go and check, never evidence.
#   * The ledger entry is written once, under a row lock, so a retried
#     verify -- a double click, a second tab -- cannot bank the same
#     charge twice.

def _checkout_params(req):
    """What the Paystack popup is opened with. Every value comes from the
    request row on the server, none from the page."""
    from pages.models import SiteSettings
    a = req.agreement
    return {
        "key": SiteSettings.get_solo().effective_paystack_public_key,
        "email": a.client_email,
        "amount": req.amount_subunit,
        "currency": req.currency,
        "reference": req.reference,
        "name": a.client_name,
        "agreement": a.reference or "",
        "verify_url": reverse("psa:pay_verify", kwargs={"token": req.token}),
    }


@login_required
@staff_required
@require_POST
def psa_payment_link(request, pk):
    """Create a payment link for what is still owing and email it to the
    client, with its SMS twin.

    Asking for a new link retires whatever was already out, so a client
    is never holding two live links for one balance and cannot pay it
    twice."""
    a = get_object_or_404(ServiceAgreement, pk=pk)
    with transaction.atomic():
        a = ServiceAgreement.objects.select_for_update().get(pk=a.pk)
        cleaned, errors = parse_payment_request(request.POST, a)
        if errors:
            messages.error(request, next(iter(errors.values())))
            return _back(request, a)
        now = timezone.now()
        a.payment_requests.filter(status=PaymentRequest.Status.PENDING).update(
            status=PaymentRequest.Status.CANCELLED, cancelled_at=now, cancelled_by=request.user,
        )
        req = PaymentRequest.objects.create(agreement=a, created_by=request.user, **cleaned)
        req.sent_at = req.last_sent_at = now
        req.send_count = 1
        req.save(update_fields=["sent_at", "last_sent_at", "send_count"])

    if emails.send_payment_link(a, req):
        messages.success(
            request,
            f"Payment link for {a.currency} {req.amount:,.2f} sent to {a.client_email}. "
            f"It stops working on {timezone.localtime(req.expires_at):%d %b %Y}.",
        )
    else:
        messages.warning(
            request,
            f"The payment link was created, but the email to {a.client_email} couldn't be sent. "
            "Use Resend on the agreement, or copy the link and send it yourself.",
        )
    return _back(request, a)


@login_required
@staff_required
@require_POST
def psa_payment_link_resend(request, pk, req_pk):
    """Send the live link again as a reminder -- email and text both --
    and push its expiry back, so chasing an old debt doesn't mint a new
    link the client has to be told about separately."""
    a = get_object_or_404(ServiceAgreement, pk=pk)
    req = get_object_or_404(PaymentRequest, pk=req_pk, agreement=a)
    if req.status != PaymentRequest.Status.PENDING:
        messages.error(request, f"That payment link is {req.state_label.lower()}, so it can't be resent.")
        return _back(request, a)
    owing = a.amount_owing
    if owing is None or owing <= 0:
        messages.error(request, f"{a.reference} has nothing outstanding, so there's nothing to chase.")
        return _back(request, a)

    now = timezone.now()
    req.last_sent_at = now
    req.sent_at = req.sent_at or now
    req.send_count += 1
    req.expires_at = now + PaymentRequest.VALID_FOR
    req.save(update_fields=["last_sent_at", "sent_at", "send_count", "expires_at"])

    if emails.send_payment_link(a, req, reminder=True):
        texted = " and texted to the client" if a.client_phone else ""
        messages.success(
            request,
            f"Reminder emailed to {a.client_email}{texted}. "
            f"The link now runs to {timezone.localtime(req.expires_at):%d %b %Y}.",
        )
    else:
        messages.warning(request, f"The reminder to {a.client_email} couldn't be sent. Check the email settings.")
    return _back(request, a)


@login_required
@staff_required
@require_POST
def psa_payment_link_cancel(request, pk, req_pk):
    """Withdraw a link sent in error. The URL stops taking money at once."""
    a = get_object_or_404(ServiceAgreement, pk=pk)
    req = get_object_or_404(PaymentRequest, pk=req_pk, agreement=a)
    if req.status != PaymentRequest.Status.PENDING:
        messages.error(request, f"That payment link is already {req.state_label.lower()}.")
        return _back(request, a)
    req.status = PaymentRequest.Status.CANCELLED
    req.cancelled_at = timezone.now()
    req.cancelled_by = request.user
    req.save(update_fields=["status", "cancelled_at", "cancelled_by"])
    messages.success(request, "That payment link has been withdrawn - it no longer takes payment.")
    return _back(request, a)


@login_required
@staff_required
def psa_receipt(request, pk, payment_pk):
    """A receipt for one entry in the ledger, for staff to file or resend."""
    a = get_object_or_404(ServiceAgreement, pk=pk)
    payment = get_object_or_404(Payment, pk=payment_pk, agreement=a)
    if payment.amount <= 0:
        messages.error(request, "That entry is a refund, so there's no receipt to issue for it.")
        return _back(request, a)
    return _receipt_response(payment, inline=request.GET.get("inline") == "1")


def _receipt_response(payment, *, inline=False):
    from . import receipt
    resp = HttpResponse(receipt.render(payment), content_type="application/pdf")
    disposition = "inline" if inline else "attachment"
    resp["Content-Disposition"] = f'{disposition}; filename="{receipt.filename(payment)}"'
    resp["Cache-Control"] = "no-store"
    return resp


# ---- the client's side ----------------------------------------------

def _no_store(resp):
    """The link is the key to the page: keep it out of caches and out of
    the Referer sent to any third-party asset."""
    resp["Cache-Control"] = "no-store"
    resp["Referrer-Policy"] = "same-origin"
    return resp


def pay(request, token):
    """The client's payment page, reached only by the emailed link."""
    req = get_object_or_404(
        PaymentRequest.objects.select_related("agreement", "payment"), token=token,
    )
    a = req.agreement
    if req.viewed_at is None and req.status == PaymentRequest.Status.PENDING:
        PaymentRequest.objects.filter(pk=req.pk, viewed_at__isnull=True).update(viewed_at=timezone.now())

    return _no_store(render(request, "psa/pay.html", {
        "req": req,
        "a": a,
        "payable": req.is_payable,
        # Why it can't be paid, in the client's terms -- never a dead end
        # without a reason.
        "blocked": _why_not_payable(req, a),
        "checkout": _checkout_params(req) if req.is_payable else None,
        "receipt": req.payment if req.is_paid else None,
    }))


def _why_not_payable(req, a):
    if req.is_payable:
        return ""
    if req.status == PaymentRequest.Status.PAID:
        return "paid"
    if req.status == PaymentRequest.Status.CANCELLED:
        return "cancelled"
    if req.is_expired:
        return "expired"
    if a.status == Status.CANCELLED:
        return "agreement_cancelled"
    owing = a.amount_owing
    if owing is not None and owing <= 0:
        return "settled"
    return "unavailable"


@require_POST
def pay_verify(request, token):
    """Asks Paystack's own servers whether this charge really happened,
    and banks it if so. Called by the page once the popup closes, and
    safe to call again: a request already paid just answers yes."""
    req = get_object_or_404(PaymentRequest.objects.select_related("agreement"), token=token)
    done = JsonResponse({"ok": True, "redirect": reverse("psa:pay", kwargs={"token": req.token})})
    if req.status == PaymentRequest.Status.PAID:
        return done
    if not req.is_payable:
        return JsonResponse({"ok": False, "error": "This payment link is no longer active."}, status=400)

    # The reference is ours, minted before Paystack was ever contacted, so
    # a browser quoting a different one is not talking about this charge.
    quoted = request.POST.get("reference", "").strip()
    if quoted and quoted != req.reference:
        return JsonResponse({"ok": False, "error": "Payment reference mismatch."}, status=400)

    from payments import paystack
    try:
        data = paystack.verify_transaction(req.reference)
    except paystack.PaystackError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    amount_ok = int(data.get("amount") or 0) == req.amount_subunit
    currency_ok = (data.get("currency") or "").upper() == req.currency.upper()
    if data.get("status") != "success" or not amount_ok or not currency_ok:
        req.paystack_response = data
        req.save(update_fields=["paystack_response"])
        if data.get("status") == "success":
            logger.error(
                "PSA payment %s verified as success but for %s %s, not the expected %s %s",
                req.reference, data.get("currency"), data.get("amount"), req.currency, req.amount_subunit,
            )
            reason = ("The amount received didn't match the amount requested, so it hasn't been "
                      "applied. Please contact Metascholar Limited - no further charge will be made.")
        else:
            reason = data.get("gateway_response") or "Payment was not successful. Please try again."
        return JsonResponse({"ok": False, "error": reason}, status=400)

    payment = _finalise(req, data)
    if payment is not None:
        _after_payment(req.agreement, payment, req)
    return done


def _finalise(req, data):
    """Turn a verified charge into a ledger entry, exactly once.

    The PENDING -> PAID flip is claimed under a row lock, so when the
    page's verify and a retry arrive together only one of them writes the
    money. Returns the new Payment, or None if someone else got there
    first -- that caller sends the receipt."""
    with transaction.atomic():
        locked = PaymentRequest.objects.select_for_update().select_related("agreement").get(pk=req.pk)
        if locked.status == PaymentRequest.Status.PAID:
            return None
        a = locked.agreement
        payment = Payment.objects.create(
            agreement=a,
            amount=locked.amount,
            paid_on=timezone.localdate(),
            method=Payment.Method.CARD,
            note=(locked.note or "Paid online")[:200],
        )
        locked.status = PaymentRequest.Status.PAID
        locked.paid_at = timezone.now()
        locked.paystack_response = data
        locked.payment = payment
        locked.save(update_fields=["status", "paid_at", "paystack_response", "payment"])
        # The list's "last touched", so a payment moves the agreement up it.
        a.save(update_fields=["updated_at"])
    req.status = PaymentRequest.Status.PAID
    req.paid_at = locked.paid_at
    req.payment = payment
    return payment


def _after_payment(a, payment, req):
    """Receipt to the client, word to the staff, a note on the dashboard.
    None of it is allowed to lose a payment already banked, so each part
    fails on its own."""
    a.refresh_from_db()
    try:
        from . import receipt as receipt_pdf
        attachment = (receipt_pdf.filename(payment), receipt_pdf.render(payment), "application/pdf")
    except Exception:
        logger.exception("PSA receipt for %s couldn't be built", payment.receipt_number)
        attachment = None
    try:
        emails.send_receipt(a, payment, attachment)
    except Exception:
        logger.exception("PSA receipt email failed for %s", req.reference)
    try:
        emails.send_payment_to_staff(a, payment, req)
    except Exception:
        logger.exception("PSA payment staff email failed for %s", req.reference)
    _notify_staff(a, f"{a.client_name} paid {a.currency} {payment.abs_amount:,.2f} on {a.reference}",
                  icon="credit-card")


def pay_receipt(request, token):
    """The client's own copy of their receipt, from the payment page."""
    req = get_object_or_404(PaymentRequest.objects.select_related("payment", "agreement"), token=token)
    if not req.is_paid or req.payment is None:
        raise Http404("No receipt at this link yet.")
    return _no_store(_receipt_response(req.payment, inline=request.GET.get("inline") == "1"))
