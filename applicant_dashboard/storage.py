"""Supabase Storage integration for application-form document uploads.

Every submission of templates/dashboards/applicant/application-form.html
can attach any number of supporting documents (protocol, consent forms,
CVs, etc). Those files are uploaded here to the "application" bucket in
Supabase Storage, keyed under a per-application folder, the same pattern
accounts/storage.py uses for the signup bucket -- see that module's
docstring for why this talks to Supabase's plain HTTP Storage API rather
than the `supabase` client package.

If SUPABASE_URL/SUPABASE_SERVICE_KEY aren't configured, every function
here is a no-op that returns None -- a Storage outage or missing config
must never block someone from submitting their application; the affected
file is just not attached.
"""
import json
import logging
import mimetypes
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

BUCKET = "application"


def _configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _upload_bytes(object_path, data, content_type):
    """Shared PUT-an-object call behind upload_application_file() and
    upload_avatar_file(). Returns `object_path` on success, None on any
    failure (unconfigured, network error, non-2xx response)."""
    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{object_path}"
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": content_type,
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


def _content_type_for(uploaded_file):
    return (
        getattr(uploaded_file, "content_type", None)
        or mimetypes.guess_type(uploaded_file.name)[0]
        or "application/octet-stream"
    )


def upload_application_file(uploaded_file, *, folder):
    """Upload one application-form document to Supabase Storage.

    `uploaded_file` is a Django UploadedFile (from request.FILES).
    `folder` groups every file from the same application submission
    together (a per-request uuid -- see applicant_dashboard/views.py).

    Returns the object's storage path (e.g. "3f2a.../protocol.pdf") on
    success, or None if Storage isn't configured or the upload failed.
    """
    if not uploaded_file or not _configured():
        return None

    safe_name = uploaded_file.name.replace("/", "_").replace("\\", "_").strip() or "document"
    object_path = f"{folder}/{safe_name}"
    return _upload_bytes(object_path, uploaded_file.read(), _content_type_for(uploaded_file))


def upload_avatar_file(uploaded_file, *, user_id):
    """Upload/replace a profile photo from profile-security.html.

    Lives in this same public "application" bucket (not the private
    "signup" bucket accounts/storage.py uses for the photo attached at
    signup) under its own avatars/<user id>/ prefix, at a fixed filename
    per user -- re-uploading always overwrites the previous photo (via
    x-upsert) instead of accumulating old copies. Returns the object path
    (e.g. "avatars/42/avatar.jpg") on success, or None if Storage isn't
    configured or the upload failed.
    """
    if not uploaded_file or not _configured():
        return None

    ext = ""
    if "." in uploaded_file.name:
        ext = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
    object_path = f"avatars/{user_id}/avatar{ext}"
    return _upload_bytes(object_path, uploaded_file.read(), _content_type_for(uploaded_file))


def delete_object(object_path):
    """Delete one object from the "application" bucket (used when an
    applicant removes their profile photo). Best-effort: a failure here
    just leaves an unreferenced object in Storage, never blocks the
    account-side removal (see applicant_dashboard/views.py)."""
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
    """Direct public URL for an object in the "application" bucket (the
    bucket is public, unlike "signup"). Returns None if unconfigured."""
    if not object_path or not settings.SUPABASE_URL:
        return None
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{BUCKET}/{object_path}"


def create_signed_url(object_path, *, expires_in=3600):
    """Temporary signed URL for an object in the "application" bucket, or
    None if Storage isn't configured, the object doesn't exist, or the
    request fails. Not usually needed since the bucket is public, but kept
    for parity with accounts/storage.py in case the bucket is later made
    private."""
    if not object_path or not _configured():
        return None

    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/sign/{BUCKET}/{object_path}"
    req = urllib.request.Request(
        url,
        data=f'{{"expiresIn": {int(expires_in)}}}'.encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read())
    except urllib.error.URLError:
        logger.exception("Supabase Storage sign failed for %s", object_path)
        return None

    signed = payload.get("signedURL") or payload.get("signedUrl")
    if not signed:
        return None
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1{signed}"
