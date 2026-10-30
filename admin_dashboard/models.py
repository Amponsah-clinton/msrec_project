"""Shared uploads: a file put into the private "upload" bucket, and the
one personalised link that reaches it."""
import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


def _new_token():
    return secrets.token_urlsafe(24)


class SharedUpload(models.Model):
    """One uploaded file and the link that shares it.

    The link is the whole of the access control: `token` is 24 random
    bytes, so the address cannot be guessed or walked, and it is the only
    way in -- the bucket itself stays private and no Supabase URL ever
    reaches a browser. That is what makes revoking real: turn the link
    off and the file stops being reachable, even for someone who copied
    the address yesterday.

    `title` is what the uploader typed, and is what the share page shows
    and what the file downloads as. The name the file arrived with is
    kept separately, because it carries the extension the browser needs
    and because it is worth being able to see what was actually sent.
    """

    title = models.CharField(max_length=200)
    # Where it lives in the bucket. Never shown to anyone.
    object_path = models.CharField(max_length=255, unique=True, editable=False)
    token = models.CharField(max_length=64, unique=True, default=_new_token, editable=False)

    original_name = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)

    note = models.CharField(max_length=300, blank=True)
    # Off, the link stops working but the file and its record stay --
    # a withdrawn link is not the same thing as a deleted file.
    is_active = models.BooleanField(default=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Counted rather than logged: who opened a public link is not
    # something this needs to know, only whether it was used at all.
    view_count = models.PositiveIntegerField(default=0)
    download_count = models.PositiveIntegerField(default=0)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "shared_uploads"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    # ---- the link ------------------------------------------------------

    def share_path(self):
        return reverse("uploads:share", kwargs={"token": self.token})

    def share_url(self, request=None):
        """The link to hand out.

        Built from the request's own host when there is one, so a link
        copied on localhost points at localhost and a link copied in
        production points at production. SITE_URL is only the fallback,
        for the places with no request to hand -- it is the deployed
        domain whether or not that is where the code is running, which is
        how a link copied in development ends up pointing at a live site
        that has never heard of the file."""
        if request is not None:
            return request.build_absolute_uri(self.share_path())
        return settings.SITE_URL.rstrip("/") + self.share_path()

    def file_url(self):
        return reverse("uploads:file", kwargs={"token": self.token})

    def download_url(self):
        return self.file_url() + "?download=1"

    # ---- what the share page needs to know -------------------------------

    @property
    def extension(self):
        if "." in (self.original_name or ""):
            return self.original_name.rsplit(".", 1)[-1].upper()[:6]
        return ""

    @property
    def download_name(self):
        """The title, carrying the original extension so the file opens in
        whatever the viewer keeps it in."""
        from .uploads_storage import extension, safe_filename
        stem = safe_filename(self.title) or "file"
        ext = extension(self.original_name)
        return stem if stem.lower().endswith(ext) else f"{stem}{ext}"

    # What may be shown inline, by exact type. An allow-list, not a
    # pattern: "anything image/*" would wave through image/svg+xml, which
    # is a script container, and "anything text/*" would wave through
    # text/html. Both would run on our own domain, with our cookies.
    INLINE_IMAGE = {"image/png", "image/jpeg", "image/gif", "image/webp",
                    "image/avif", "image/bmp", "image/x-icon"}
    INLINE_VIDEO = {"video/mp4", "video/webm", "video/ogg", "video/quicktime"}
    INLINE_AUDIO = {"audio/mpeg", "audio/mp4", "audio/ogg", "audio/wav",
                    "audio/webm", "audio/x-m4a", "audio/aac"}
    INLINE_TEXT = {"text/plain", "text/csv"}

    @property
    def kind(self):
        """What the share page does with it. Anything not on an inline
        list is a "file": offered for download, never rendered."""
        ctype = (self.content_type or "").split(";")[0].strip().lower()
        if ctype in self.INLINE_IMAGE:
            return "image"
        if ctype in self.INLINE_VIDEO:
            return "video"
        if ctype in self.INLINE_AUDIO:
            return "audio"
        if ctype == "application/pdf":
            return "pdf"
        if ctype in self.INLINE_TEXT:
            return "text"
        return "file"

    @property
    def can_preview(self):
        return self.kind != "file"

    @property
    def serve_content_type(self):
        """What we send as the type -- what we recorded at upload, never
        what the fetch reports back, and never anything scriptable for a
        response that will be shown inline."""
        ctype = (self.content_type or "").split(";")[0].strip().lower()
        if self.kind == "file":
            # Downloaded, so the type only has to be honest enough to not
            # tempt a browser into rendering it.
            return "application/octet-stream"
        if self.kind == "text":
            return f"{ctype}; charset=utf-8"
        return ctype

    @property
    def size_display(self):
        size = float(self.size_bytes or 0)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"

    def record_view(self):
        type(self).objects.filter(pk=self.pk).update(
            view_count=models.F("view_count") + 1, last_seen_at=timezone.now())

    def record_download(self):
        type(self).objects.filter(pk=self.pk).update(
            download_count=models.F("download_count") + 1, last_seen_at=timezone.now())
