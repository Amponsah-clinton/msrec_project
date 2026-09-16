from django.conf import settings
from django.db import models


class Conversation(models.Model):
    """One applicant's support conversation with MSREC.

    Deliberately not "conversation between exactly two named users" --
    `applicant` is the one fixed party, and the other side is anyone
    currently staffing the Secretariat (see messaging.access.is_staff_side),
    which membership.py-style modelling around an M2M would only chase.
    One row per applicant keeps "get my conversation" a single get-or-create
    with no possibility of duplicates.
    """

    applicant = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="support_conversation"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "conversations"

    def __str__(self):
        return f"Support conversation with {self.applicant.email}"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "messages"
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"#{self.pk} in conversation {self.conversation_id}"


class ConversationRead(models.Model):
    """Per-user last-read marker for a conversation -- one row per (user,
    conversation) rather than a read receipt per message, so unread counts
    (`Message.created_at > last_read_at`, excluding the viewer's own
    messages) stay a single indexed query no matter how long the thread
    gets."""

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="read_marks")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversation_reads"
    )
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "conversation_reads"
        constraints = [
            models.UniqueConstraint(fields=["conversation", "user"], name="unique_conversation_read_per_user")
        ]

    def __str__(self):
        return f"{self.user_id} read conversation {self.conversation_id} @ {self.last_read_at}"


class ReviewerConversation(models.Model):
    """The Secretariat's side-channel to one reviewer -- same shape as
    Conversation above (one row per reviewer, get-or-create), but this
    side the Secretariat is the one who opens the first line, since a
    reviewer has no reason to message in before they've been assigned
    anything. Kept as its own table rather than reusing Conversation so
    "applicant" never has to become a nullable/generic FK just to also
    mean "reviewer" -- the two inboxes never mix.
    """

    reviewer = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviewer_conversation"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reviewer_conversations"

    def __str__(self):
        return f"Reviewer conversation with {self.reviewer.email}"


class ReviewerMessage(models.Model):
    conversation = models.ForeignKey(ReviewerConversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_reviewer_messages"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reviewer_messages"
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"#{self.pk} in reviewer conversation {self.conversation_id}"


class ReviewerConversationRead(models.Model):
    conversation = models.ForeignKey(ReviewerConversation, on_delete=models.CASCADE, related_name="read_marks")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviewer_conversation_reads"
    )
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "reviewer_conversation_reads"
        constraints = [
            models.UniqueConstraint(fields=["conversation", "user"], name="unique_reviewer_conversation_read_per_user")
        ]

    def __str__(self):
        return f"{self.user_id} read reviewer conversation {self.conversation_id} @ {self.last_read_at}"
