"""Supabase Storage integration for the homepage hero image
(SiteSettings.hero_image_path), edited from admin_dashboard's Settings page.

Its own public "hero" bucket rather than reusing pages/storage.py's
"profile" bucket -- the hero image is a distinct, single, large banner
asset (not a per-record photo/logo), so it gets its own bucket the same
way accounts/storage.py's signup uploads get their own "signup" bucket.
Same plain HTTP Storage API approach as every other storage module here --
see accounts/storage.py's docstring for why this doesn't pull in the
`supabase` client package.

If SUPABASE_URL/SUPABASE_SERVICE_KEY aren't configured, every function
here is a no-op that returns None -- a Storage outage must never block
saving Settings; the homepage just keeps showing the bundled static
fallback image (see templates/pages/index.html).
"""
import logging
import mimetypes
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

BUCKET = "hero"


def _configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _content_type_for(uploaded_file):
    return (
        getattr(uploaded_file, "content_type", None)
        or mimetypes.guess_type(uploaded_file.name)[0]
        or "application/octet-stream"
    )


def upload_hero_image(uploaded_file):
    """Upload/replace the homepage hero image.

    Fixed "hero/image.<ext>" path -- there's only ever one, so
    re-uploading always overwrites the previous image (via x-upsert)
    instead of accumulating old copies, same "fixed filename, singleton"
    idea as pages/storage.py's upload_site_logo(). Returns the object
    path on success, or None if Storage isn't configured or the upload
    failed.
    """
    if not uploaded_file or not _configured():
        return None

    ext = ""
    if "." in uploaded_file.name:
        ext = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
    object_path = f"hero/image{ext}"

    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{object_path}"
    req = urllib.request.Request(
        url,
        data=uploaded_file.read(),
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": _content_type_for(uploaded_file),
            "x-upsert": "true",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status not in (200, 201):
                logger.warning("Supabase Storage upload of %s returned status %s", object_path, resp.status)
                return None
    except urllib.error.URLError:
        logger.exception("Supabase Storage upload failed for %s", object_path)
        return None

    return object_path


def delete_object(object_path):
    """Delete one object from the "hero" bucket -- used when the hero
    image is replaced with a different extension. Best-effort: a failure
    here just leaves an unreferenced object in Storage, never blocks the
    Settings save itself."""
    if not object_path or not _configured():
        return False

    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{object_path}"
    req = urllib.request.Request(
        url,
        method="DELETE",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 204)
    except urllib.error.URLError:
        logger.exception("Supabase Storage delete failed for %s", object_path)
        return False


def public_url(object_path):
    """A link to an object in the "hero" bucket, proxied through this
    app's own domain (see pages/file_proxy.py) rather than a raw
    Supabase URL. Returns None if unconfigured."""
    from . import file_proxy
    return file_proxy.build_url(BUCKET, object_path)
