"""Supabase Storage for the workshop (public "workshop" bucket): the banner
image, the materials file and the certificate signature images. Same stdlib-
urllib pattern as hall_of_fame/storage.py."""
import logging
import mimetypes
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

BUCKET = "workshop"


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
                logger.warning("Workshop upload of %s returned status %s", object_path, resp.status)
                return None
    except urllib.error.URLError:
        logger.exception("Workshop Storage upload failed for %s", object_path)
        return None
    return object_path


def _ext(uploaded_file):
    if "." in uploaded_file.name:
        return "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
    return ""


def upload_banner(uploaded_file):
    if not uploaded_file or not _configured():
        return None
    object_path = f"banner/banner{_ext(uploaded_file)}"
    return _upload(object_path, uploaded_file.read(), _content_type_for(uploaded_file))


def upload_materials(uploaded_file):
    if not uploaded_file or not _configured():
        return None
    safe = uploaded_file.name.replace("/", "_").replace("\\", "_").strip() or "materials"
    object_path = f"materials/{safe}"
    return _upload(object_path, uploaded_file.read(), _content_type_for(uploaded_file))


def upload_signature(uploaded_file, *, which):
    if not uploaded_file or not _configured():
        return None
    object_path = f"signatures/signatory{which}{_ext(uploaded_file)}"
    return _upload(object_path, uploaded_file.read(), _content_type_for(uploaded_file))


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
        logger.exception("Workshop Storage download failed for %s", object_path)
        return None


def delete_object(object_path):
    if not object_path or not _configured():
        return False
    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{object_path}"
    req = urllib.request.Request(
        url, method="DELETE",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 204)
    except urllib.error.HTTPError as exc:
        return exc.code == 404
    except urllib.error.URLError:
        logger.exception("Workshop Storage delete failed for %s", object_path)
        return False


def public_url(object_path):
    if not object_path or not _configured():
        return None
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{BUCKET}/{object_path}"
