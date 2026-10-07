"""Workshop registration, settings and certificate design.

Three tables, all in Supabase Postgres via the ORM:
  * WorkshopSettings          -- one row: banner, fee, meeting link, materials
  * WorkshopCertificateTemplate -- one row: the certificate wording + signatories
  * WorkshopRegistration      -- one row per person who registers on /workshop

The public /workshop page (workshop.views.register) writes a
WorkshopRegistration; an admin manages everything from /admins/workshop/.
"""
from decimal import Decimal

from django.db import models
from django.utils import timezone


class WorkshopSettings(models.Model):
    """The one workshop configuration row (always pk=1 via get_solo) -- the
    banner shown on /workshop, the certificate fee charged when someone asks
    for a certificate, the meeting link and the materials an admin sends out.
    """

    workshop_title = models.CharField(max_length=200, default="MSREC Research Ethics Workshop")
    workshop_tagline = models.CharField(max_length=300, blank=True, default="Strengthening ethical research across institutions")
    workshop_description = models.TextField(blank=True, default=(
        "Join the Metascholar Research Ethics Committee for a practical workshop on research "
        "ethics, review pathways and good research practice. Register below to take part."
    ))

    # Banner: an uploaded image (object path in the public "workshop" bucket)
    # takes precedence over an external link; with neither set the page shows
    # a styled gradient hero (see templates/workshop/register.html).
    banner_image_path = models.CharField(max_length=255, blank=True)
    banner_image_link = models.URLField(blank=True)

    # What a certificate costs (charged via Paystack when someone ticks
    # "I want a certificate"). Editable from the admin workshop page.
    certificate_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("100.00"))
    fee_currency = models.CharField(max_length=10, default="GHS")

    # Sent to registrants from the admin page.
    meeting_link = models.URLField(blank=True)
    materials_file_path = models.CharField(max_length=255, blank=True)
    materials_link = models.URLField(blank=True)

    registration_open = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workshop_settings"

    def __str__(self):
        return "Workshop Settings"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def banner_url(self):
        if self.banner_image_path:
            from . import storage
            return storage.public_url(self.banner_image_path)
        return self.banner_image_link or None

    @property
    def materials_download_url(self):
        if self.materials_file_path:
            from . import storage
            return storage.public_url(self.materials_file_path)
        return self.materials_link or None


# Default certificate wording. {name} is the recipient, {workshop} the title.
CERT_BODY_DEFAULT = (
    "participated in the {workshop} organised by the Metascholar Research Ethics "
    "Committee, and is recognised for their active engagement and commitment to "
    "advancing ethical research practice."
)


class WorkshopCertificateTemplate(models.Model):
    """The one certificate-design row (pk=1 via get_solo) -- title, wording,
    seal caption and up to two signatories (name, title and a background-free
    signature PNG each). Edited from the admin workshop page; the PDF is drawn
    on demand (workshop.certificate), so a change restyles every certificate
    at once."""

    title = models.CharField(max_length=60, default="Certificate")
    title_tail = models.CharField(max_length=80, default="of Participation")
    intro = models.CharField(max_length=200, default="This is to certify that")
    body = models.TextField(default=CERT_BODY_DEFAULT)
    seal_caption = models.CharField(max_length=24, default="WORKSHOP")

    signatory1_name = models.CharField(max_length=150, blank=True)
    signatory1_title = models.CharField(max_length=150, blank=True, default="Workshop Coordinator")
    signatory1_signature_path = models.CharField(max_length=255, blank=True)

    signatory2_name = models.CharField(max_length=150, blank=True)
    signatory2_title = models.CharField(max_length=150, blank=True)
    signatory2_signature_path = models.CharField(max_length=255, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workshop_certificate_templates"

    def __str__(self):
        return "Workshop Certificate Template"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def signature_url(self, which):
        from . import storage
        path = self.signatory1_signature_path if which == 1 else self.signatory2_signature_path
        return storage.public_url(path) if path else None

    @property
    def signatory1_signature_url(self):
        return self.signature_url(1)

    @property
    def signatory2_signature_url(self):
        return self.signature_url(2)


class Workshop(models.Model):
    """One workshop -- its public page content, schedule, certificate fee and
    its own certificate design. The platform can run many of these: upcoming
    and past ones are all listed on /workshop (the Upcoming Workshops page),
    and each has its own registration page at /workshop/<slug>/.
    """

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    tagline = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    # Display size (px) of the title in the hero on the public workshop page.
    # Used as the max of a responsive clamp, so it scales down on small screens.
    title_font_size = models.PositiveSmallIntegerField(default=30)

    # Schedule. starts_at drives whether registration is open and whether the
    # workshop shows as upcoming or past. registration_closes_at defaults to
    # starts_at when left blank.
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    registration_closes_at = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True)

    # Banner: uploaded image (public "workshop" bucket) wins over a link.
    banner_image_path = models.CharField(max_length=255, blank=True)
    banner_image_link = models.URLField(blank=True)

    # Certificate fee (charged via Paystack when a registrant wants one).
    certificate_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("100.00"))
    fee_currency = models.CharField(max_length=10, default="GHS")

    # Delivered to registrants from the admin page.
    meeting_link = models.URLField(blank=True)
    materials_file_path = models.CharField(max_length=255, blank=True)
    materials_link = models.URLField(blank=True)

    is_published = models.BooleanField(default=True)
    # Manual override to force registration shut regardless of the schedule.
    registration_closed = models.BooleanField(default=False)

    # ---- Per-workshop certificate design -------------------------------
    cert_title_tail = models.CharField(max_length=80, default="of Participation")
    cert_intro = models.CharField(max_length=200, default="This is to certify that")
    cert_body = models.TextField(default=CERT_BODY_DEFAULT)
    cert_seal_caption = models.CharField(max_length=24, default="WORKSHOP")

    cert_sig1_name = models.CharField(max_length=150, blank=True)
    cert_sig1_title = models.CharField(max_length=150, blank=True, default="Workshop Coordinator")
    cert_sig1_signature_path = models.CharField(max_length=255, blank=True)

    cert_sig2_name = models.CharField(max_length=150, blank=True)
    cert_sig2_title = models.CharField(max_length=150, blank=True, default="Workshop Coordinator")
    cert_sig2_signature_path = models.CharField(max_length=255, blank=True)

    # Feature toggles -- add/remove elements of the certificate per workshop.
    cert_show_body = models.BooleanField(default=True)
    cert_show_seal = models.BooleanField(default=True)
    cert_show_second_signature = models.BooleanField(default=True)
    cert_show_verification = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workshops"
        ordering = ["-starts_at", "-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        from django.utils.text import slugify
        base = slugify(self.title) or "workshop"
        slug, i = base, 2
        while Workshop.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f"{base}-{i}"
            i += 1
        return slug[:220]

    # ---- schedule helpers ---------------------------------------------
    @property
    def is_past(self):
        end = self.ends_at or self.starts_at
        return bool(end and timezone.now() > end)

    @property
    def is_upcoming(self):
        return not self.is_past

    @property
    def registration_deadline(self):
        return self.registration_closes_at or self.starts_at

    @property
    def registration_open(self):
        if not self.is_published or self.registration_closed:
            return False
        deadline = self.registration_deadline
        if deadline and timezone.now() > deadline:
            return False
        return True

    @property
    def status_label(self):
        if self.is_past:
            return "Past"
        if self.registration_open:
            return "Registration open"
        return "Upcoming"

    # ---- media helpers ------------------------------------------------
    @property
    def banner_url(self):
        if self.banner_image_path:
            from . import storage
            return storage.public_url(self.banner_image_path)
        return self.banner_image_link or None

    @property
    def materials_download_url(self):
        if self.materials_file_path:
            from . import storage
            return storage.public_url(self.materials_file_path)
        return self.materials_link or None

    @property
    def materials_filename(self):
        return self.materials_file_path.rsplit("/", 1)[-1] if self.materials_file_path else ""

    def cert_signature_url(self, which):
        from . import storage
        path = self.cert_sig1_signature_path if which == 1 else self.cert_sig2_signature_path
        return storage.public_url(path) if path else None

    @property
    def cert_sig1_signature_url(self):
        return self.cert_signature_url(1)

    @property
    def cert_sig2_signature_url(self):
        return self.cert_signature_url(2)


class WorkshopRegistration(models.Model):
    """One person who registered for a workshop (/workshop/<slug>/)."""

    class PaymentStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "No certificate"
        PENDING = "pending", "Payment pending"
        SUCCESS = "success", "Paid"
        FAILED = "failed", "Payment failed"

    workshop = models.ForeignKey(
        "workshop.Workshop", on_delete=models.CASCADE, related_name="registrations",
        null=True, blank=True,
    )

    name = models.CharField(max_length=200)
    institution = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=40, blank=True)
    wants_certificate = models.BooleanField(default=False)
    comments = models.TextField(blank=True)

    # Certificate-fee payment (only when wants_certificate is True).
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.NOT_REQUIRED
    )
    payment_reference = models.CharField(max_length=64, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=10, default="GHS")
    paid_at = models.DateTimeField(null=True, blank=True)
    paystack_response = models.JSONField(blank=True, default=dict)

    # Set the moment the admin emails each item, so the list can show what's
    # already gone out and the admin doesn't double-send.
    meeting_link_sent_at = models.DateTimeField(null=True, blank=True)
    certificate_sent_at = models.DateTimeField(null=True, blank=True)
    materials_sent_at = models.DateTimeField(null=True, blank=True)

    certificate_ref = models.CharField(max_length=60, blank=True)

    # Post-workshop approval: the secretary approves a participant, which
    # issues their documents (certificate for paid participants + a
    # Confirmation of Participation letter), emails them, and texts a unique
    # download link.
    approved_at = models.DateTimeField(null=True, blank=True)
    documents_sent_at = models.DateTimeField(null=True, blank=True)
    # Opaque, unguessable token for the public download link (no login).
    download_token = models.CharField(max_length=64, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "workshop_registrations"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}>"

    @property
    def amount_subunit(self):
        return int(round(self.amount * 100))

    @property
    def is_paid(self):
        return self.payment_status == self.PaymentStatus.SUCCESS

    def ensure_certificate_ref(self):
        if not self.certificate_ref:
            year = (self.paid_at or self.created_at or timezone.now()).year
            self.certificate_ref = f"MSREC/WS/CERT/{year}/{self.pk:04d}"
        return self.certificate_ref

    def ensure_download_token(self):
        if not self.download_token:
            import secrets
            self.download_token = secrets.token_urlsafe(32)
        return self.download_token

    @property
    def participation_ref(self):
        year = (self.approved_at or self.paid_at or self.created_at or timezone.now()).year
        return f"MSREC/WS/PART/{year}/{self.pk:04d}"
