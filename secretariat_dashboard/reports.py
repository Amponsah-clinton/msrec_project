"""Query helpers behind the Reports & Analytics page -- kept out of
views.py the same way applicant_dashboard/oversight.py and
payments/services.py are, so each tab's aggregation logic reads as one
function with one job rather than getting lost inside a long view.

Every number here comes from a real table (Application, ReviewAssignment,
Payment, RoleApprovalLog) -- there is deliberately no Committee-decision
or Post-Approval (amendment/adverse-event/continuing-review) model in
this project yet, so committee_activity() and post_approval_compliance()
say so honestly instead of inventing numbers -- same "empty until
populated, and says why" posture as reviewer_dashboard.models.ReviewAssignment's
own docstring.
"""
import calendar
from decimal import Decimal

from django.db.models import Avg, Count, F, Q, Sum
from django.utils import timezone

from accounts.models import RoleApprovalLog, User
from applicant_dashboard.models import Application
from payments import fees
from payments.models import Payment
from reviewer_dashboard.models import ReviewAssignment

REVIEW_TYPE_ORDER = ["exemption", "expedited", "full", "not-sure"]

STATUS_COLOR = {
    Application.Status.SUBMITTED: "blue",
    Application.Status.UNDER_REVIEW: "purple",
    Application.Status.REVISIONS_REQUIRED: "orange",
    Application.Status.APPROVED: "green",
    Application.Status.NOT_APPROVED: "red",
}


def _non_draft():
    return Application.objects.exclude(status=Application.Status.DRAFT)


def _last_n_months(n):
    """The last `n` calendar months as (year, month, label), oldest
    first, always ending on the current month -- used for both the
    submissions trend and the revenue trend so they line up."""
    today = timezone.localdate()
    months = []
    y, m = today.year, today.month
    for _ in range(n):
        months.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    months.reverse()
    return [(y, m, f"{calendar.month_abbr[m]}") for y, m in months]


def _month_bounds(year, month):
    start = timezone.datetime(year, month, 1)
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    if month == 12:
        end = timezone.datetime(year + 1, 1, 1)
    else:
        end = timezone.datetime(year, month + 1, 1)
    if timezone.is_naive(end):
        end = timezone.make_aware(end)
    return start, end


def application_statistics():
    qs = _non_draft()
    total = qs.count()

    status_counts = [
        {"key": status, "label": label, "count": qs.filter(status=status).count(), "color": STATUS_COLOR.get(status, "gray")}
        for status, label in Application.Status.choices if status != Application.Status.DRAFT
    ]

    type_counts = []
    for review_type in REVIEW_TYPE_ORDER:
        count = qs.filter(review_type=review_type).count()
        type_counts.append({"key": review_type, "label": fees.label_for(review_type), "count": count})
    untyped = qs.exclude(review_type__in=REVIEW_TYPE_ORDER).count()
    if untyped:
        type_counts.append({"key": "", "label": "Not specified", "count": untyped})

    decided = qs.filter(status__in=[Application.Status.APPROVED, Application.Status.NOT_APPROVED])
    approved = decided.filter(status=Application.Status.APPROVED).count()
    decided_total = decided.count()
    approval_rate = round((approved / decided_total) * 100) if decided_total else None

    trend = []
    for year, month, label in _last_n_months(6):
        start, end = _month_bounds(year, month)
        trend.append({"label": label, "count": qs.filter(submitted_at__gte=start, submitted_at__lt=end).count()})
    trend_max = max((row["count"] for row in trend), default=0) or 1

    return {
        "total": total,
        "status_counts": status_counts,
        "type_counts": type_counts,
        "type_max": max((row["count"] for row in type_counts), default=0) or 1,
        "status_max": max((row["count"] for row in status_counts), default=0) or 1,
        "approval_rate": approval_rate,
        "decided_total": decided_total,
        "trend": trend,
        "trend_max": trend_max,
    }


def status_reports():
    qs = list(_non_draft().select_related("applicant").order_by("-submitted_at"))
    now = timezone.now()
    for application in qs:
        anchor = application.decided_at or now
        application.days_open = (anchor - application.submitted_at).days if application.submitted_at else None

    counts = {status: 0 for status, _ in Application.Status.choices}
    for application in qs:
        counts[application.status] = counts.get(application.status, 0) + 1

    return {
        "applications": qs,
        "counts": counts,
    }


def turnaround_times():
    decided = _non_draft().filter(
        status__in=[Application.Status.APPROVED, Application.Status.NOT_APPROVED],
        decided_at__isnull=False, submitted_at__isnull=False,
    )

    overall = decided.aggregate(avg_days=Avg(F("decided_at") - F("submitted_at")))
    avg_days = overall["avg_days"].days if overall["avg_days"] else None

    fastest = decided.order_by(F("decided_at") - F("submitted_at")).first()
    slowest = decided.order_by(F("decided_at") - F("submitted_at")).last()

    by_type = []
    for review_type in REVIEW_TYPE_ORDER:
        type_qs = decided.filter(review_type=review_type)
        agg = type_qs.aggregate(avg_days=Avg(F("decided_at") - F("submitted_at")), n=Count("id"))
        if agg["n"]:
            by_type.append({
                "label": fees.label_for(review_type),
                "avg_days": agg["avg_days"].days,
                "n": agg["n"],
            })
    by_type_max = max((row["avg_days"] for row in by_type), default=0) or 1

    return {
        "avg_days": avg_days,
        "decided_total": decided.count(),
        "fastest_days": (fastest.decided_at - fastest.submitted_at).days if fastest else None,
        "slowest_days": (slowest.decided_at - slowest.submitted_at).days if slowest else None,
        "by_type": by_type,
        "by_type_max": by_type_max,
    }


def reviewer_workload():
    reviewers = list(
        User.objects.filter(role=User.Role.REVIEWER, reviewer_status=User.RequestStatus.APPROVED)
        .annotate(
            active_count=Count(
                "review_assignments",
                filter=Q(review_assignments__status__in=[ReviewAssignment.Status.NEW, ReviewAssignment.Status.ACCEPTED]),
                distinct=True,
            ),
            overdue_count=Count(
                "review_assignments",
                filter=Q(
                    review_assignments__status=ReviewAssignment.Status.ACCEPTED,
                    review_assignments__due_date__lte=timezone.localdate(),
                ),
                distinct=True,
            ),
            completed_count=Count(
                "review_assignments",
                filter=Q(review_assignments__status=ReviewAssignment.Status.COMPLETED),
                distinct=True,
            ),
        )
        .order_by("-completed_count", "-active_count", "first_name")
    )

    totals = {
        "reviewers": len(reviewers),
        "active": sum(r.active_count for r in reviewers),
        "overdue": sum(r.overdue_count for r in reviewers),
        "completed": sum(r.completed_count for r in reviewers),
    }
    return {"reviewers": reviewers, "totals": totals}


def committee_activity():
    """The only committee-related audit trail this project actually
    records today: admin approve/reject decisions on the Committee role
    itself (accounts.models.RoleApprovalLog). There's no meeting/vote/
    decision model yet -- the note in the template says so rather than
    padding this out with invented activity."""
    logs = list(
        RoleApprovalLog.objects.filter(role=User.Role.COMMITTEE)
        .select_related("user", "acted_by")
        .order_by("-created_at")[:50]
    )
    current_members = User.objects.filter(role=User.Role.COMMITTEE).count()
    approved = RoleApprovalLog.objects.filter(role=User.Role.COMMITTEE, action=RoleApprovalLog.Action.APPROVED).count()
    rejected = RoleApprovalLog.objects.filter(role=User.Role.COMMITTEE, action=RoleApprovalLog.Action.REJECTED).count()

    return {
        "logs": logs,
        "current_members": current_members,
        "approved": approved,
        "rejected": rejected,
    }


def post_approval_compliance():
    """Amendments / Continuing Reviews / Adverse Events / Complaints /
    Closures all have a placeholder link in the sidebar's Post-Approval
    Management group, but no backing model yet -- listed here as honest
    "not tracked yet" cards rather than a report with made-up numbers."""
    return {
        "modules": [
            {"label": "Amendments", "icon": "edit"},
            {"label": "Continuing Reviews", "icon": "refresh"},
            {"label": "Progress Reports", "icon": "doc"},
            {"label": "Deviations", "icon": "alert"},
            {"label": "Adverse Events", "icon": "alert"},
            {"label": "Complaints / Ethics Concerns", "icon": "flag"},
            {"label": "Closures", "icon": "check"},
        ],
    }


def financial_reports():
    payments_qs = Payment.objects.all()
    successful = payments_qs.filter(status=Payment.Status.SUCCESS)

    total_collected = successful.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    pending_amount = payments_qs.filter(status=Payment.Status.PENDING).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    by_type = []
    for review_type in REVIEW_TYPE_ORDER:
        agg = successful.filter(review_type=review_type).aggregate(total=Sum("amount"), n=Count("id"))
        if agg["n"]:
            by_type.append({"label": fees.label_for(review_type), "total": agg["total"] or Decimal("0"), "n": agg["n"]})
    by_type_max = max((row["total"] for row in by_type), default=Decimal("0")) or Decimal("1")

    trend = []
    for year, month, label in _last_n_months(6):
        start, end = _month_bounds(year, month)
        total = successful.filter(paid_at__gte=start, paid_at__lt=end).aggregate(total=Sum("amount"))["total"] or Decimal("0")
        trend.append({"label": label, "total": total})
    trend_max = max((row["total"] for row in trend), default=Decimal("0")) or Decimal("1")

    return {
        "total_collected": total_collected,
        "pending_amount": pending_amount,
        "success_count": successful.count(),
        "failed_count": payments_qs.filter(status=Payment.Status.FAILED).count(),
        "by_type": by_type,
        "by_type_max": by_type_max,
        "trend": trend,
        "trend_max": trend_max,
        "currency": fees.CURRENCY,
    }
