"""Committee member protocol review -- Protocols for Committee Review,
Reviewer Recommendations, Conflict & Recusal and Committee Deliberations.

A member's "protocols" are the applications placed on the agenda of a
meeting they've been invited to (AgendaItem.application), never their own
submissions. Everything is read from existing Supabase tables (agenda items,
applications, review assignments, meetings); writes go to two tables:
ProtocolDeclaration (their conflict declaration) and DeliberationPost.

Confidentiality rules, enforced here rather than in templates:
  * a member who has recused themselves from a protocol is locked out of its
    detail, reviewer recommendations and deliberation;
  * a member can only post to a deliberation once they have declared, and
    only while their declaration lets them participate (no conflict, or a
    conflict the Chair has cleared).
"""
from collections import Counter, defaultdict
from types import SimpleNamespace

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError, transaction
from django.db.models import Count, Max
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from applicant_dashboard import storage as application_storage
from applicant_dashboard.models import Application
from meetings.models import AgendaItem, Meeting
from notifications import services as notification_services
from notifications.models import Notification
from pages.models import ConflictDeclaration
from payments import fees
from reviewer_dashboard.models import ReviewAssignment

from .models import DeliberationPost, ProtocolDeclaration

MAX_POST_LENGTH = 3000
MAX_CONFLICT_LENGTH = 2000

REC_SHORT = {
    "approve": "Approve",
    "minor_revisions": "Minor revisions",
    "major_revisions": "Major revisions",
    "refer_committee": "Refer to committee",
    "not_approved": "Not approved",
}
REC_ORDER = ["approve", "minor_revisions", "major_revisions", "refer_committee", "not_approved"]
REC_BADGE = ReviewAssignment.RECOMMENDATION_BADGE

DECL_LABEL = {
    "none": "Not declared",
    "clear": "No conflict",
    "pending": "Awaiting Chair decision",
    "recused": "Recused",
    "cleared": "Cleared to participate",
}


def _is_committee(user):
    return (
        user.is_authenticated
        and user.role == User.Role.COMMITTEE
        and user.committee_status == User.RequestStatus.APPROVED
    )


committee_required = user_passes_test(_is_committee, login_url="pages:login")


def _base_context(request):
    audience = Notification.Audience.COMMITTEE
    return {
        "notifications": notification_services.for_user(request.user, audience, limit=6),
        "unread_count": notification_services.unread_count(request.user, audience),
    }


# ------------------------------------------------------------ data assembly

def _text(value):
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value if v)
    return str(value).strip() if value not in (None, "") else ""


def _consensus(recs):
    """(label, badge) summarising the reviewers' completed recommendations."""
    if not recs:
        return "Awaiting reviews", "gray"
    counts = Counter(a.recommendation for a in recs)
    top, top_n = counts.most_common(1)[0]
    if len(counts) == 1:
        return (f"Unanimous: {REC_SHORT[top]}" if len(recs) > 1 else REC_SHORT[top]), REC_BADGE.get(top, "gray")
    if top_n * 2 > len(recs):
        return f"Majority: {REC_SHORT[top]}", REC_BADGE.get(top, "gray")
    return "Split opinions", "orange"


def _tally(recs):
    counts = Counter(a.recommendation for a in recs)
    total = len(recs) or 1
    return [
        {
            "key": key, "label": REC_SHORT[key], "badge": REC_BADGE[key],
            "count": counts[key], "pct": round(100 * counts[key] / total),
        }
        for key in REC_ORDER if counts[key]
    ]


def _protocol_rows(user, *, only=None):
    """Every protocol this member can see, as SimpleNamespaces carrying the
    application, the meeting it's on, my declaration, the reviewers'
    recommendations and discussion activity. `only` restricts to one
    application id (for the detail/thread pages)."""
    items = (
        AgendaItem.objects
        .filter(application__isnull=False, meeting__participants__user=user)
        .exclude(meeting__status=Meeting.Status.CANCELLED)
        .exclude(application__applicant=user)
        .exclude(application__status=Application.Status.DRAFT)
        .select_related("application", "application__applicant", "meeting")
        .order_by("meeting__scheduled_at")
    )
    if only is not None:
        items = items.filter(application_id=only)

    now = timezone.now()
    per_app = defaultdict(list)
    for item in items:  # ascending by meeting date
        per_app[item.application_id].append(item)
    chosen = {}
    for app_id, app_items in per_app.items():
        upcoming = [
            i for i in app_items
            if i.meeting.status == Meeting.Status.SCHEDULED and i.meeting.ends_at >= now
        ]
        # the next upcoming meeting it's on, else the most recent one
        chosen[app_id] = (upcoming[0] if upcoming else app_items[-1], bool(upcoming))
    if not chosen:
        return []

    app_ids = list(chosen)

    declarations = {
        d.application_id: d
        for d in ProtocolDeclaration.objects.filter(user=user, application_id__in=app_ids).select_related("conflict_record")
    }

    completed = defaultdict(list)
    assigned = Counter()
    for a in ReviewAssignment.objects.filter(application_id__in=app_ids).exclude(
        status=ReviewAssignment.Status.DECLINED
    ).select_related("reviewer"):
        assigned[a.application_id] += 1
        if a.status == ReviewAssignment.Status.COMPLETED and a.recommendation:
            completed[a.application_id].append(a)

    activity = {
        row["application_id"]: row
        for row in DeliberationPost.objects.filter(application_id__in=app_ids, is_deleted=False)
        .values("application_id")
        .annotate(posts=Count("id"), people=Count("author", distinct=True), last=Max("created_at"))
    }

    rows = []
    for app_id, (item, _up) in chosen.items():
        app = item.application
        data = app.form_data or {}
        decl = declarations.get(app_id)
        status = decl.effective_status if decl else "none"
        recs = completed.get(app_id, [])
        label, badge = _consensus(recs)
        act = activity.get(app_id)
        rows.append(SimpleNamespace(
            app=app, pk=app_id, item=item, meeting=item.meeting,
            ref=app.reference_no or f"Application #{app.pk}", title=app.title,
            pi_name=_text(data.get("piName")), institution=_text(data.get("piInstitution")),
            review_type=fees.label_for(app.review_type),
            decl=decl, status=status, status_label=DECL_LABEL.get(status, status),
            is_recused=status == "recused",
            can_participate=status in ("clear", "cleared"),
            recs=recs, reviews_in=len(recs), reviews_assigned=assigned.get(app_id, 0),
            consensus=label, consensus_badge=badge, tally=_tally(recs),
            post_count=act["posts"] if act else 0,
            people_count=act["people"] if act else 0,
            last_post_at=act["last"] if act else None,
        ))
    rows.sort(key=lambda r: (r.meeting.scheduled_at, r.ref))
    return rows


def _get_protocol(user, pk):
    rows = _protocol_rows(user, only=pk)
    if not rows:
        raise Http404("Protocol not found")
    return rows[0]


# ---------------------------------------------------------------- protocols

@login_required
@committee_required
def protocols(request):
    rows = _protocol_rows(request.user)
    ctx = _base_context(request)
    ctx.update({
        "protocols": rows,
        "total": len(rows),
        "needs_declaration": sum(1 for r in rows if r.status == "none"),
        "participating": sum(1 for r in rows if r.can_participate),
        "recused_count": sum(1 for r in rows if r.status in ("recused", "pending")),
        "reviews_in_count": sum(1 for r in rows if r.reviews_in),
        "discussion_total": sum(r.post_count for r in rows),
    })
    return render(request, "dashboards/committee/protocols.html", ctx)


PROTOCOL_FACTS = [
    ("Principal investigator", "piName"), ("Institution", "piInstitution"), ("Department", "piDepartment"),
    ("Study type", "studyType"), ("Research area", "researchArea"), ("Funding", "fundingOrg"),
    ("Start date", "startDate"), ("Completion", "completionDate"), ("Risk level", "riskLevel"),
    ("Consent method", "consentMethod"),
]
PROTOCOL_SECTIONS = [
    ("Purpose of the study", "studyPurpose"), ("Methodology", "methodologyDesc"),
    ("Risks to participants", "risksDescribe"), ("How risks are minimised", "risksMinimize"),
    ("Expected benefits", "expectedBenefits"),
]
PROTOCOL_FLAGS = [
    ("Identifiable data", "identifiableInfoYn"), ("Sensitive information", "sensitiveInfoYn"),
    ("Externally funded", "fundedYn"), ("Commercially sponsored", "commerciallySponsoredYn"),
    ("Participant compensation", "compensationYn"), ("International study", "internationalYn"),
    ("Uses AI", "aiInvolvedYn"),
]


def _yes(value):
    return str(value).strip().lower() in {"yes", "y", "true", "1", "on"}


@login_required
@committee_required
def protocol_detail(request, pk):
    p = _get_protocol(request.user, pk)
    data = p.app.form_data or {}
    ctx = _base_context(request)
    ctx["p"] = p

    if not p.is_recused:
        ctx.update({
            "facts": [(label, _text(data.get(key))) for label, key in PROTOCOL_FACTS if _text(data.get(key))],
            "sections": [(label, _text(data.get(key))) for label, key in PROTOCOL_SECTIONS if _text(data.get(key))],
            "flags": [(label, _yes(data.get(key))) for label, key in PROTOCOL_FLAGS if _text(data.get(key))],
            "documents": [
                {**doc, "url": application_storage.public_url(doc.get("path"))}
                for doc in (p.app.documents or [])
            ],
            "latest_posts": list(
                DeliberationPost.objects.filter(application_id=pk, is_deleted=False)
                .select_related("author").order_by("-created_at")[:3]
            ),
        })
    return render(request, "dashboards/committee/protocol_detail.html", ctx)


# ---------------------------------------------------------- recommendations

@login_required
@committee_required
def recommendations(request):
    rows = _protocol_rows(request.user)
    for p in rows:
        if p.is_recused:
            continue
        for a in p.recs:
            a.rec_short = REC_SHORT.get(a.recommendation, a.get_recommendation_display())
            a.rec_badge = REC_BADGE.get(a.recommendation, "gray")
            checklist = a.checklist or {}
            a.check_rows = [
                {
                    "label": label,
                    "text": ReviewAssignment.CHECKLIST_LABEL.get(checklist.get(key), "Not answered"),
                    "badge": ReviewAssignment.CHECKLIST_BADGE.get(checklist.get(key), "gray"),
                }
                for key, label in ReviewAssignment.CHECKLIST_ITEMS
            ]
            a.needs_revision_count = sum(1 for v in checklist.values() if v == "needs_revision")

    visible = [p for p in rows if not p.is_recused]
    ctx = _base_context(request)
    ctx.update({
        "protocols": rows,
        "with_reviews": sum(1 for p in visible if p.reviews_in),
        "unanimous_approve": sum(1 for p in visible if p.consensus.endswith("Approve") and p.consensus.startswith("Unanimous")),
        "split_count": sum(1 for p in visible if p.consensus == "Split opinions"),
        "awaiting_count": sum(1 for p in visible if not p.reviews_in),
        "rec_legend": [(REC_SHORT[k], REC_BADGE[k]) for k in REC_ORDER],
    })
    return render(request, "dashboards/committee/recommendations.html", ctx)


# ---------------------------------------------------------------- conflicts

def _governance_seat(user):
    try:
        return user.governance_seat
    except ObjectDoesNotExist:
        return None


def _sync_conflict_record(decl, user, application):
    """Mirror a declared conflict onto pages.ConflictDeclaration so the
    Secretariat/admin Conflict Records page sees it. Never raises -- a
    member without a governance seat simply has no mirrored record."""
    record = decl.conflict_record
    seat = _governance_seat(user)
    type_label = decl.get_conflict_type_display() or "Conflict"
    text = f"[{type_label}] {decl.description}".strip()

    if decl.has_conflict:
        status = ConflictDeclaration.Status.RECUSED if decl.wants_recusal else ConflictDeclaration.Status.PENDING
        if record is not None:
            record.description, record.status = text, status
            record.save(update_fields=["description", "status", "updated_at"])
        elif seat is not None:
            decl.conflict_record = ConflictDeclaration.objects.create(
                member=seat, application=application, related_to=(application.reference_no or "")[:200],
                description=text, status=status, recorded_by=user,
            )
    elif record is not None and record.status != ConflictDeclaration.Status.RESOLVED:
        record.status = ConflictDeclaration.Status.RESOLVED
        record.resolution_notes = "Withdrawn by the member: no conflict declared."
        record.resolved_at = timezone.now()
        record.save(update_fields=["status", "resolution_notes", "resolved_at", "updated_at"])


@login_required
@committee_required
def conflicts(request):
    rows = _protocol_rows(request.user)
    declared = sorted((r for r in rows if r.decl), key=lambda r: r.decl.updated_at, reverse=True)
    ctx = _base_context(request)
    ctx.update({
        "awaiting": [r for r in rows if not r.decl],
        "declared": declared,
        "clear_count": sum(1 for r in rows if r.status == "clear"),
        "conflict_count": sum(1 for r in rows if r.decl and r.decl.has_conflict),
        "recused_count": sum(1 for r in rows if r.status == "recused"),
        "awaiting_count": sum(1 for r in rows if not r.decl),
        "conflict_types": ProtocolDeclaration.ConflictType.choices,
    })
    return render(request, "dashboards/committee/conflicts.html", ctx)


@login_required
@committee_required
@require_POST
def conflict_declare(request, pk):
    p = _get_protocol(request.user, pk)
    back = redirect(request.POST.get("next") if request.POST.get("next", "").startswith("/dashboard/committee/")
                    else reverse("committee_dashboard:conflicts"))

    existing = p.decl
    if existing and existing.effective_status == ProtocolDeclaration.Status.CLEARED and existing.has_conflict:
        messages.error(request, "The Chair has already ruled on your declaration for this protocol.")
        return back

    has_conflict = request.POST.get("has_conflict") == "1"
    conflict_type = request.POST.get("conflict_type", "")
    description = request.POST.get("description", "").strip()
    wants_recusal = request.POST.get("action") == "recuse"

    if has_conflict:
        if conflict_type not in ProtocolDeclaration.ConflictType.values:
            messages.error(request, "Please choose the type of conflict.")
            return back
        if not description:
            messages.error(request, "Please describe the conflict so the Chair can assess it.")
            return back
        if len(description) > MAX_CONFLICT_LENGTH:
            messages.error(request, f"Please keep the description under {MAX_CONFLICT_LENGTH} characters.")
            return back
    else:
        conflict_type, description, wants_recusal = "", "", False

    status = (
        ProtocolDeclaration.Status.CLEAR if not has_conflict
        else ProtocolDeclaration.Status.RECUSED if wants_recusal
        else ProtocolDeclaration.Status.PENDING
    )
    try:
        with transaction.atomic():
            decl, _created = ProtocolDeclaration.objects.get_or_create(application=p.app, user=request.user)
            decl.has_conflict, decl.conflict_type = has_conflict, conflict_type
            decl.description, decl.wants_recusal, decl.status = description, wants_recusal, status
            _sync_conflict_record(decl, request.user, p.app)
            decl.save()
    except DatabaseError:
        messages.error(request, "Your declaration couldn't be saved. Please try again.")
        return back

    if has_conflict:
        note = f"{request.user.full_name} declared a conflict of interest on {p.ref}" + (
            " and has recused themselves." if wants_recusal else " and is awaiting a Chair decision."
        )
        for audience in (Notification.Audience.SECRETARIAT, Notification.Audience.CHAIR):
            notification_services.notify(audience, note, icon=Notification.Icon.WARN)
        messages.success(
            request,
            "You have recused yourself from this protocol." if wants_recusal
            else "Your conflict has been sent to the Chair for a decision.",
        )
    else:
        messages.success(request, f"Recorded: no conflict of interest on {p.ref}.")
    return back


# ------------------------------------------------------------ deliberations

@login_required
@committee_required
def deliberations(request):
    rows = _protocol_rows(request.user)
    ctx = _base_context(request)
    ctx.update({
        "protocols": rows,
        "active_count": sum(1 for r in rows if r.post_count and not r.is_recused),
        "post_total": sum(r.post_count for r in rows if not r.is_recused),
        "quiet_count": sum(1 for r in rows if not r.post_count and not r.is_recused),
    })
    return render(request, "dashboards/committee/deliberations.html", ctx)


def _thread(application_id):
    posts = list(
        DeliberationPost.objects.filter(application_id=application_id).select_related("author").order_by("created_at", "id")
    )
    replies = defaultdict(list)
    top = []
    for post in posts:
        if post.parent_id:
            replies[post.parent_id].append(post)
        else:
            top.append(post)
    for post in top:
        post.reply_list = replies.get(post.pk, [])
    live = [p for p in posts if not p.is_deleted]
    kinds = Counter(p.kind for p in live)
    people = {p.author_id for p in live}
    return top, live, kinds, len(people)


@login_required
@committee_required
def deliberation_thread(request, pk):
    p = _get_protocol(request.user, pk)
    ctx = _base_context(request)
    ctx["p"] = p
    if not p.is_recused:
        top, live, kinds, people = _thread(pk)
        ctx.update({
            "posts": top,
            "post_count": len(live),
            "people_count": people,
            "kind_counts": [
                {"key": k, "label": label, "count": kinds.get(k, 0)}
                for k, label in DeliberationPost.Kind.choices
            ],
            "kinds": DeliberationPost.Kind.choices,
        })
    return render(request, "dashboards/committee/deliberation_thread.html", ctx)


@login_required
@committee_required
@require_POST
def deliberation_post(request, pk):
    p = _get_protocol(request.user, pk)
    back = f"{reverse('committee_dashboard:deliberation_thread', args=[pk])}"

    if p.is_recused:
        messages.error(request, "You have recused yourself from this protocol.")
        return redirect(back)
    if not p.decl:
        messages.error(request, "Please declare any conflict of interest before joining the discussion.")
        return redirect(reverse("committee_dashboard:conflicts"))
    if not p.can_participate:
        messages.error(request, "You can join the discussion once the Chair has cleared your declared conflict.")
        return redirect(back)

    body = request.POST.get("body", "").strip()
    kind = request.POST.get("kind", DeliberationPost.Kind.COMMENT)
    if kind not in DeliberationPost.Kind.values:
        kind = DeliberationPost.Kind.COMMENT
    if not body:
        messages.error(request, "Write something before posting.")
        return redirect(back)
    if len(body) > MAX_POST_LENGTH:
        messages.error(request, f"Posts are limited to {MAX_POST_LENGTH} characters.")
        return redirect(back)

    parent = None
    parent_id = request.POST.get("parent")
    if parent_id:
        parent = DeliberationPost.objects.filter(pk=parent_id, application_id=pk, is_deleted=False).first()
        if parent is None:
            messages.error(request, "That post is no longer available to reply to.")
            return redirect(back)
        if parent.parent_id:  # one level of nesting: reply to the top-level post
            parent = parent.parent

    post = DeliberationPost.objects.create(application=p.app, author=request.user, parent=parent, kind=kind, body=body)
    return redirect(f"{back}#post-{post.pk}")


@login_required
@committee_required
@require_POST
def deliberation_delete(request, post_id):
    post = get_object_or_404(DeliberationPost, pk=post_id, author=request.user)
    post.is_deleted, post.body = True, ""
    post.save(update_fields=["is_deleted", "body", "updated_at"])
    messages.success(request, "Your post was removed.")
    return redirect(reverse("committee_dashboard:deliberation_thread", args=[post.application_id]))
