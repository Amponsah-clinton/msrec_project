"""The admin Finance page's income, grouped by where it comes from.

Two streams, never mixed in one list:
  * Ethics applications -- review fees (payments.Payment), grouped by the
    fee that was charged: the same categories as the Fee Schedule
    (Undergraduate / Diploma Student Research, PhD, Ghanaian Independent ...);
  * Workshops -- certificate fees, which live on
    workshop.WorkshopRegistration rather than in Payment, grouped by the
    workshop they were paid for.

`breakdown()` is the grouped summary (counts, collected and outstanding per
group, per stream, and overall); `Ledger` is one stream's list, optionally
narrowed to one review type or one workshop, with every row tagged with its
group so the table can show a header and subtotal over each group.

Workshop income is a registration that was actually charged: a certificate
was wanted and a fee applied (amount > 0; pending / success / failed). Free
certificates and opted-out registrations are not income.

Money is always kept per currency -- a workshop priced in USD is shown
beside the cedi total, never silently added into it.
"""
import csv
from collections import OrderedDict
from decimal import Decimal
from types import SimpleNamespace

from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone

from .models import Payment

SOURCES = ("applications", "workshops")
STATUSES = ("success", "pending", "failed")
STATUS_LABELS = {"success": "Successful", "pending": "Pending", "failed": "Failed"}


# ---------------------------------------------------------------------
# Money helpers
# ---------------------------------------------------------------------

def money(totals):
    """{"GHS": Decimal, ...} -> [("GHS", Decimal), ...]: GHS first, zeros dropped."""
    items = [(c, a) for c, a in totals.items() if a]
    items.sort(key=lambda item: (item[0] != "GHS", item[0]))
    return items


def _add(bucket, currency, amount):
    currency = currency or "GHS"
    bucket[currency] = bucket.get(currency, Decimal("0")) + (amount or Decimal("0"))


def _new_group(key, label, **extra):
    return SimpleNamespace(
        key=key, label=label, paid=0, pending=0, failed=0,
        collected={}, outstanding={}, **extra,
    )


def _finish(group):
    group.count = group.paid + group.pending + group.failed
    group.collected = money(group.collected)
    group.outstanding = money(group.outstanding)
    return group


def _roll_up(groups, key, label, **extra):
    total = _new_group(key, label, **extra)
    for g in groups:
        total.paid += g.paid
        total.pending += g.pending
        total.failed += g.failed
        for cur, amt in g.collected:
            _add(total.collected, cur, amt)
        for cur, amt in g.outstanding:
            _add(total.outstanding, cur, amt)
    return _finish(total)


# ---------------------------------------------------------------------
# The two streams, filtered by the page's search + date range
# ---------------------------------------------------------------------

def application_payments(*, query="", date_from=None, date_to=None):
    from . import services

    return services.filter_payments(
        services.all_payments(), query=query, date_from=date_from, date_to=date_to)


def workshop_charges(*, query="", date_from=None, date_to=None):
    from workshop.models import WorkshopRegistration

    qs = (
        WorkshopRegistration.objects.select_related("workshop")
        .filter(wants_certificate=True, amount__gt=0, payment_status__in=STATUSES)
    )
    query = (query or "").strip()
    if query:
        qs = qs.filter(
            Q(name__icontains=query) | Q(email__icontains=query)
            | Q(payment_reference__icontains=query) | Q(workshop__title__icontains=query)
        )
    # Dates on when they registered -- application payments filter on
    # created_at the same way (see payments.services.filter_payments).
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    return qs


def fee_key(purpose, review_type="", category=""):
    """Which Fee Schedule entry a payment was charged under. Checkout
    (services.start_checkout) writes the purpose as "<fee label> fee", so
    that is the most faithful record of what was charged -- the price
    follows the applicant category, not the review pathway. Falls back to
    the application's category, then the stored review type."""
    from . import fees

    label = (purpose or "").strip()
    if label.lower().endswith(" fee"):
        label = label[:-4].strip()
    for key, known in fees.ALL_LABELS.items():
        if known.lower() == label.lower():
            return key
    return category or review_type or ""


def fee_label(key):
    from . import fees

    return fees.ALL_LABELS.get(key, key) if key else "Other application fees"


def _keyed_payments(payments):
    """[(fee key, Payment), ...] for a Payment queryset."""
    qs = payments.select_related("applicant", "application")
    return [
        (fee_key(p.purpose, p.review_type, getattr(p.application, "applicant_category", "") if p.application else ""), p)
        for p in qs
    ]


# ---------------------------------------------------------------------
# Grouped summary
# ---------------------------------------------------------------------

def _tally(groups, key, status, currency, n, amount, make):
    group = groups.get(key) or groups.setdefault(key, make())
    if status == "success":
        group.paid += n
        _add(group.collected, currency, amount)
    else:
        if status == "pending":
            group.pending += n
        else:
            group.failed += n
        _add(group.outstanding, currency, amount)


def application_groups(payments, keyed=None):
    groups = OrderedDict()
    for key, p in (keyed if keyed is not None else _keyed_payments(payments)):
        _tally(groups, key, p.status, p.currency, 1, p.amount,
               lambda key=key: _new_group(key, fee_label(key), fee_key=key))
    out = [_finish(g) for g in groups.values()]
    out.sort(key=lambda g: (-g.count, g.label))
    return out


def workshop_groups(charges):
    from workshop.models import Workshop

    groups = OrderedDict()
    rows = list(charges.values("workshop_id", "payment_status", "currency").annotate(n=Count("pk"), total=Sum("amount")))
    workshops = {w.pk: w for w in Workshop.objects.filter(pk__in={r["workshop_id"] for r in rows})}
    for r in rows:
        wid = r["workshop_id"]
        ws = workshops.get(wid)

        def make(wid=wid, ws=ws):
            return _new_group(
                wid, ws.title if ws else "Deleted workshop", workshop_id=wid,
                starts_at=ws.starts_at if ws else None,
                manage_url=reverse("workshop_admin:manage", args=[wid]) if ws else "",
            )
        _tally(groups, wid, r["payment_status"], r["currency"], r["n"], r["total"], make)
    out = [_finish(g) for g in groups.values()]
    far = timezone.now() - timezone.timedelta(days=36500)
    out.sort(key=lambda g: g.starts_at or far, reverse=True)  # most recent workshop first
    return out


def breakdown(*, query="", date_from=None, date_to=None):
    """Income grouped by stream and by review type / workshop, for the
    page's search and date range (never narrowed by the list's own tabs)."""
    apps = application_groups(application_payments(query=query, date_from=date_from, date_to=date_to))
    shops = workshop_groups(workshop_charges(query=query, date_from=date_from, date_to=date_to))
    applications = _roll_up(apps, "applications", "Ethics applications")
    workshops = _roll_up(shops, "workshops", "Workshops")
    return SimpleNamespace(
        applications=applications, application_groups=apps,
        workshops=workshops, workshop_groups=shops,
        total=_roll_up([applications, workshops], "total", "All income"),
    )


# ---------------------------------------------------------------------
# One stream's list
# ---------------------------------------------------------------------

def _application_row(p, group):
    return SimpleNamespace(
        group=group, reference=p.reference,
        payer=p.applicant.full_name if p.applicant_id else "", email=p.applicant.email if p.applicant_id else "",
        link_label=p.application.reference_no if p.application else "",
        link_url=reverse("admin_dashboard:application_detail", args=[p.application.pk]) if p.application else "",
        detail=p.purpose, amount=p.amount, currency=p.currency,
        status=p.status, status_label=STATUS_LABELS.get(p.status, p.status),
        created_at=p.created_at, paid_at=p.paid_at,
    )


def _workshop_row(r, group):
    return SimpleNamespace(
        group=group, reference=r.payment_reference or "",
        payer=r.name, email=r.email, link_label=r.institution, link_url="",
        detail="Certificate fee", amount=r.amount, currency=r.currency,
        status=r.payment_status, status_label=STATUS_LABELS.get(r.payment_status, r.payment_status),
        created_at=r.created_at, paid_at=r.paid_at,
    )


class Ledger:
    """One stream's payments ("applications" or "workshops"), optionally
    narrowed to one review type / one workshop, for the page's filters."""

    def __init__(self, *, source="applications", group="", query="", date_from=None, date_to=None):
        self.source = source if source in SOURCES else "applications"
        self.group = str(group or "")
        if self.source == "applications":
            qs = application_payments(query=query, date_from=date_from, date_to=date_to)
            keyed = _keyed_payments(qs)
            self.groups = application_groups(qs, keyed)
            if self.group:
                wanted = "" if self.group == "-" else self.group
                keyed = [(k, p) for k, p in keyed if k == wanted]
                qs = qs.filter(pk__in=[p.pk for _, p in keyed])
            self.keyed = dict((p.pk, k) for k, p in keyed)
            self.status_field = "status"
        else:
            qs = workshop_charges(query=query, date_from=date_from, date_to=date_to)
            self.groups = workshop_groups(qs)
            if self.group.isdigit():
                qs = qs.filter(workshop_id=int(self.group))
            self.status_field = "payment_status"
        self.qs = qs

    def group_options(self):
        """(value, label) for the list's group picker."""
        if self.source == "applications":
            return [(g.fee_key or "-", g.label) for g in self.groups]
        return [(str(g.workshop_id), g.label) for g in self.groups]

    def counts(self):
        out = {"all": self.qs.count()}
        for status in STATUSES:
            out[status] = self.qs.filter(**{self.status_field: status}).count()
        return out

    def rows(self, status="all"):
        """Rows grouped (by review type / workshop, in the summary's order),
        newest first within each group."""
        qs = self.qs
        if status in STATUSES:
            qs = qs.filter(**{self.status_field: status})
        by_key = {g.key: g for g in self.groups}
        order = {g.key: i for i, g in enumerate(self.groups)}
        if self.source == "applications":
            items = [(self.keyed.get(p.pk, ""), p) for p in qs.select_related("applicant", "application")]
            rows = [_application_row(p, by_key.get(k)) for k, p in items]
            keys = [k for k, _ in items]
        else:
            items = [(r.workshop_id, r) for r in qs]
            rows = [_workshop_row(r, by_key.get(k)) for k, r in items]
            keys = [k for k, _ in items]
        paired = list(zip(keys, rows))
        paired.sort(key=lambda kr: (order.get(kr[0], 1 << 30), -kr[1].created_at.timestamp()))
        return [r for _, r in paired]


def export_csv(source, rows):
    """The list on screen as a CSV, with the group each payment belongs to."""
    stream = "workshop" if source == "workshops" else "ethics-application"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="msrec-{stream}-payments-{timezone.localdate().isoformat()}.csv"'
    )
    response.write("﻿")
    writer = csv.writer(response)
    if source == "workshops":
        writer.writerow(["Workshop", "Reference", "Participant", "Email", "Institution",
                         "Amount", "Currency", "Status", "Registered At", "Paid At"])
    else:
        writer.writerow(["Fee Category", "Reference", "Applicant", "Email", "Application Ref",
                         "Purpose", "Amount", "Currency", "Status", "Created At", "Paid At"])

    def stamp(dt):
        return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M") if dt else ""

    for r in rows:
        group = r.group.label if r.group else ""
        if source == "workshops":
            writer.writerow([group, r.reference, r.payer, r.email, r.link_label,
                             r.amount, r.currency, r.status_label, stamp(r.created_at), stamp(r.paid_at)])
        else:
            writer.writerow([group, r.reference, r.payer, r.email, r.link_label, r.detail,
                             r.amount, r.currency, r.status_label, stamp(r.created_at), stamp(r.paid_at)])
    return response
