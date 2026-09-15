from django.conf import settings
from django.db import models


class SiteSettings(models.Model):
    """The one site-wide configuration row -- logo, footer content,
    Contact page routing addresses, and the Paystack keys actually
    charged against. Edited from admin_dashboard's Settings page
    (admin-only, see admin_dashboard.views.site_settings).

    A true singleton: always read/written through get_solo(), which
    get-or-creates the one row at pk=1. Nothing else ever creates a
    second row or looks one up by a different id -- there's no "add
    another settings" anywhere in the UI, unlike GovernanceMember/
    Inquiry above, which are genuinely one-row-per-record.
    """

    # ---- Identity / logo -------------------------------------------------
    site_name = models.CharField(max_length=150, default="MSREC", blank=True)
    # Object path inside Supabase Storage's public "profile" bucket (see
    # pages/storage.py's upload_site_logo()) -- fixed "site/logo.<ext>"
    # path, not per-id like governance photos, since this is a singleton.
    # Blank means "no custom logo yet", and every template that shows the
    # logo falls back to the bundled static/assets/img/logo1.png.
    logo_path = models.CharField(max_length=255, blank=True)

    # ---- Public-site footer (templates/base.html) -------------------------
    footer_about = models.TextField(blank=True, default=(
        "Metascholar Research Ethics Committee provides structured ethical review, "
        "post-approval oversight and verifiable decisions for researchers and "
        "institutions across multiple disciplines."
    ))
    # Free text, one line per address component (org name / parent body /
    # country, or whatever an admin wants) -- rendered with linebreaksbr
    # rather than forcing a rigid name/line1/line2/country field shape.
    footer_address = models.TextField(blank=True, default=(
        "Metascholar Research Ethics Committee\nEstablished under Metascholar Limited\nGhana"
    ))
    footer_phone = models.CharField(max_length=40, blank=True, default="+1 5589 55488 55")
    footer_email = models.EmailField(blank=True, default="secretariat@msrec.org")
    social_twitter_url = models.URLField(blank=True)
    social_facebook_url = models.URLField(blank=True)
    social_instagram_url = models.URLField(blank=True)
    social_linkedin_url = models.URLField(blank=True)

    # ---- Contact page (templates/pages/contact.html) ----------------------
    # One routing address per Inquiry.Reason -- these are what a submitter
    # sees as "who this goes to", shown as plain text on the Contact page
    # (the actual submission always goes through pages.views.contact into
    # the Inquiry table regardless of which address is displayed here).
    contact_secretariat_email = models.EmailField(blank=True, default="secretariat@msrec.org")
    contact_applications_email = models.EmailField(blank=True, default="applications@msrec.org")
    contact_complaints_email = models.EmailField(blank=True, default="complaints@msrec.org")
    contact_ethics_email = models.EmailField(blank=True, default="ethics@msrec.org")
    contact_techsupport_email = models.EmailField(blank=True, default="techsupport@msrec.org")
    contact_phone = models.CharField(max_length=40, blank=True, default="+1 5589 55488 55")

    # ---- Payment gateway ---------------------------------------------------
    # Blank means "not overridden here" -- payments/paystack.py and
    # payments/views.py fall back to settings.PAYSTACK_SECRET_KEY/
    # PAYSTACK_PUBLIC_KEY (the env-configured ones) whenever these are
    # empty, so an install works out of the box before anyone visits this
    # page, and switching keys live never requires touching .env or
    # redeploying. See effective_paystack_public_key/_secret_key below.
    paystack_public_key = models.CharField(max_length=150, blank=True)
    paystack_secret_key = models.CharField(max_length=150, blank=True)

    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="site_settings_edits",
    )

    class Meta:
        db_table = "site_settings"

    def __str__(self):
        return "Site Settings"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def logo_url(self):
        if not self.logo_path:
            return None
        from . import storage
        return storage.public_url(self.logo_path)

    @property
    def effective_paystack_public_key(self):
        from django.conf import settings as django_settings
        return self.paystack_public_key or django_settings.PAYSTACK_PUBLIC_KEY

    @property
    def effective_paystack_secret_key(self):
        from django.conf import settings as django_settings
        return self.paystack_secret_key or django_settings.PAYSTACK_SECRET_KEY


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
