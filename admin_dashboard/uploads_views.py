"""The Upload page, and the share link each upload gets.

Two audiences, two rules:

  * /admins/upload/ is staff only: upload a file under a name you choose,
    copy its link, turn a link off, delete a file for good.
  * /u/<token>/ is open to anyone holding the link. It shows the file
    where a browser can show it -- images, PDFs, video, audio, plain text
    -- and offers it for download either way.

The file itself is never served from Supabase directly. /u/<token>/file/
fetches it with the service key and streams it back, so the bucket stays
private, the only address in existence is the one we minted, and turning
a link off actually stops the file being reachable.
"""
import logging
import secrets
import urllib.parse

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from messaging.access import is_staff_side

from . import uploads_storage as storage
from .models import SharedUpload

logger = logging.getLogger(__name__)

staff_required = user_passes_test(is_staff_side, login_url="pages:login")

MAX_BYTES = storage.MAX_BYTES
TITLE_MAX = 200


def _clean_title(raw, fallback):
    title = " ".join((raw or "").split())[:TITLE_MAX]
    return title or " ".join((fallback or "").split())[:TITLE_MAX] or "Untitled file"


# ---------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------

@login_required
@staff_required
def uploads(request):
    """The Upload page: the form, and everything shared so far."""
    if request.method == "POST":
        return _handle(request)

    rows = list(SharedUpload.objects.select_related("uploaded_by"))
    for row in rows:
        # Resolved against this request, so the link you copy is a link
        # that works from where you are.
        row.link = row.share_url(request)
    return render(request, "dashboards/admin/uploads.html", {
        "uploads": rows,
        "total": len(rows),
        "live": sum(1 for r in rows if r.is_active),
        "max_mb": MAX_BYTES // (1024 * 1024),
        "configured": storage._configured(),
        "active": "uploads",
    })


def _handle(request):
    action = request.POST.get("action", "upload")
    if action == "upload":
        return _add(request)

    pk = request.POST.get("id", "")
    if not pk.isdigit():
        return redirect("admin_dashboard:uploads")
    row = get_object_or_404(SharedUpload, pk=int(pk))

    if action == "toggle":
        row.is_active = not row.is_active
        row.save(update_fields=["is_active"])
        messages.success(request, (
            f"“{row.title}” is shareable again." if row.is_active else
            f"“{row.title}” is no longer reachable — the link stops working for everyone who has it."
        ))
    elif action == "rename":
        row.title = _clean_title(request.POST.get("title"), row.title)
        row.save(update_fields=["title"])
        messages.success(request, f"Renamed to “{row.title}”.")
    elif action == "relink":
        # A new address for a link that got out. The old one dies with it.
        row.token = secrets.token_urlsafe(24)
        row.save(update_fields=["token"])
        messages.success(request, f"“{row.title}” has a new link. The old one no longer works.")
    elif action == "delete":
        title = row.title
        if not storage.delete(row.object_path):
            logger.warning("Upload %s left in the bucket after delete", row.object_path)
        row.delete()
        messages.success(request, f"“{title}” deleted — the file is gone from storage too.")
    return redirect("admin_dashboard:uploads")


def _add(request):
    uploaded = request.FILES.get("file")
    if not uploaded:
        messages.error(request, "Choose a file to upload.")
        return redirect("admin_dashboard:uploads")
    if uploaded.size > MAX_BYTES:
        messages.error(
            request,
            f"That file is {uploaded.size / 1024 / 1024:.0f} MB. The limit is "
            f"{MAX_BYTES // (1024 * 1024)} MB.",
        )
        return redirect("admin_dashboard:uploads")
    if not storage._configured():
        messages.error(request, "File storage isn't configured on this server, so nothing was uploaded.")
        return redirect("admin_dashboard:uploads")

    title = _clean_title(request.POST.get("title"), uploaded.name)
    # Dated folder, random stem: two files called report.pdf never collide,
    # and the stored path says nothing a guess could use.
    stamp = timezone.now()
    stem = secrets.token_hex(8)
    object_path = (
        f"{stamp:%Y/%m}/{stem}{storage.extension(uploaded.name)}"
    )
    content_type = storage.content_type_for(uploaded)
    stored = storage.upload(object_path, uploaded.read(), content_type)
    if not stored:
        messages.error(request, "The upload didn't reach storage. Try again, or check the storage settings.")
        return redirect("admin_dashboard:uploads")

    row = SharedUpload.objects.create(
        title=title, object_path=stored, original_name=uploaded.name[:255],
        content_type=content_type, size_bytes=uploaded.size,
        note=" ".join((request.POST.get("note") or "").split())[:300],
        uploaded_by=request.user,
    )
    messages.success(request, f"“{row.title}” uploaded. Its link is ready to share.")
    return redirect(f"{request.path}?new={row.pk}")


# ---------------------------------------------------------------------
# Anyone holding the link
# ---------------------------------------------------------------------

def _live(token):
    row = get_object_or_404(SharedUpload, token=token)
    if not row.is_active:
        raise Http404("This link is no longer active.")
    return row


def share(request, token):
    """The page the link opens: the file shown where it can be, and a
    download either way."""
    row = _live(token)
    row.record_view()
    resp = render(request, "uploads/share.html", {"item": row})
    # A shared link is not for caches to keep, and no third-party asset on
    # the page should learn the address.
    resp["Cache-Control"] = "no-store"
    resp["Referrer-Policy"] = "same-origin"
    resp["X-Robots-Tag"] = "noindex, nofollow"
    return resp


def file(request, token):
    """The bytes.

    Inline only for the kinds a browser can show without running
    anything: see SharedUpload.can_preview. Everything else downloads,
    whatever the viewer asks for.

    This matters more than it looks. The file comes back from *our*
    domain, so an uploaded .html or .svg served inline would run its
    script on our origin, with our cookies -- a staff upload page turned
    into stored XSS against whoever opens the link while signed in.
    Three things stop that: the content type is never inherited from the
    uploader (we send what we recorded), anything scriptable is forced to
    download, and every response carries a sandbox policy so even a type
    we misjudged lands in an opaque origin with no script and no access
    to anything of ours."""
    row = _live(token)
    data, _reported = storage.download(row.object_path)
    if data is None:
        raise Http404("That file is no longer in storage.")

    inline = row.can_preview and request.GET.get("download") != "1"
    if not inline:
        row.record_download()

    resp = HttpResponse(data, content_type=row.serve_content_type)
    name = row.download_name
    # Quoted and RFC 5987-encoded, so a title with a space or an accent
    # arrives whole instead of being cut at the first space.
    resp["Content-Disposition"] = (
        f'{"inline" if inline else "attachment"}; filename="{name}"; '
        f"filename*=UTF-8''{urllib.parse.quote(name)}"
    )
    resp["Content-Length"] = len(data)
    resp["Cache-Control"] = "no-store"
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'; media-src 'self'"
    resp["X-Robots-Tag"] = "noindex, nofollow"
    return resp
