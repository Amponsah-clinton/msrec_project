"""The MSREC Membership Certificate, issued automatically to every approved
Reviewer and Committee member.

One Ethics ID per person (User.membership_ethics_id, see
accounts.models.User.approve_role). The certificate wording follows the
highest role held: Committee membership outranks Reviewer, and the
certificate is re-issued when a Reviewer joins the Committee. Rendered on
demand, never stored, so the Chair's current name, title and signature
(Settings > Certificates) always appear on it.
"""


def is_member(user):
    return bool(getattr(user, "membership_ethics_id", None))


def membership_role(user):
    """("committee" | "reviewer", human label)."""
    from .models import User

    if user.committee_status == User.RequestStatus.APPROVED:
        position = (user.committee_profile or {}).get("committeePosition") or ""
        return "committee", position.strip() or "Committee Member"
    return "reviewer", "Ethics Reviewer"


def certificate_message(user):
    kind, label = membership_role(user)
    if kind == "committee":
        return (
            f"has been confirmed as a Member of the Metascholar Research Ethics Committee, serving as "
            f"{label}, and is entrusted with the independent, impartial and confidential ethical review of "
            f"research, in good standing under the Committee's governing Charter."
        )
    return (
        "has been appointed to the panel of Ethics Reviewers of the Metascholar Research Ethics Committee, "
        "entrusted with the independent, impartial and confidential review of research protocols, in good "
        "standing under the Committee's governing Charter."
    )


def certificate_context(user):
    """Context for templates/certificates/award_certificate.html."""
    from pages.certificate_signatory import chair_details

    return {
        "theme": "white",
        "cert_title": "Certificate",
        "cert_subtitle": "of Membership",
        "seal_caption": "MEMBERSHIP",
        "recipient_name": user.full_name,
        "message": certificate_message(user),
        "cert_id": user.membership_ethics_id,
        "cert_id_label": "Ethics ID",
        "issued_on": user.membership_confirmed_at,
        "chair": chair_details(),
    }


def render_certificate_pdf(user):
    from reviewer_dashboard.certificate import render_certificate_pdf as render

    return render(
        title_tail="of Membership",
        recipient_name=user.full_name,
        message=certificate_message(user),
        cert_id=user.membership_ethics_id,
        issued_at=user.membership_confirmed_at,
        seal_caption="MEMBERSHIP",
        id_label="ETHICS ID",
    )


def certificate_filename(user):
    return f"MSREC-Membership-Certificate-{user.membership_ethics_id.replace('/', '-')}.pdf"
