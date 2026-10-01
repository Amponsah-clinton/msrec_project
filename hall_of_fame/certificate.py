from reviewer_dashboard.certificate import render_certificate_pdf


def render_hof_certificate_pdf(nomination):
    message = (
        "in recognition of distinguished professional contribution, service, "
        "achievement, and commitment to the advancement of research ethics, "
        "scholarship, peer review, academic excellence, mentorship, or "
        "related professional service."
    )
    return render_certificate_pdf(
        title_tail="of Recognition",
        recipient_name=nomination.full_name,
        message=message,
        cert_id=nomination.certificate_ref,
        issued_at=nomination.approved_at,
        seal_caption="HALL OF FAME",
        id_label="HALL OF FAME ID",
    )
