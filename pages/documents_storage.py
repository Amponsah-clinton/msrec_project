"""Supabase Storage integration for committee/reviewer document libraries --
meeting packets/minutes (MeetingDocument) and MSREC SOPs / Reviewer
Guidance / Ethics Guidelines (PolicyDocument).

Public "ethics" bucket (same public-bucket-plus-direct-URL pattern as
"profile"/"application"/"team_member" elsewhere in this app) -- every
document here already has its own gate (a reviewer has to be signed in
and land on a reviewer-only page to ever see the link at all), so a
plain public_url() is enough; nothing needs the extra round trip a
signed URL costs. Same plain HTTP Storage API approach as
accounts/storage.py -- see that module's docstring for why this doesn't
pull in the `supabase` client package. If SUPABASE_URL/SUPABASE_SERVICE_KEY
aren't configured, every function here is a no-op that returns None -- a
Storage outage must never block saving a meeting or policy record; the
file is just not attached.
"""
import json
import logging
import mimetypes
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

BUCKET = "ethics"


def _configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _content_type_for(uploaded_file):
    return (
        getattr(uploaded_file, "content_type", None)
        or mimetypes.guess_type(uploaded_file.name)[0]
        or "application/octet-stream"
    )


def upload_document(uploaded_file, *, folder):
    """Upload one document (a meeting packet/minutes, or a policy PDF) to
    Supabase Storage. `folder` groups it under a stable per-record prefix
    (e.g. "meetings/<id>" or "policies/<id>") -- the original filename is
    kept (sanitised) so a download keeps a sensible name. Returns the
    object path on success, or None if Storage isn't configured or the
    upload failed."""
    if not uploaded_file or not _configured():
        return None

    safe_name = uploaded_file.name.replace("/", "_").replace("\\", "_").strip() or "document"
    object_path = f"{folder}/{safe_name}"

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
    """Delete one object from the "committee_documents" bucket (used when
    a document is replaced or its record is deleted). Best-effort: a
    failure here just leaves an unreferenced object in Storage, never
    blocks the surrounding save/delete."""
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
    """Direct public URL for an object in the "ethics" bucket (public,
    like "profile"/"application"/"team_member"). Returns None if
    unconfigured or blank."""
    if not object_path or not settings.SUPABASE_URL:
        return None
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{BUCKET}/{object_path}"
