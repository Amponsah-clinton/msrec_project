"""Committee member Meetings & Agenda -- Dashboard meeting widgets,
Committee Meetings (Upcoming / Calendar / Previous) and the Meeting Agenda.

Kept in its own module (views.py re-exports these) so the account pages
(Notifications / Profile / Security in account_views.py) and this section
can be edited independently.

Everything is read from the `meetings` app's tables (Supabase Postgres): a
member sees only meetings they've been invited to (a MeetingParticipant
row). Two things are written back: their RSVP
(MeetingParticipant.rsvp_status) and their private per-item notes
(AgendaItemNote -> meeting_agenda_notes).
"""
import calendar as _calendar
import datetime as _dt
from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import DatabaseError
from django.db.models import Count, Prefetch
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.models import User
from meetings.models import AgendaItem, AgendaItemNote, Meeting, MeetingParticipant
from notifications import services as notification_services
from notifications.models import Notification

MAX_NOTE_LENGTH = 5000


def _is_committee(user):
    return (
        user.is_authenticated
        and user.role == User.Role.COMMITTEE
        and user.committee_status == User.RequestStatus.APPROVED
    )


committee_required = user_passes_test(_is_committee, login_url="pages:login")


# ---------------------------------------------------------------- helpers

def _base_context(request):
    """What the shared topbar (bell dropdown) needs on every page."""
    audience = Notification.Audience.COMMITTEE
    return {
        "notifications": notification_services.for_user(request.user, audience, limit=6),
        "unread_count": notification_services.unread_count(request.user, audience),
    }


def _my_meetings(user):
    """Meetings this member is invited to; `.mine` holds their own
    MeetingParticipant row, `.agenda_count` the number of agenda items."""
    return (
        Meeting.objects.filter(participants__user=user)
        .select_related("chair")
        .prefetch_related(Prefetch(
            "participants", queryset=MeetingParticipant.objects.filter(user=user), to_attr="mine",
        ))
        .annotate(agenda_count=Count("agenda_items", distinct=True))
        .distinct()
    )


def _attach_mine(meetings):
    for m in meetings:
        m.my_part = m.mine[0] if getattr(m, "mine", None) else None
    return meetings


def _split_meetings(user):
    """(upcoming, previous). A meeting counts as upcoming while it's in
    progress; cancelled ones always go to previous."""
    now = timezone.now()
    everything = _attach_mine(list(_my_meetings(user).order_by("scheduled_at")))
    upcoming, previous = [], []
    for m in everything:
        if m.status == Meeting.Status.SCHEDULED and m.ends_at >= now:
            upcoming.append(m)
        else:
            previous.append(m)
    previous.reverse()  # most recent first
    return upcoming, previous


def _decorate_timing(meetings):
    """Adds `.is_live` and `.days_away` (whole local days) to each meeting."""
    now = timezone.now()
    today = timezone.localdate()
    for m in meetings:
        m.is_live = m.status == Meeting.Status.SCHEDULED and m.scheduled_at <= now <= m.ends_at
        m.days_away = (timezone.localtime(m.scheduled_at).date() - today).days
    return meetings


def _safe_next(request, fallback):
    target = request.POST.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def _reviewed_count(user, item_ids):
    if not item_ids:
        return 0
    try:
        return AgendaItemNote.objects.filter(user=user, agenda_item_id__in=item_ids, is_reviewed=True).count()
    except DatabaseError:
        # meeting_agenda_notes not created yet (supabase/committee_agenda_notes.sql)
        return 0


# -------------------------------------------------------------- dashboard

def home_context(request):
    """Extra context the Dashboard home template needs (meeting stats,
    next-meeting hero, agenda preview). `home` in views.py merges this with
    the shared shell context."""
    upcoming, previous = _split_meetings(request.user)
    _decorate_timing(upcoming)
    _decorate_timing(previous)

    next_meeting = upcoming[0] if upcoming else None
    next_items, protocols_on_agenda, prepared = [], 0, 0
    if next_meeting:
        next_items = list(next_meeting.agenda_items.select_related("application").order_by("order", "id"))
        protocols_on_agenda = sum(1 for i in next_items if i.application_id)
        prepared = _reviewed_count(request.user, [i.pk for i in next_items])

    awaiting = [
        m for m in upcoming
        if m.my_part and m.my_part.rsvp_status == MeetingParticipant.RsvpStatus.PENDING
    ]
    return {
        "next_meeting": next_meeting,
        "next_items": next_items[:5],
        "next_items_total": len(next_items),
        "protocols_on_agenda": protocols_on_agenda,
        "prepared_count": prepared,
        "upcoming_meetings": upcoming[:4],
        "upcoming_count": len(upcoming),
        "awaiting_rsvp": awaiting,
        "awaiting_rsvp_count": len(awaiting),
        "previous_count": len(previous),
        "recent_meetings": previous[:3],
    }


# -------------------------------------------------------------- meetings

@login_required
@committee_required
def meetings_upcoming(request):
    upcoming, _previous = _split_meetings(request.user)
    _decorate_timing(upcoming)
    ctx = _base_context(request)
    ctx.update({
        "meetings": upcoming,
        "live_meetings": [m for m in upcoming if m.is_live],
        "type_filters": Meeting.MeetingType.choices,
    })
    return render(request, "dashboards/committee/meetings_upcoming.html", ctx)


@login_required
@committee_required
def meetings_previous(request):
    _upcoming, previous = _split_meetings(request.user)
    _decorate_timing(previous)
    ctx = _base_context(request)
    ctx.update({
        "meetings": previous,
        "attended_count": sum(1 for m in previous if m.my_part and m.my_part.attended),
        "completed_count": sum(1 for m in previous if m.status == Meeting.Status.COMPLETED),
        "cancelled_count": sum(1 for m in previous if m.status == Meeting.Status.CANCELLED),
    })
    return render(request, "dashboards/committee/meetings_previous.html", ctx)


@login_required
@committee_required
def meetings_calendar(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        first = _dt.date(year, month, 1)
    except (ValueError, OverflowError):
        year, month = today.year, today.month
        first = _dt.date(year, month, 1)

    following = _dt.date(year + 1, 1, 1) if month == 12 else _dt.date(year, month + 1, 1)
    preceding = _dt.date(year - 1, 12, 1) if month == 1 else _dt.date(year, month - 1, 1)

    month_meetings = _attach_mine(list(
        _my_meetings(request.user)
        .filter(scheduled_at__date__gte=first, scheduled_at__date__lt=following)
        .order_by("scheduled_at")
    ))
    by_day = defaultdict(list)
    for m in month_meetings:
        by_day[timezone.localtime(m.scheduled_at).day].append(m)

    weeks = []
    for week in _calendar.Calendar(firstweekday=6).monthdayscalendar(year, month):  # Sunday-first
        weeks.append([
            {
                "day": day,
                "is_today": bool(day) and today == _dt.date(year, month, day),
                "meetings": by_day.get(day, []),
            }
            for day in week
        ])

    upcoming, _previous = _split_meetings(request.user)
    ctx = _base_context(request)
    ctx.update({
        "weeks": weeks,
        "month_label": first.strftime("%B %Y"),
        "prev_year": preceding.year, "prev_month": preceding.month,
        "next_year": following.year, "next_month": following.month,
        "today_year": today.year, "today_month": today.month,
        "month_meeting_count": len(month_meetings),
        "upcoming_meetings": _decorate_timing(upcoming[:5]),
    })
    return render(request, "dashboards/committee/meetings_calendar.html", ctx)


@login_required
@committee_required
@require_POST
def meeting_rsvp(request, pk):
    part = get_object_or_404(
        MeetingParticipant.objects.select_related("meeting"), meeting_id=pk, user=request.user,
    )
    meeting = part.meeting
    fallback = reverse("committee_dashboard:meetings_upcoming")

    status = request.POST.get("status")
    if status not in {
        MeetingParticipant.RsvpStatus.ACCEPTED,
        MeetingParticipant.RsvpStatus.DECLINED,
        MeetingParticipant.RsvpStatus.TENTATIVE,
    }:
        messages.error(request, "That isn't a valid response.")
        return redirect(_safe_next(request, fallback))
    if meeting.status != Meeting.Status.SCHEDULED or meeting.ends_at < timezone.now():
        messages.error(request, "This meeting is no longer open for responses.")
        return redirect(_safe_next(request, fallback))

    part.rsvp_status = status
    part.responded_at = timezone.now()
    part.save(update_fields=["rsvp_status", "responded_at"])

    verb = {"accepted": "accepted", "declined": "declined", "tentative": "tentatively accepted"}[status]
    notification_services.notify(
        Notification.Audience.SECRETARIAT,
        f"{request.user.full_name} {verb} the invitation to “{meeting.title}”.",
        icon=Notification.Icon.WARN if status == "declined" else Notification.Icon.INFO,
    )
    messages.success(request, f"Your response to “{meeting.title}” has been recorded.")
    return redirect(_safe_next(request, fallback))


# ---------------------------------------------------------------- agenda

def _agenda_meeting(request):
    """?meeting=<id> if given (and the member is invited), else their next
    meeting, else their most recent."""
    mine = _attach_mine(list(_my_meetings(request.user).order_by("-scheduled_at")[:60]))
    if not mine:
        return None, []

    wanted = request.GET.get("meeting")
    if wanted:
        for m in mine:
            if str(m.pk) == wanted:
                return m, mine
        raise Http404("Meeting not found")

    now = timezone.now()
    upcoming = [m for m in mine if m.status == Meeting.Status.SCHEDULED and m.ends_at >= now]
    if upcoming:
        return min(upcoming, key=lambda m: m.scheduled_at), mine
    return mine[0], mine


@login_required
@committee_required
def agenda(request):
    meeting, picker = _agenda_meeting(request)
    ctx = _base_context(request)
    ctx["meetings"] = picker

    if meeting is None:
        ctx["meeting"] = None
        return render(request, "dashboards/committee/agenda.html", ctx)

    _decorate_timing([meeting])
    items = list(meeting.agenda_items.select_related("application").order_by("order", "id"))

    try:
        notes = {
            n.agenda_item_id: n
            for n in AgendaItemNote.objects.filter(user=request.user, agenda_item__meeting=meeting)
        }
        notes_available = True
    except DatabaseError:
        notes, notes_available = {}, False

    clock = timezone.localtime(meeting.scheduled_at)
    total_minutes = 0
    for index, item in enumerate(items, start=1):
        item.number = index
        item.starts = clock + _dt.timedelta(minutes=total_minutes)
        total_minutes += item.duration_minutes
        item.ends = clock + _dt.timedelta(minutes=total_minutes)
        note = notes.get(item.pk)
        item.my_note = note.note if note else ""
        item.is_reviewed = bool(note and note.is_reviewed)

    participants = list(meeting.participants.select_related("user").order_by("role_at_meeting", "user__first_name"))
    rsvp_counts = defaultdict(int)
    for p in participants:
        rsvp_counts[p.rsvp_status] += 1

    reviewed = sum(1 for i in items if i.is_reviewed)
    ctx.update({
        "meeting": meeting,
        "items": items,
        "participants": participants,
        "rsvp_counts": dict(rsvp_counts),
        "total_minutes": total_minutes,
        "protocol_count": sum(1 for i in items if i.application_id),
        "reviewed_count": reviewed,
        "reviewed_pct": round(100 * reviewed / len(items)) if items else 0,
        "notes_available": notes_available,
        "over_time": total_minutes > meeting.duration_minutes,
        "can_rsvp": (
            meeting.my_part is not None
            and meeting.status == Meeting.Status.SCHEDULED
            and meeting.ends_at >= timezone.now()
        ),
        "can_take_notes": meeting.status != Meeting.Status.CANCELLED and notes_available,
    })
    return render(request, "dashboards/committee/agenda.html", ctx)


@login_required
@committee_required
@require_POST
def agenda_note_save(request, item_id):
    """Saves this member's private note and/or "prepared" flag for one
    agenda item. JSON for the page's autosave, redirect for a plain post."""
    item = get_object_or_404(AgendaItem.objects.select_related("meeting"), pk=item_id)
    is_ajax = request.headers.get("x-requested-with") == "fetch"
    back = f"{reverse('committee_dashboard:agenda')}?meeting={item.meeting_id}#item-{item.pk}"

    def fail(message, status):
        if is_ajax:
            return JsonResponse({"ok": False, "error": message}, status=status)
        messages.error(request, message)
        return redirect(back)

    if not MeetingParticipant.objects.filter(meeting_id=item.meeting_id, user=request.user).exists():
        return fail("You're not invited to this meeting.", 403)

    updates = {}
    if "note" in request.POST:
        text = request.POST["note"].strip()
        if len(text) > MAX_NOTE_LENGTH:
            return fail(f"Notes are limited to {MAX_NOTE_LENGTH} characters.", 400)
        updates["note"] = text
    if "is_reviewed" in request.POST:
        updates["is_reviewed"] = request.POST["is_reviewed"] in {"1", "true", "on"}
    if not updates:
        return fail("Nothing to save.", 400)

    try:
        note, _created = AgendaItemNote.objects.update_or_create(
            agenda_item=item, user=request.user, defaults=updates,
        )
        reviewed = AgendaItemNote.objects.filter(
            user=request.user, agenda_item__meeting_id=item.meeting_id, is_reviewed=True,
        ).count()
    except DatabaseError:
        return fail("Notes can't be saved yet — the notes table hasn't been set up.", 503)

    if is_ajax:
        return JsonResponse({
            "ok": True,
            "is_reviewed": note.is_reviewed,
            "reviewed_count": reviewed,
            "saved_at": date_format(timezone.localtime(note.updated_at), "g:i A"),
        })
    messages.success(request, "Saved.")
    return redirect(back)
