from django.db.models import F, OuterRef, Q, Subquery


def unread_messages(request):
    """Feeds the Communications sidebar badges (Applicant Messages / Reviewer
    Messages) on every Secretariat page -- same shape as
    applicant_dashboard.context_processors.notif_bell, scoped to role ==
    secretariat so it's a no-op (and does no extra queries) on every other
    dashboard, even though it's registered globally in settings.py.

    Each unread count is one query: a correlated subquery pulls this staff
    member's own last_read_at for each conversation, so a message counts as
    unread if there's no read mark at all, or it arrived after that mark --
    the same rule messaging.views uses per-conversation, just done in bulk
    instead of once per conversation in the list.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or user.role != user.Role.SECRETARIAT:
        return {}

    from messaging.models import (
        ConversationRead, Message, ReviewerConversationRead, ReviewerMessage,
    )

    applicant_read_at = ConversationRead.objects.filter(
        conversation=OuterRef("conversation"), user=user,
    ).values("last_read_at")[:1]
    unread_applicant_messages = (
        Message.objects.exclude(sender=user)
        .annotate(_read_at=Subquery(applicant_read_at))
        .filter(Q(_read_at__isnull=True) | Q(created_at__gt=F("_read_at")))
        .count()
    )

    reviewer_read_at = ReviewerConversationRead.objects.filter(
        conversation=OuterRef("conversation"), user=user,
    ).values("last_read_at")[:1]
    unread_reviewer_messages = (
        ReviewerMessage.objects.exclude(sender=user)
        .annotate(_read_at=Subquery(reviewer_read_at))
        .filter(Q(_read_at__isnull=True) | Q(created_at__gt=F("_read_at")))
        .count()
    )

    return {
        "nav_unread_applicant_messages": unread_applicant_messages,
        "nav_unread_reviewer_messages": unread_reviewer_messages,
    }
