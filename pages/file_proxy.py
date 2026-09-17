"""Every Storage module's public_url()/create_signed_url() builds its
download link through here instead of returning a raw Supabase URL
directly. Without this, any downloaded file or `<img src>` reveals this
project's Supabase host (https://<project-ref>.supabase.co/storage/...)
in the browser's address bar, page source, and network tab -- an
infrastructure detail nothing in the UI should ever expose. Every link
this produces instead points back at this app's own domain
(/files/<token>/); this module's serve() view is what actually fetches
the bytes server-side (with the service key, so it works for a private
bucket exactly the same way it works for a public one) and streams them
back under our own host.

The token is signed (django.core.signing, keyed off SECRET_KEY) so a
client can't forge one for an arbitrary bucket/path, and expiring links
(the create_signed_url() call sites) carry their own expiry timestamp
inside the payload, checked in serve() -- but it is signing, not
encryption: a base64 decode of a token a client already holds would
reveal the bucket and object path in plain text. That's an accepted
trade-off here, not an oversight -- the thing this module exists to hide
is the Supabase *host*, since that's the one piece of infrastructure
detail with no legitimate reason to ever reach a browser. Nothing in
this system relies on an object path being unguessable as its actual
access control (private buckets are private because Supabase's REST API
refuses anon/public reads of them, not because the path is a secret);
what actually gated a private object before this module existed was a
short-lived Supabase-issued signed URL, and that same short lifetime is
preserved here for every create_signed_url() call site.
"""
import logging
import mimetypes
import time
import urllib.error
import urllib.request

from django.conf import settings
from django.core import signing
from django.http import Http404, HttpResponse
from django.urls import reverse

logger = logging.getLogger(__name__)

SALT = "pages.file_proxy"


def _configured():
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY)


def build_url(bucket, object_path, *, expires_in=None):
    """The one place every storage module's public_url()/
    create_signed_url() gets its link from. `expires_in` (seconds) makes
    this behave like a Supabase signed URL -- the link itself stops
    resolving after that long, checked in serve() below -- omit it for
    what used to be a public, never-expiring URL. Returns None under the
    exact same conditions the old direct-URL builders did (no object
    path, or Storage unconfigured), so every existing "no file yet"
    template check (`{% if x.photo_url %}`) keeps working unchanged.
    """
    if not object_path or not _configured():
        return None

    payload = {"b": bucket, "p": object_path}
    if expires_in is not None:
        payload["exp"] = time.time() + expires_in

    token = signing.dumps(payload, salt=SALT)
    return reverse("pages:file_proxy", kwargs={"token": token})


def _fetch(bucket, object_path):
    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket}/{object_path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
            "apikey": settings.SUPABASE_SERVICE_KEY,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read(), resp.headers.get("Content-Type")


def serve(request, token):
    """The view every /files/<token>/ URL hits. Verifies the signature
    (and expiry, for a link built with expires_in), fetches the object
    server-side, and streams it back -- the only Supabase URL ever
    contacted here is contacted by this server, never sent to the
    browser."""
    try:
        payload = signing.loads(token, salt=SALT)
    except signing.BadSignature:
        raise Http404("Invalid file link.")

    bucket = payload.get("b")
    object_path = payload.get("p")
    if not bucket or not object_path:
        raise Http404("Invalid file link.")

    expires_at = payload.get("exp")
    if expires_at is not None and time.time() > expires_at:
        raise Http404("This link has expired.")

    try:
        content, content_type = _fetch(bucket, object_path)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise Http404("File not found.")
        logger.warning("File proxy fetch of %s/%s returned HTTP %s", bucket, object_path, exc.code)
        raise Http404("Could not retrieve file.")
    except urllib.error.URLError:
        logger.exception("File proxy fetch failed for %s/%s", bucket, object_path)
        raise Http404("Could not retrieve file.")

    filename = object_path.rsplit("/", 1)[-1]
    content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"

    response = HttpResponse(content, content_type=content_type)
    # inline (not attachment): a photo/logo should render in an <img>
    # tag, a PDF should open in the browser's own viewer -- exactly how
    # the raw Supabase URL behaved before. The browser's own "Save As"
    # still works from either; this only affects the default click
    # behavior, not whether it can be saved.
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    # Never cached by a shared/public cache -- an expiring link (a
    # private CV, a revision document) must not end up stored in a
    # proxy or CDN in front of this app; the browser's own cache for
    # this one visitor is still fine.
    response["Cache-Control"] = "private, max-age=3600"
    return response
