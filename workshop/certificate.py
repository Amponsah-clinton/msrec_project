"""Workshop certificate PDF.

Rendered through the exact same engine as the Peer Review and Committee
(Membership) certificates awarded on the platform -- reviewer_dashboard.
certificate.render_certificate_pdf -- so a workshop certificate is visually
identical to those: the MSREC white edition with the teal lattice border, the
embossed seal, the logo letterhead, and signed by the Chair (whose name,
title and signature come from Site Settings -> Certificates, the one place
every MSREC certificate's signatory is set).

Only the workshop-specific wording differs, and that stays admin-editable in
WorkshopCertificateTemplate: the title tail ("of Participation"), the
certifying sentence, and the seal caption.
"""
from reviewer_dashboard.certificate import render_certificate_pdf


def render_workshop_certificate_pdf(registration, *, tpl=None, ws=None):
    """Returns the certificate PDF bytes for one registration.

    `tpl`/`ws` let the admin preview an *unsaved* design: the editor passes a
    transient WorkshopCertificateTemplate built from the posted fields. When
    omitted, the saved singletons are used (the real issued certificate).
    """
    from .models import WorkshopCertificateTemplate, WorkshopSettings

    tpl = tpl or WorkshopCertificateTemplate.get_solo()
    ws = ws or WorkshopSettings.get_solo()

    cert_id = registration.ensure_certificate_ref()
    issued_at = registration.paid_at or registration.created_at
    message = (tpl.body or "").replace("{workshop}", ws.workshop_title).replace("{name}", registration.name)

    return render_certificate_pdf(
        title_tail=tpl.title_tail or "of Participation",
        recipient_name=registration.name,
        message=message,
        cert_id=cert_id,
        issued_at=issued_at,
        seal_caption=tpl.seal_caption or "WORKSHOP",
    )
