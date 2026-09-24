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




def upload_chair_signature(png_bytes):
    """Upload/replace the Chair's certificate signature (a background-free
    PNG produced by pages/signature.py) into the same "profile" bucket as
    the Client Logos. Every save gets a new, unique object name -- Supabase
    serves an overwritten object from its CDN cache for a while, so reusing
    one fixed name would keep showing the old signature on certificates.
    The caller deletes the previous object once the new one is stored.
    Returns the object path, or None if Storage isn't configured or the
    upload failed."""
    if not png_bytes or not _configured():
        return None

    import uuid

    CHAIR_SIGNATURE_PATH = f"site/chair-signature-{uuid.uuid4().hex[:12]}.png"

    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{CHAIR_SIGNATURE_PATH}"
    req = urllib.request.Request(
        url,
        data=png_bytes,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": "image/png",
            "x-upsert": "true",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status not in (200, 201):
                logger.warning("Supabase Storage upload of %s returned status %s", CHAIR_SIGNATURE_PATH, resp.status)
                return None
    except urllib.error.URLError:
        logger.exception("Supabase Storage upload failed for %s", CHAIR_SIGNATURE_PATH)
        return None

    return CHAIR_SIGNATURE_PATH


def download_object(object_path):
    """Raw bytes of one object in the "profile" bucket (server-side, with the
    service key), or None if unconfigured / missing / the fetch failed --
    callers treat that as "leave it out", never as fatal."""
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


def upload_auth_image(uploaded_file):
    """Upload/replace the image shown beside the Login / Forgot password /
    Reset password forms (SiteSettings.auth_image_path), into the same
    "profile" bucket as the Client Logos. Fixed "site/auth-image.<ext>"
    path -- re-uploading overwrites the previous image (via x-upsert).
    Returns the object path, or None if Storage isn't configured or the
    upload failed.
    """
    if not uploaded_file or not _configured():
        return None

    ext = ""
    if "." in uploaded_file.name:
        ext = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
    object_path = f"site/auth-image{ext}"

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


# Every carousel slide on the landing page's Clients section is displayed
# at this exact box (see .clients .swiper-slide img in main.css) --
# double that CSS size so retina screens don't upscale a blurry image.
# upload_client_logo() below letterboxes whatever an admin uploads onto a
# transparent canvas of this size, so one oversized or oddly-cropped logo
# can never throw off the carousel's row height.
CLIENT_LOGO_SIZE = (320, 140)


def _fit_client_logo(uploaded_file):
    """Return PNG bytes of `uploaded_file` letterboxed onto a transparent
    CLIENT_LOGO_SIZE canvas, preserving its own aspect ratio. Raises on a
    file Pillow can't read as an image -- callers should catch that."""
    from io import BytesIO

    from PIL import Image, ImageOps

    image = Image.open(uploaded_file)
    image = ImageOps.exif_transpose(image).convert("RGBA")
    fitted = ImageOps.contain(image, CLIENT_LOGO_SIZE)
    canvas = Image.new("RGBA", CLIENT_LOGO_SIZE, (0, 0, 0, 0))
    offset = ((CLIENT_LOGO_SIZE[0] - fitted.width) // 2, (CLIENT_LOGO_SIZE[1] - fitted.height) // 2)
    canvas.paste(fitted, offset, fitted)

    buffer = BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def upload_client_logo(uploaded_file, *, logo_id):
    """Upload/replace one Clients-carousel logo (ClientLogo.image_path),
    resizing it to CLIENT_LOGO_SIZE first (see _fit_client_logo() above)
    so it displays at the same size as every other slide regardless of
    what was uploaded. Fixed "clients/<id>/logo.png" path -- re-uploading
    always overwrites the previous image (via x-upsert). Returns the
    object path on success, or None if Storage isn't configured, the
    file isn't a readable image, or the upload failed.
    """
    if not uploaded_file or not _configured():
        return None

    try:
        image_bytes = _fit_client_logo(uploaded_file)
    except Exception:
        logger.exception("Could not process client logo upload")
        return None

    object_path = f"clients/{logo_id}/logo.png"
    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{object_path}"
    req = urllib.request.Request(
        url,
        data=image_bytes,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": "image/png",
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


# Every card in the "Grounded in Recognized Standards" carousel displays
# its photo at 90px wide, circular (see .testimonials .testimonial-img in
# main.css) -- double-plus that for retina screens. upload_testimonial_image()
# below center-crops whatever an admin uploads onto this square so every
# card's avatar reads at the same size and framing.
TESTIMONIAL_IMAGE_SIZE = (240, 240)


def _fit_testimonial_image(uploaded_file):
    """Return JPEG bytes of `uploaded_file` center-cropped to fill a
    TESTIMONIAL_IMAGE_SIZE square -- a circular headshot needs the frame
    fully covered (unlike a logo, which is letterboxed onto transparency),
    so this uses ImageOps.fit rather than _fit_client_logo's contain.
    Raises on a file Pillow can't read as an image -- callers should catch
    that."""
    from io import BytesIO

    from PIL import Image, ImageOps

    image = Image.open(uploaded_file)
    image = ImageOps.exif_transpose(image).convert("RGB")
    fitted = ImageOps.fit(image, TESTIMONIAL_IMAGE_SIZE, method=Image.LANCZOS)

    buffer = BytesIO()
    fitted.save(buffer, format="JPEG", quality=88, optimize=True)
    buffer.seek(0)
    return buffer.getvalue()


def upload_testimonial_image(uploaded_file, *, testimonial_id):
    """Upload/replace one testimonial card's photo (Testimonial.image_path),
    cropping it to TESTIMONIAL_IMAGE_SIZE first (see _fit_testimonial_image()
    above). Fixed "testimonials/<id>/photo.jpg" path -- re-uploading always
    overwrites the previous image (via x-upsert). Returns the object path
    on success, or None if Storage isn't configured, the file isn't a
    readable image, or the upload failed.
    """
    if not uploaded_file or not _configured():
        return None

    try:
        image_bytes = _fit_testimonial_image(uploaded_file)
    except Exception:
        logger.exception("Could not process testimonial image upload")
        return None

    object_path = f"testimonials/{testimonial_id}/photo.jpg"
    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{BUCKET}/{object_path}"
    req = urllib.request.Request(
        url,
        data=image_bytes,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
            "Content-Type": "image/jpeg",
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
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return True  # already gone -- nothing left to delete
        logger.exception("Supabase Storage delete failed for %s", object_path)
        return False
    except urllib.error.URLError:
        logger.exception("Supabase Storage delete failed for %s", object_path)
        return False


def public_url(object_path):
    """A link to an object in the "profile" bucket, proxied through this
    app's own domain (see pages/file_proxy.py) rather than a raw
    Supabase URL. Returns None if unconfigured."""
    from . import file_proxy
    return file_proxy.build_url(BUCKET, object_path)
