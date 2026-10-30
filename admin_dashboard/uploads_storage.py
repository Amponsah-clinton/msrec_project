"""Supabase Storage for shared uploads (the private "upload" bucket).

Same stdlib-urllib pattern as workshop/storage.py and hall_of_fame's --
two endpoints is nowhere near enough surface to justify a dependency.

The bucket is private on purpose. Nothing here ever hands a Supabase URL
to a browser: the file is fetched with the service key and streamed back
through this app's own share link, so the only address that exists for a
file is the one we minted, and revoking that link really does stop the
file being reachable. A public bucket URL, once copied, would outlive any
switch we own.
"""
import logging
import mimetypes
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

BUCKET = "upload"

# Read in one go -- what gets shared here is a document or a short video,
# not an archive. The form refuses anything larger before it reaches us.
MAX_BYTES = 100 * 1024 * 1024


def _configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def _object_url(object_path):
    encoded = urllib.parse.quote(object_path, safe="/")
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{encoded}"


def _headers(**extra):
    return {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
        "apikey": settings.SUPABASE_SERVICE_KEY,
        **extra,
    }


def safe_filename(name):
    """A storage-safe filename: no spaces or characters that break a URL."""
    name = (name or "").replace("/", "_").replace("\\", "_").strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "file"
    return name[:150]


def content_type_for(uploaded_file):
    return (
        getattr(uploaded_file, "content_type", None)
        or mimetypes.guess_type(uploaded_file.name)[0]
        or "application/octet-stream"
    )


def extension(filename):
    if "." in (filename or ""):
        return "." + filename.rsplit(".", 1)[-1].lower()[:12]
    return ""


def upload(object_path, data, content_type):
    """The stored path on success, None on any failure."""
    if not _configured():
        logger.warning("Upload skipped: Supabase Storage is not configured")
        return None
    req = urllib.request.Request(
        _object_url(object_path), data=data, method="POST",
        headers=_headers(**{"Content-Type": content_type, "x-upsert": "true"}),
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            if resp.status not in (200, 201):
                logger.warning("Upload of %s returned status %s", object_path, resp.status)
                return None
    except Exception:
        logger.exception("Supabase upload failed for %s", object_path)
        return None
    return object_path


def download(object_path):
    """(bytes, content_type) or (None, None). The content type Supabase
    reports wins over anything we guessed at upload time."""
    if not object_path or not _configured():
        return None, None
    req = urllib.request.Request(_object_url(object_path), headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read(), resp.headers.get("Content-Type")
    except Exception:
        logger.exception("Supabase download failed for %s", object_path)
        return None, None


def delete(object_path):
    if not object_path or not _configured():
        return False
    req = urllib.request.Request(_object_url(object_path), method="DELETE", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 204)
    except urllib.error.HTTPError as exc:
        # Already gone is the outcome we wanted.
        return exc.code == 404
    except Exception:
        logger.exception("Supabase delete failed for %s", object_path)
        return False
