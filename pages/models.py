from django.conf import settings
from django.db import models


class Inquiry(models.Model):
    """One submission of the public Contact page
    (templates/pages/contact.html). Saved straight to Supabase Postgres via
    Django's ORM (no Storage involved -- there's nothing to upload here).
    admin_dashboard's Inquiries page is where the Secretariat reads and
    replies to these.
    """

    class Reason(models.TextChoices):
        SECRETARIAT = "secretariat", "Secretariat / General Enquiry"
        APPLICATION_SUPPORT = "application-support", "Application Support"
        COMPLAINTS = "complaints", "Complaints"
        ETHICS_CONCERNS = "ethics-concerns", "Ethics Concerns"
        TECHNICAL_SUPPORT = "technical-support", "Technical Support"

    class Status(models.TextChoices):
        NEW = "new", "New"
        RESOLVED = "resolved", "Resolved"

    name = models.CharField(max_length=150)
    email = models.EmailField()
    reason = models.CharField(max_length=30, choices=Reason.choices, default=Reason.SECRETARIAT)
    message = models.TextField()

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)

    # Set together when a Secretariat/admin user sends a reply from
    # dashboards/admin/inquiries.html (also emailed to `email` -- see
    # admin_dashboard.views.inquiries).
    reply_message = models.TextField(blank=True)
    replied_at = models.DateTimeField(null=True, blank=True)
    replied_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="inquiry_replies",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "inquiries"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}> - {self.get_reason_display()}"


# Titles stripped when deriving avatar initials from a full name (see
# GovernanceMember.initials) -- "Prof. Kojo Antwi-Boateng" should read as
# "KA", not "PK".
_NAME_TITLES = {
    "prof", "prof.", "dr", "dr.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.",
    "rev", "rev.", "barr", "barr.", "madam", "engr", "engr.",
}


class GovernanceMember(models.Model):
    """One person shown on the public Board & Committee page
    (templates/pages/board_committee.html) -- added, edited and removed
    from admin_dashboard's Board & Committee page, photo included, so the
    public page always reflects who's actually currently serving without
    anyone touching a template.
    """

    class Group(models.TextChoices):
        BOARD = "board", "Board"
        COMMITTEE = "committee", "Committee"
        SECRETARIAT = "secretariat", "Secretariat"

    full_name = models.CharField(max_length=150)
    role_title = models.CharField(max_length=150)
    # Short descriptor shown under the role, e.g. "Health & Biomedical
    # Science" for a Committee member or "Secretariat" for admin staff.
    tag = models.CharField(max_length=150, blank=True)
    group = models.CharField(max_length=20, choices=Group.choices)

    # Object path inside Supabase Storage's public "profile" bucket (see
    # pages/storage.py) -- blank means "no photo yet", and the public page
    # falls back to a colored initials avatar, same as every other
    # avatar in this app.
    photo_path = models.CharField(max_length=255, blank=True)

    # Lower sorts first within a group; ties break on full_name. Lets an
    # admin put a Chairperson above ordinary members without relying on
    # alphabetical luck.
    display_order = models.PositiveSmallIntegerField(default=0)

    # Unpublishing (someone's term ended, or they're on leave) without
    # losing the record -- same "keep the history, hide from the public
    # page" idea as User.is_active elsewhere in this app.
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "governance_members"
        ordering = ["group", "display_order", "full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.get_group_display()})"

    @property
    def initials(self):
        words = [w for w in self.full_name.replace(".", ". ").split() if w.strip(".")]
        significant = [w for w in words if w.lower().rstrip(".") not in {t.rstrip(".") for t in _NAME_TITLES}]
        significant = significant or words
        first = significant[0][0] if significant else ""
        last = significant[-1][0] if len(significant) > 1 else ""
        return (first + last).upper() or "?"
