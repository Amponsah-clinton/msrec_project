"""The one person named on every awarded certificate: the Chair.

Details come from Settings > Certificates (SiteSettings.chair_name /
chair_title / chair_signature_path), so changing them there restyles every
certificate at once -- past and future -- because certificates are always
rendered on demand rather than stored. If no name has been entered yet it
falls back to the active Chair account's name, and if there is none either
the certificate shows a bare line to sign by hand.
"""
from accounts.models import User

DEFAULT_TITLE = "Chair of the Committee"


def chair_details():
    """dict(name, title, signature_url, signature_path)."""
    from .models import SiteSettings

    site = SiteSettings.get_solo()
    name = (site.chair_name or "").strip()
    if not name:
        chair = User.objects.filter(role=User.Role.CHAIR, is_active=True).order_by("pk").first()
        name = chair.full_name if chair else ""
    return {
        "name": name,
        "title": (site.chair_title or "").strip() or DEFAULT_TITLE,
        "signature_url": site.chair_signature_url,
        "signature_path": site.chair_signature_path,
    }


def chair_signature_bytes(details=None):
    """The signature PNG's bytes for the PDF renderer, or None."""
    from . import storage

    details = details or chair_details()
    return storage.download_object(details["signature_path"])
