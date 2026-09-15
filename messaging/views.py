from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import is_staff_side, staff_role_label
from .models import Conversation, ConversationRead, Message

staff_required = user_passes_test(is_staff_side, login_url="pages:login")


def _serialize_message(message, viewer):
    local = timezone.localtime(message.created_at)
    return {
        "id": message.pk,
        "body": message.body,
        "sender_id": message.sender_id,
        "sender_name": message.sender.full_name,
        # '' for the applicant's own messages -- see staff_role_label().
        "sender_role": staff_role_label(message.sender),
        "is_mine": message.sender_id == viewer.pk,
        "created_at": message.created_at.isoformat(),
        "created_at_display": local.strftime("%b %d, %Y · %I:%M %p"),
        "time_display": local.strftime("%I:%M %p").lstrip("0"),
    }


def _mark_read(conversation, user):
    ConversationRead.objects.update_or_create(
        conversation=conversation, user=user, defaults={"last_read_at": timezone.now()}
    )


def _unread_count(conversation, user):
    qs = conversation.messages.exclude(sender=user)
    mark = ConversationRead.objects.filter(conversation=conversation, user=user).first()
    if mark and mark.last_read_at:
        qs = qs.filter(created_at__gt=mark.last_read_at)
    return qs.count()


def _get_or_create_conversation(applicant):
    conversation, _ = Conversation.objects.get_or_create(applicant=applicant)
    return conversation


# ---------------------------------------------------------------------
# Applicant side -- one conversation per applicant, resolved from
# request.user, so the URLs never carry a conversation id (nothing to
# tamper with, nothing to look up wrong).
# ---------------------------------------------------------------------

@login_required
def applicant_messages(request):
    conversation = _get_or_create_conversation(request.user)

    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            Message.objects.create(conversation=conversation, sender=request.user, body=body)
        _mark_read(conversation, request.user)
        return redirect("applicant_dashboard:messages")

    _mark_read(conversation, request.user)
    thread_messages = [_serialize_message(m, request.user) for m in conversation.messages.select_related("sender")]
    last_id = thread_messages[-1]["id"] if thread_messages else 0

    return render(request, "dashboards/applicant/messages.html", {
        "thread_messages": thread_messages,
        "last_message_id": last_id,
    })


@login_required
def applicant_messages_poll(request):
    conversation = _get_or_create_conversation(request.user)
    return _poll_response(request, conversation)


@login_required
@require_POST
def applicant_messages_send(request):
    conversation = _get_or_create_conversation(request.user)
    return _send_response(request, conversation)


# ---------------------------------------------------------------------
# Staff side -- every applicant's conversation, inbox-style: pick one,
# read/reply, same poll/send machinery keyed by conversation id. Shared
# by admin_dashboard AND secretariat_dashboard (see their urls.py) --
# is_staff_side already treats Admin and Secretariat as the same "staff
# side" of a conversation, so one view pair serves both, each passing
# its own dashboard's template_name so the sidebar/topbar stay branded.
# ---------------------------------------------------------------------

@login_required
@staff_required
def staff_messages(request, template_name="dashboards/admin/messages.html"):
    conversations = list(
        Conversation.objects.select_related("applicant")
        .annotate(last_message_at=Max("messages__created_at"), message_count=Count("messages"))
        .order_by("-last_message_at", "-created_at")
    )
    for c in conversations:
        c.unread_for_staff = _unread_count(c, request.user)

    selected_id = request.GET.get("conversation")
    selected = None
    if selected_id:
        selected = next((c for c in conversations if str(c.pk) == selected_id), None)
    if selected is None:
        selected = conversations[0] if conversations else None

    thread_messages = []
    if selected is not None:
        thread_messages = [
            _serialize_message(m, request.user) for m in selected.messages.select_related("sender")
        ]
        _mark_read(selected, request.user)
        selected.unread_for_staff = 0

    return render(request, template_name, {
        "conversations": conversations,
        "selected": selected,
        "thread_messages": thread_messages,
        "last_message_id": thread_messages[-1]["id"] if thread_messages else 0,
    })


@login_required
@staff_required
def staff_messages_poll(request, conversation_id):
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    return _poll_response(request, conversation)


@login_required
@staff_required
@require_POST
def staff_messages_send(request, conversation_id):
    conversation = get_object_or_404(Conversation, pk=conversation_id)
    return _send_response(request, conversation)


# ---------------------------------------------------------------------
# Shared JSON handlers
# ---------------------------------------------------------------------

def _poll_response(request, conversation):
    after_id = request.GET.get("after") or 0
    try:
        after_id = int(after_id)
    except (TypeError, ValueError):
        after_id = 0

    new_messages = list(
        conversation.messages.select_related("sender").filter(pk__gt=after_id)
    )
    if new_messages:
        _mark_read(conversation, request.user)

    latest = conversation.messages.aggregate(Max("id"))["id__max"] or after_id
    return JsonResponse({
        "messages": [_serialize_message(m, request.user) for m in new_messages],
        "last_id": latest,
    })


def _send_response(request, conversation):
    body = request.POST.get("body", "").strip()
    if not body:
        return JsonResponse({"error": "empty"}, status=400)
    if len(body) > 4000:
        return JsonResponse({"error": "too_long"}, status=400)

    message = Message.objects.create(conversation=conversation, sender=request.user, body=body)
    _mark_read(conversation, request.user)
    return JsonResponse(_serialize_message(message, request.user))
