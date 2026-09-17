"""Supabase Storage integration for the public Resource Centre page
(ResourceDocument: Application Forms, Protocol Templates, Consent
Templates, Reporting Forms, Guidelines, FAQs, Training).

Own "resources" bucket, public -- same plain HTTP Storage API approach as
accounts/storage.py, pages/storage.py and pages/documents_storage.py (see
those modules' docstrings for why this doesn't pull in the `supabase`
client package). If SUPABASE_URL/SUPABASE_SERVICE_KEY aren't configured,
every function here is a no-op that returns None -- a Storage outage must
never block saving a resource; the file is just not attached.
"""
import logging
import mimetypes
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

BUCKET = "resources"


def _configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _content_type_for(uploaded_file):
    return (
        getattr(uploaded_file, "content_type", None)
        or mimetypes.guess_type(uploaded_file.name)[0]
        or "application/octet-stream"
    )


def upload_document(uploaded_file, *, folder):
    """Upload one resource file (PDF/DOCX/etc.) to Supabase Storage.
    `folder` groups it under a stable per-record prefix (e.g.
    "application_forms/<id>") -- the original filename is kept
    (sanitised) so a download keeps a sensible name. Returns the object
    path on success, or None if Storage isn't configured or the upload
    failed."""
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
    """Delete one object from the "resources" bucket (used when a
    resource's file is replaced or the record is deleted). Best-effort: a
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
    """A link to an object in the "resources" bucket, proxied through
    this app's own domain (see pages/file_proxy.py) rather than a raw
    Supabase URL -- never expires, matching this bucket's actual public
    access. Returns None if unconfigured or blank."""
    from . import file_proxy
    return file_proxy.build_url(BUCKET, object_path)
