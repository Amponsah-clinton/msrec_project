from django.conf import settings
from django.db import models
from django.utils import timezone


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
# "KA", not "PK". Also the option list for GovernanceMember.title's
# dropdown on the Add/Edit Board & Committee member form.
GOVERNANCE_TITLE_CHOICES = [
    "Prof.", "Dr.", "Mr.", "Mrs.", "Ms.", "Rev.", "Engr.", "Barr.", "Madam",
]
_NAME_TITLES = {
    "prof", "prof.", "dr", "dr.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.",
    "rev", "rev.", "barr", "barr.", "madam", "engr", "engr.",
}

# Option list for GovernanceMember.tag's "Tag / discipline" dropdown --
# reuses the same research-area taxonomy as the applicant application
# form (Section 2.1, "Main Research Area") for consistency, plus a couple
# of governance-specific entries. The form always offers an "Other"
# option alongside these so anyone whose discipline isn't listed can type
# their own -- tag itself stays a free-text column, this is just what the
# dropdown suggests.
GOVERNANCE_TAG_CHOICES = [
    "Health & Biomedical Sciences", "Nursing & Allied Health", "Public Health",
    "Clinical Research", "Pharmaceutical Research", "Social & Behavioral Sciences",
    "Education", "Business & Management", "Economics", "Agriculture & Food Science",
    "Environmental Research", "Engineering", "Computer Science & ICT",
    "Artificial Intelligence & Machine Learning", "Data Science & Big Data",
    "Cybersecurity & Networking", "Human-Computer Interaction",
    "Software & Information Systems Development", "Renewable Energy & Energy Systems",
    "Multidisciplinary Research", "Law & Governance", "Secretariat",
]


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
    # Honorific shown before the name (e.g. "Prof.", "Dr.") -- kept
    # separate from full_name so it can be a dropdown rather than typed
    # inline; blank means none was set (legacy rows may still carry a
    # title as part of full_name -- see initials, below).
    title = models.CharField(max_length=20, blank=True)
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
    def display_name(self):
        return f"{self.title} {self.full_name}".strip() if self.title else self.full_name

    @property
    def initials(self):
        words = [w for w in self.full_name.replace(".", ". ").split() if w.strip(".")]
        significant = [w for w in words if w.lower().rstrip(".") not in {t.rstrip(".") for t in _NAME_TITLES}]
        significant = significant or words
        first = significant[0][0] if significant else ""
        last = significant[-1][0] if len(significant) > 1 else ""
        return (first + last).upper() or "?"


class ClientLogo(models.Model):
    """One logo in the landing page's scrolling "Clients" carousel
    (templates/pages/index.html, #clients section) -- added, reordered
    and removed from admin_dashboard's Settings page (Client Logos tab),
    so the carousel can be updated without anyone touching a template or
    the bundled static/assets/img/clients/client-N.png files.

    If no ClientLogo rows exist, the public page falls back to that
    bundled set of 8 -- same "blank means use the bundled default" idea
    as SiteSettings.logo_path above.
    """

    # Object path inside Supabase Storage's public "profile" bucket (see
    # pages/storage.py's upload_client_logo()) under "clients/<id>/".
    # upload_client_logo() always letterboxes the image onto storage.
    # CLIENT_LOGO_SIZE before it's saved, so every slide in the carousel
    # reads at the same size regardless of what an admin uploads.
    image_path = models.CharField(max_length=255)
    alt_text = models.CharField(max_length=150, blank=True)

    # Lower sorts first -- lets an admin control carousel order without
    # relying on upload order.
    display_order = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "client_logos"
        ordering = ["display_order", "created_at"]

    def __str__(self):
        return self.alt_text or f"Client logo #{self.pk}"


class Testimonial(models.Model):
    """One card in the landing page's "Grounded in Recognized Standards"
    carousel (templates/pages/index.html, #testimonials section) -- added,
    edited and removed from admin_dashboard's Settings page (Testimonials
    tab), so the carousel's quotes and photos can be updated without
    anyone touching a template or the bundled static/assets/img/
    testimonials/testimonials-N.jpg files.

    If no Testimonial rows exist, the public page falls back to that
    bundled set of 5 hardcoded cards -- same "blank means use the bundled
    default" idea as ClientLogo above.
    """

    org_name = models.CharField(max_length=150)
    subtitle = models.CharField(max_length=200, blank=True)
    quote = models.TextField()

    # Object path inside Supabase Storage's public "profile" bucket (see
    # pages/storage.py's upload_testimonial_image()) under
    # "testimonials/<id>/". Blank means no photo was uploaded yet.
    image_path = models.CharField(max_length=255, blank=True)

    # Lower sorts first -- lets an admin control carousel order without
    # relying on creation order.
    display_order = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "testimonials"
        ordering = ["display_order", "created_at"]

    def __str__(self):
        return self.org_name


class CommitteeMeeting(models.Model):
    """One scheduled Full Committee / REC meeting -- shown on the
    Reviewer dashboard's Upcoming Meetings page. Managed from Django
    admin (/admin/) by the Secretariat; MeetingDocument rows (agenda,
    packet, minutes) attach to one of these.
    """

    title = models.CharField(max_length=200)
    scheduled_at = models.DateTimeField()
    # Physical room, or blank if this is a virtual-only meeting.
    location = models.CharField(max_length=255, blank=True)
    # Zoom/Teams/etc link -- blank means in-person only.
    meeting_link = models.URLField(blank=True)
    agenda = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "committee_meetings"
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.title} ({self.scheduled_at:%d %b %Y})"

    @property
    def is_past(self):
        return self.scheduled_at < timezone.now()


class MeetingDocument(models.Model):
    """One file attached to a CommitteeMeeting -- its agenda, full review
    packet, or minutes. Shown on the Reviewer dashboard's Meeting
    Documents / Packets page. File lives in Supabase Storage's public
    "ethics" bucket (pages/documents_storage.py); downloads are a direct
    public URL, resolved fresh on every render from file_path.
    """

    class DocType(models.TextChoices):
        AGENDA = "agenda", "Agenda"
        PACKET = "packet", "Meeting Packet"
        MINUTES = "minutes", "Minutes"
        OTHER = "other", "Other"

    meeting = models.ForeignKey(CommitteeMeeting, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=20, choices=DocType.choices, default=DocType.OTHER)
    title = models.CharField(max_length=200)

    # Blank until a file is actually uploaded (see admin.py's upload
    # form) -- the record can exist first (e.g. "Minutes -- pending")
    # without blocking on a file being ready yet.
    file_path = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "meeting_documents"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return f"{self.title} ({self.get_doc_type_display()})"


class PolicyDocument(models.Model):
    """One MSREC SOP / Reviewer Guidance / Ethics Guideline document,
    shown on the Reviewer dashboard's three Policies & Guidance pages
    (filtered by `category`, each its own URL -- not tabs on one page).
    Same public "ethics" bucket as MeetingDocument.
    """

    class Category(models.TextChoices):
        SOP = "sop", "MSREC SOP"
        GUIDANCE = "guidance", "Reviewer Guidance"
        ETHICS = "ethics", "Ethics Guideline"

    category = models.CharField(max_length=20, choices=Category.choices)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    version = models.CharField(max_length=20, blank=True)

    file_path = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)

    display_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "policy_documents"
        ordering = ["category", "display_order", "title"]

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"


class ResourceDocument(models.Model):
    """One item on the public Resource Centre page
    (templates/pages/resources.html) -- an Application Form, Protocol
    Template, Consent Template, Reporting Form, Guideline, FAQ or Training
    entry. One shared table/model for all seven categories (filtered by
    `category`, rendered into that category's card grid) rather than
    seven near-identical models. Managed from admin_dashboard's Resources
    page. File lives in Supabase Storage's public "resources" bucket
    (pages/resources_storage.py); a row doesn't need a file at all (e.g. a
    FAQ is just title+description), so file_path is optional.
    """

    class Category(models.TextChoices):
        APPLICATION_FORMS = "application_forms", "Application Forms"
        PROTOCOL_TEMPLATES = "protocol_templates", "Protocol Templates"
        CONSENT_TEMPLATES = "consent_templates", "Consent Templates"
        REPORTING_FORMS = "reporting_forms", "Reporting Forms"
        GUIDELINES = "guidelines", "Guidelines"
        FAQS = "faqs", "FAQs"
        TRAINING = "training", "Training"

    category = models.CharField(max_length=20, choices=Category.choices)
    title = models.CharField(max_length=200)
    # For most categories, a short blurb shown under the title. For FAQs,
    # this is the answer body; for Training, the module description.
    description = models.TextField(blank=True)

    file_path = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    # Fallback for a Training entry that just links out to an external
    # course rather than a file hosted here -- blank means "no link".
    external_url = models.URLField(blank=True)

    # Unpublishing keeps the record (and any uploaded file) without
    # showing it on the public page -- same idea as GovernanceMember.is_active.
    is_published = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "resource_documents"
        ordering = ["category", "display_order", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.get_category_display()})"

    @property
    def file_name(self):
        return self.file_path.rsplit("/", 1)[-1] if self.file_path else ""

    @property
    def download_url(self):
        if not self.file_path:
            return None
        from . import resources_storage
        return resources_storage.public_url(self.file_path)


class CommitteeAppointment(models.Model):
    """One appointment/term for a Board or Committee member -- which seat
    they hold, who appointed them, and for how long. Terms & Expiry
    (admin_dashboard) reads these same rows sorted/filtered by end_date
    instead of start_date -- there's one appointment history per member,
    not two separate concepts, so Membership/Appointments and Terms &
    Expiry are two views onto one table.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RENEWED = "renewed", "Renewed"
        EXPIRED = "expired", "Expired"
        TERMINATED = "terminated", "Terminated"

    member = models.ForeignKey(GovernanceMember, on_delete=models.CASCADE, related_name="appointments")
    seat_title = models.CharField(
        max_length=150, help_text='e.g. "Committee Member — Health & Biomedical Science"'
    )
    appointed_by = models.CharField(max_length=150, blank=True)
    start_date = models.DateField()
    # Blank means open-ended / until further notice -- Terms & Expiry
    # treats those as "ongoing", never as expiring.
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)

    # Object path inside Supabase Storage's public "ethics" bucket (see
    # pages/documents_storage.py), under "appointments/<id>/" -- blank
    # until the signed letter is uploaded.
    letter_path = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "committee_appointments"
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.member.full_name} — {self.seat_title}"

    @property
    def days_to_expiry(self):
        if not self.end_date:
            return None
        return (self.end_date - timezone.now().date()).days

    @property
    def expiry_state(self):
        """"ongoing" (no end date), "expired", "expiring" (<=90 days out) or "current"."""
        days = self.days_to_expiry
        if days is None:
            return "ongoing"
        if days < 0:
            return "expired"
        if days <= 90:
            return "expiring"
        return "current"


class TrainingRecord(models.Model):
    """One completed (or scheduled) training/certification for a Board or
    Committee member -- GCP, human subjects protection, conflict of
    interest, etc. Shown on the Training page (admin_dashboard) so the
    Secretariat can see who's due for refresher training before a term
    renewal.
    """

    member = models.ForeignKey(GovernanceMember, on_delete=models.CASCADE, related_name="training_records")
    course_title = models.CharField(max_length=200)
    provider = models.CharField(max_length=150, blank=True)
    completed_date = models.DateField(null=True, blank=True)
    # Blank means the certification doesn't expire.
    expiry_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    # Object path inside Supabase Storage's public "ethics" bucket, under
    # "training/<id>/" -- blank until the certificate is uploaded.
    certificate_path = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "committee_training_records"
        ordering = ["-completed_date"]

    def __str__(self):
        return f"{self.member.full_name} — {self.course_title}"

    @property
    def days_to_expiry(self):
        if not self.expiry_date:
            return None
        return (self.expiry_date - timezone.now().date()).days

    @property
    def expiry_state(self):
        days = self.days_to_expiry
        if days is None:
            return "ongoing"
        if days < 0:
            return "expired"
        if days <= 90:
            return "expiring"
        return "current"


class ConflictDeclaration(models.Model):
    """One conflict-of-interest declaration against a Board or Committee
    member -- recorded whenever a member discloses (or is flagged for) a
    potential conflict on an application, then tracked through to
    resolution. Shown on the Conflict Records page (admin_dashboard).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending Review"
        REVIEWED = "reviewed", "Reviewed"
        RECUSED = "recused", "Member Recused"
        RESOLVED = "resolved", "Resolved"

    member = models.ForeignKey(GovernanceMember, on_delete=models.CASCADE, related_name="conflict_declarations")
    application = models.ForeignKey(
        "applicant_dashboard.Application", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="conflict_declarations",
    )
    # Free-text context when no specific application applies, e.g. an
    # institution name or study title.
    related_to = models.CharField(max_length=200, blank=True)
    date_declared = models.DateField(default=timezone.now)
    description = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    resolution_notes = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="conflicts_recorded"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "committee_conflict_declarations"
        ordering = ["-date_declared"]

    def __str__(self):
        return f"{self.member.full_name} — {self.get_status_display()}"
