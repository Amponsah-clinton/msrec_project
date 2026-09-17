"""Supabase Storage integration for Board & Committee member photos.

Same public "profile" bucket reviewer_dashboard/storage.py already uses
for reviewer avatars, under a separate "governance/<member id>/" prefix
so admin_dashboard's per-user storage cleanup (which branches on the
object path's prefix) never confuses the two. Same plain HTTP Storage
API approach as accounts/storage.py -- see that module's docstring for
why this doesn't pull in the `supabase` client package. If
SUPABASE_URL/SUPABASE_SERVICE_KEY aren't configured, every function here
is a no-op that returns None -- a Storage outage must never block saving
a Board & Committee member; the photo is just not attached.
"""
import logging
import mimetypes
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

BUCKET = "profile"


def _configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _content_type_for(uploaded_file):
    return (
        getattr(uploaded_file, "content_type", None)
        or mimetypes.guess_type(uploaded_file.name)[0]
        or "application/octet-stream"
    )


def upload_member_photo(uploaded_file, *, member_id):
    """Upload/replace a Board & Committee member's photo.

    Fixed filename per member under governance/<id>/ -- re-uploading
    always overwrites the previous photo (via x-upsert) instead of
    accumulating old copies. Returns the object path on success, or None
    if Storage isn't configured or the upload failed.
    """
    if not uploaded_file or not _configured():
        return None

    ext = ""
    if "." in uploaded_file.name:
        ext = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
    object_path = f"governance/{member_id}/photo{ext}"

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


def upload_site_logo(uploaded_file):
    """Upload/replace the site's logo (SiteSettings.logo_path).

    Fixed "site/logo.<ext>" path -- there's only ever one, so re-uploading
    always overwrites the previous logo (via x-upsert) instead of
    accumulating old copies, the same "fixed filename, singleton" idea as
    upload_member_photo() above but with no id to key on. Returns the
    object path on success, or None if Storage isn't configured or the
    upload failed.
    """
    if not uploaded_file or not _configured():
        return None

    ext = ""
    if "." in uploaded_file.name:
        ext = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
    object_path = f"site/logo{ext}"

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
    """Delete one object from the "profile" bucket (used when a member's
    photo is replaced with a different extension, or the member is
    deleted). Best-effort: a failure here just leaves an unreferenced
    object in Storage, never blocks the admin-side action."""
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
    """A link to an object in the "profile" bucket, proxied through this
    app's own domain (see pages/file_proxy.py) rather than a raw
    Supabase URL. Returns None if unconfigured."""
    from . import file_proxy
    return file_proxy.build_url(BUCKET, object_path)
