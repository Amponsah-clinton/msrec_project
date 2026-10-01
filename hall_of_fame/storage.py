import logging
import mimetypes
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

BUCKET = "hall"


def _configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _content_type_for(uploaded_file):
    return (
        getattr(uploaded_file, "content_type", None)
        or mimetypes.guess_type(uploaded_file.name)[0]
        or "application/octet-stream"
    )


def _upload(object_path, data, content_type):
    if not _configured():
        return None
    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{object_path}"
    req = urllib.request.Request(
        url, data=data, method="POST",
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


def upload_nomination_file(uploaded_file, *, nomination_id, kind):
    if not uploaded_file or not _configured():
        return None
    ext = ""
    if "." in uploaded_file.name:
        ext = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
    object_path = f"nominations/{nomination_id}/{kind}{ext}"
    return _upload(object_path, uploaded_file.read(), _content_type_for(uploaded_file))


def upload_photo(uploaded_file, *, nomination_id):
    return upload_nomination_file(uploaded_file, nomination_id=nomination_id, kind="photo")


def upload_cv(uploaded_file, *, nomination_id):
    return upload_nomination_file(uploaded_file, nomination_id=nomination_id, kind="cv")


def upload_activity_report(uploaded_file, *, nomination_id):
    return upload_nomination_file(uploaded_file, nomination_id=nomination_id, kind="activity_report")


def upload_supporting_evidence(uploaded_file, *, nomination_id):
    return upload_nomination_file(uploaded_file, nomination_id=nomination_id, kind="supporting_evidence")


def download_object(object_path):
    if not object_path or not _configured():
        return None
    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{object_path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.URLError:
        logger.exception("Supabase Storage download failed for %s", object_path)
        return None


def create_signed_url(object_path, expires_in=3600):
    if not object_path or not _configured():
        return None
    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/sign/{BUCKET}/{object_path}"
    import json
    body = json.dumps({"expiresIn": expires_in}).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            signed = data.get("signedURL", "")
            if signed.startswith("/"):
                return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1{signed}"
            return signed
    except urllib.error.URLError:
        logger.exception("Supabase Storage signed URL failed for %s", object_path)
        return None


def public_url(object_path):
    if not object_path or not _configured():
        return None
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{BUCKET}/{object_path}"
