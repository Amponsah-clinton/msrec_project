"""Supabase Storage integration for signup-form file uploads.

Every account created via templates/pages/signup.html can attach a
profile photo, and (depending on which roles were selected) a CV/résumé
for the Reviewer and/or Committee Member role. Those files are uploaded
here to the private "signup" bucket in Supabase Storage, keyed under a
per-signup folder, rather than through Django's local MEDIA storage --
the project already treats Supabase as the durable store (see
SUPABASE_URL/SUPABASE_SERVICE_KEY in config/settings.py), and file
uploads are the one part of signup that never belonged in the SQL
database itself.

Talks to Supabase's plain HTTP Storage API (stdlib urllib) rather than
adding the `supabase` package as a dependency -- signup only needs two
calls (upload an object, sign a URL to view one later), which is a much
smaller surface than pulling in the full client SDK for.

If SUPABASE_URL/SUPABASE_SERVICE_KEY aren't configured (e.g. local dev
with only DATABASE_URL unset, using SQLite), every function here is a
no-op that returns None -- signup must never fail because Storage isn't
configured; the file is just not attached.
"""
import json
import logging
import mimetypes
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

BUCKET = "signup"


def _configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def upload_signup_file(uploaded_file, *, folder, field_name):
    """Upload one signup-form file to Supabase Storage.

    `uploaded_file` is a Django UploadedFile (from request.FILES).
    `folder` groups every file from the same signup submission together
    (a per-request uuid — see accounts/views.py). `field_name` (e.g.
    "profilePhoto", "reviewerCv") becomes part of the object name so the
    bucket stays human-readable.

    Returns the object's storage path (e.g.
    "3f2a.../reviewerCv.pdf") on success, or None if Storage isn't
    configured or the upload failed -- callers must treat None as
    "no file attached" and keep going; a Storage outage should never
    block someone from creating an account.
    """
    if not uploaded_file or not _configured():
        return None

    ext = ""
    if "." in uploaded_file.name:
        ext = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
    object_path = f"{folder}/{field_name}{ext}"

    content_type = (
        getattr(uploaded_file, "content_type", None)
        or mimetypes.guess_type(uploaded_file.name)[0]
        or "application/octet-stream"
    )

    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{object_path}"
    data = uploaded_file.read()

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
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status not in (200, 201):
                logger.warning("Supabase Storage upload of %s returned status %s", object_path, resp.status)
                return None
    except urllib.error.URLError:
        logger.exception("Supabase Storage upload failed for %s", object_path)
        return None

    return object_path


def create_signed_url(object_path, *, expires_in=3600):
    """Return a temporary signed URL for a private object in the
    "signup" bucket, or None if Storage isn't configured, the object
    doesn't exist, or the request fails. Used by admin_dashboard's
    Accounts page to let an admin open an applicant's CV while
    reviewing a reviewer/committee request."""
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
