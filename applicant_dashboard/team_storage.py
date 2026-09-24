"""Supabase Storage integration for Research Team member photos.

Its own bucket ("team_member", public) rather than reusing the
"application" bucket applicant_dashboard/storage.py already owns -- a
team member's photo isn't part of any one application submission, it
belongs to the applicant's own research-team address book, so it gets its
own small storage module, the same "one bucket, one module" convention as
pages/storage.py ("profile") and accounts/storage.py ("signup"). See that
module's docstring for why this talks to Supabase's plain HTTP Storage API
rather than the `supabase` client package.

If SUPABASE_URL/SUPABASE_SERVICE_KEY aren't configured, every function
here is a no-op that returns None -- a Storage outage or missing config
must never block saving a team member; the photo is just not attached.

The "team_member" bucket itself is not created by this file or by
supabase/schema.sql (Supabase Storage buckets are provisioned from the
Supabase dashboard or its API, never SQL) -- create it once, as public,
from Storage > New bucket in the Supabase dashboard before this module's
uploads can succeed.
"""
import logging
import mimetypes
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

BUCKET = "team_member"


def _configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _content_type_for(uploaded_file):
    return (
        getattr(uploaded_file, "content_type", None)
        or mimetypes.guess_type(uploaded_file.name)[0]
        or "application/octet-stream"
    )


def upload_team_photo(uploaded_file, *, member_id):
    """Upload/replace a research-team member's photo.

    Fixed filename per member (team/<member id>/photo.<ext>) -- re-
    uploading always overwrites the previous photo (via x-upsert) instead
    of accumulating old copies. Returns the object path on success, or
    None if Storage isn't configured or the upload failed.
    """
    if not uploaded_file or not _configured():
        return None

    ext = ""
    if "." in uploaded_file.name:
        ext = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
    object_path = f"team/{member_id}/photo{ext}"

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
    """Delete one object from the "team_member" bucket (used when a photo
    is replaced or a team member is removed). Best-effort: a failure here
    just leaves an unreferenced object in Storage, never blocks the
    surrounding save/delete."""
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
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return True  # already gone -- nothing left to delete
        logger.exception("Supabase Storage delete failed for %s", object_path)
        return False
    except urllib.error.URLError:
        logger.exception("Supabase Storage delete failed for %s", object_path)
        return False


def public_url(object_path):
    """A link to an object in the "team_member" bucket (public, like
    "application"/"profile"), proxied through this app's own domain (see
    pages/file_proxy.py) rather than a raw Supabase URL. Returns None if
    unconfigured or blank."""
    from pages import file_proxy
    return file_proxy.build_url(BUCKET, object_path)
