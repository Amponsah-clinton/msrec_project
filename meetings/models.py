"""Full Committee / Secretariat meetings -- scheduling, agenda, RSVP +
check-in ("attendance"), quorum, minutes and recorded decisions.

One Meeting fans out into everything a real committee meeting needs:
MeetingParticipant (who's invited, whether they RSVP'd, whether they
actually showed up -- attendance and quorum are both read off this one
table), AgendaItem (what gets discussed, optionally tied to an
Application under review), MeetingMinutes (the narrative record, one
per meeting) and Decision (the actual outcome recorded against an
agenda item / application, with a vote tally).

Kept as its own app rather than folded into secretariat_dashboard
because a meeting's participants span roles (chair, committee members,
secretariat) -- it's a shared concept those dashboards read/write, not
one dashboard's private data.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class Meeting(models.Model):
    class MeetingType(models.TextChoices):
        FULL_COMMITTEE = "full_committee", "Full Committee Review"
        EXPEDITED_PANEL = "expedited_panel", "Expedited Panel"
        SPECIAL = "special", "Special Session"
        EMERGENCY = "emergency", "Emergency Session"
        ADMINISTRATIVE = "administrative", "Administrative / Planning"

    class Mode(models.TextChoices):
        IN_PERSON = "in_person", "In Person"
        VIRTUAL = "virtual", "Virtual"
        HYBRID = "hybrid", "Hybrid"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    title = models.CharField(max_length=200)
    meeting_type = models.CharField(max_length=20, choices=MeetingType.choices, default=MeetingType.FULL_COMMITTEE)
    description = models.TextField(blank=True)

    scheduled_at = models.DateTimeField()
    duration_minutes = models.PositiveIntegerField(default=120)

    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.IN_PERSON)
    location = models.CharField(max_length=255, blank=True, help_text="Room / building, for in-person or hybrid.")
    meeting_link = models.URLField(blank=True, help_text="Video call link, for virtual or hybrid.")

    # 0 means "not set yet" -- Quorum page prompts the Secretariat to set
    # this before treating the meeting as quorate/not quorate.
    quorum_required = models.PositiveIntegerField(default=0)

    chair = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="meetings_chaired"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="meetings_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "meetings"
        ordering = ["-scheduled_at"]

    def __str__(self):
        return f"{self.title} — {self.scheduled_at:%d %b %Y, %H:%M}"

    @property
    def is_past(self):
        return self.scheduled_at < timezone.now()

    @property
    def ends_at(self):
        return self.scheduled_at + timezone.timedelta(minutes=self.duration_minutes)

    def voting_participant_count(self):
        return self.participants.filter(is_voting=True).count()

    def attended_voting_count(self):
        return self.participants.filter(is_voting=True, attended=True).count()

    def is_quorate(self):
        if not self.quorum_required:
            return None
        return self.attended_voting_count() >= self.quorum_required


class MeetingParticipant(models.Model):
    class RsvpStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        TENTATIVE = "tentative", "Tentative"

    class ParticipantRole(models.TextChoices):
        CHAIR = "chair", "Chair"
        MEMBER = "member", "Committee Member"
        SECRETARY = "secretary", "Secretary / Secretariat"
        GUEST = "guest", "Guest / Observer"

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="meeting_invites")

    role_at_meeting = models.CharField(max_length=12, choices=ParticipantRole.choices, default=ParticipantRole.MEMBER)
    is_voting = models.BooleanField(default=True, help_text="Counts toward quorum and vote tallies.")

    rsvp_status = models.CharField(max_length=10, choices=RsvpStatus.choices, default=RsvpStatus.PENDING)
    invited_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    attended = models.BooleanField(default=False)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "meeting_participants"
        ordering = ["role_at_meeting", "user__first_name"]
        unique_together = [("meeting", "user")]

    def __str__(self):
        return f"{self.user} @ {self.meeting}"


class AgendaItem(models.Model):
    class ItemStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        DISCUSSED = "discussed", "Discussed"
        DEFERRED = "deferred", "Deferred"

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="agenda_items")
    order = models.PositiveIntegerField(default=0)

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    presenter = models.CharField(max_length=150, blank=True)
    duration_minutes = models.PositiveIntegerField(default=10)

    application = models.ForeignKey(
        "applicant_dashboard.Application", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="agenda_items",
    )
    status = models.CharField(max_length=10, choices=ItemStatus.choices, default=ItemStatus.PENDING)

    class Meta:
        db_table = "meeting_agenda_items"
        ordering = ["meeting", "order", "id"]

    def __str__(self):
        return self.title


class MeetingMinutes(models.Model):
    meeting = models.OneToOneField(Meeting, on_delete=models.CASCADE, related_name="minutes")
    content = models.TextField(blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="minutes_recorded"
    )
    is_finalized = models.BooleanField(default=False)
    finalized_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "meeting_minutes"

    def __str__(self):
        return f"Minutes — {self.meeting.title}"


class Decision(models.Model):
    class Outcome(models.TextChoices):
        APPROVED = "approved", "Approved"
        APPROVED_WITH_CONDITIONS = "approved_conditions", "Approved with Conditions"
        MODIFICATIONS_REQUIRED = "modifications", "Modifications Required"
        REJECTED = "rejected", "Rejected"
        DEFERRED = "deferred", "Deferred"
        TABLED = "tabled", "Tabled"
        NOTED = "noted", "Noted / For Information"

    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="decisions")
    agenda_item = models.ForeignKey(
        AgendaItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="decisions"
    )
    application = models.ForeignKey(
        "applicant_dashboard.Application", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="meeting_decisions",
    )

    title = models.CharField(max_length=255)
    outcome = models.CharField(max_length=20, choices=Outcome.choices, default=Outcome.NOTED)
    details = models.TextField(blank=True)

    votes_for = models.PositiveIntegerField(default=0)
    votes_against = models.PositiveIntegerField(default=0)
    votes_abstain = models.PositiveIntegerField(default=0)

    decided_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="decisions_recorded"
    )

    class Meta:
        db_table = "meeting_decisions"
        ordering = ["-decided_at"]

    def __str__(self):
        return f"{self.title} — {self.get_outcome_display()}"

    @property
    def total_votes(self):
        return self.votes_for + self.votes_against + self.votes_abstain


class AgendaItemNote(models.Model):
    """A committee member's own working notes on one agenda item, plus
    whether they've marked it "prepared". Private to that member -- one
    row per (agenda item, user), never shown to other participants.
    """

    agenda_item = models.ForeignKey(AgendaItem, on_delete=models.CASCADE, related_name="member_notes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agenda_notes")

    note = models.TextField(blank=True)
    is_reviewed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "meeting_agenda_notes"
        unique_together = [("agenda_item", "user")]

    def __str__(self):
        return f"{self.user} — {self.agenda_item}"
