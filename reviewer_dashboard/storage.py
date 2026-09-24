"""Supabase Storage integration for reviewer profile assets.

Reviewer profile photos (changed from Profile & Expertise) live in their
own public "profile" bucket in Supabase Storage, under a per-user
`reviewers/<id>/` prefix -- kept separate from applicant_dashboard's
"application" bucket (used for applicant avatars and application
documents) so a reviewer's account assets have their own home, and so
admin_dashboard's storage cleanup can tell the two apart purely from the
object path's prefix (see admin_dashboard.views._cleanup_user_storage and
accounts.context_processors.profile_avatar, which both branch on
"reviewers/" vs "avatars/" vs anything else).

Same plain HTTP Storage API approach as accounts/storage.py and
applicant_dashboard/storage.py -- see accounts/storage.py's docstring for
why this doesn't pull in the `supabase` client package. If
SUPABASE_URL/SUPABASE_SERVICE_KEY aren't configured, every function here
is a no-op that returns None -- a Storage outage must never block a
reviewer from saving their profile; the photo is just not attached.
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


def upload_avatar_file(uploaded_file, *, user_id):
    """Upload/replace a reviewer's profile photo.

    Fixed filename per user under reviewers/<user id>/ -- re-uploading
    always overwrites the previous photo (via x-upsert) instead of
    accumulating old copies. Returns the object path (e.g.
    "reviewers/42/avatar.jpg") on success, or None if Storage isn't
    configured or the upload failed.
    """
    if not uploaded_file or not _configured():
        return None

    ext = ""
    if "." in uploaded_file.name:
        ext = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
    object_path = f"reviewers/{user_id}/avatar{ext}"

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
    """Delete one object from the "profile" bucket (used when a reviewer
    removes their photo, or admin_dashboard deletes their account).
    Best-effort: a failure here just leaves an unreferenced object in
    Storage, never blocks the account-side action."""
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
    """A link to an object in the "profile" bucket (public, like
    "application" -- unlike the private "signup" bucket), proxied
    through this app's own domain (see pages/file_proxy.py) rather than
    a raw Supabase URL. Returns None if unconfigured."""
    from pages import file_proxy
    return file_proxy.build_url(BUCKET, object_path)
