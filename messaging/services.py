"""Small cross-app entry points into messaging -- the pieces other apps
(applicant_dashboard's nav-counts endpoint, the floating chat widget)
need without reaching into messaging.views' request/response-shaped
internals directly.
"""
from .models import Conversation
from .views import _unread_count


def unread_count_for_user(user):
    """Unread-message count for `user`'s own support conversation -- 0 if
    they've never started one. Safe to call for any authenticated user,
    not just applicants: staff have no `support_conversation` of their
    own (Conversation.applicant is always an applicant), so this simply
    returns 0 for them rather than raising."""
    conversation = Conversation.objects.filter(applicant=user).first()
    if conversation is None:
        return 0
    return _unread_count(conversation, user)
