from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone

from meetings.models import Meeting, MeetingMinutes

from .meeting_views import _base_context, _decorate_timing
from .views import committee_required


def _visible_meetings(user):
    """Meetings the member was invited to and whose minutes exist."""
    return (
        Meeting.objects.filter(participants__user=user, minutes__isnull=False)
        .select_related("chair", "minutes", "minutes__recorded_by")
        .distinct()
        .order_by("-scheduled_at")
    )


def _paragraphs(text):
    """Split typed minutes into blocks: blank-line separated paragraphs."""
    blocks = [b.strip() for b in (text or "").replace("\r\n", "\n").split("\n\n")]
    return [b.split("\n") for b in blocks if b]


@login_required
@committee_required
def minutes(request):
    meetings = list(_visible_meetings(request.user))
    _decorate_timing(meetings)
    mine = {p.meeting_id: p for p in request.user.meeting_invites.filter(meeting__in=meetings)}
    for m in meetings:
        m.my_part = mine.get(m.pk)
        m.has_text = bool((m.minutes.content or "").strip())

    selected = None
    raw = request.GET.get("meeting")
    if raw and raw.isdigit():
        selected = next((m for m in meetings if m.pk == int(raw)), None)
    if selected is None and meetings:
        selected = meetings[0]

    ctx = _base_context(request)
    ctx.update({
        "meetings": meetings,
        "meeting": selected,
        "blocks": _paragraphs(selected.minutes.content) if selected else [],
        "finalised_count": sum(1 for m in meetings if m.minutes.is_finalized),
        "draft_count": sum(1 for m in meetings if not m.minutes.is_finalized),
        "decisions": list(selected.decisions.all()[:20]) if selected else [],
        "now": timezone.now(),
    })
    return render(request, "dashboards/committee/minutes.html", ctx)


@login_required
@committee_required
def minutes_status(request, pk):
    """Lightweight poll so an open page can tell the secretary saved again."""
    obj = MeetingMinutes.objects.filter(
        meeting_id=pk, meeting__participants__user=request.user
    ).first()
    if not obj:
        return JsonResponse({"exists": False})
    return JsonResponse({
        "exists": True,
        "stamp": obj.updated_at.isoformat(),
        "finalized": obj.is_finalized,
    })
