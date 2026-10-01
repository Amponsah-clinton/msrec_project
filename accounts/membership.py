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


def appointment_letter_filename(user):
    from .appointment import letter_filename

    return letter_filename(user)


def render_appointment_letter_pdf(user):
    """One-page appointment letter, issued alongside the Membership
    Certificate when a Reviewer/Committee request is approved (see
    admin_dashboard.views._send_role_approved_email). Wording, letterhead
    and signatory are edited in Site Settings > Appointment Letter; see
    accounts/appointment.py."""
    from .appointment import render_letter_pdf

    return render_letter_pdf(user)


def personal_documents_context(user):
    """Everything the Reviewer/Committee "My Documents" page needs: the
    member's identity header and the list of credential documents issued to
    them (appointment letter + membership certificate), with URLs resolved.

    Both the appointment letter and certificate are rendered on demand from
    the member's record (see accounts.views.appointment_letter /
    membership_certificate), so they always reflect the current signatory --
    this page simply links to those existing downloads in one place.
    """
    from django.urls import reverse

    member = is_member(user)
    kind, role_label = membership_role(user)
    documents = []
    if member:
        documents = [
            {
                "key": "appointment_letter",
                "title": "Appointment Letter",
                "description": (
                    "Your official MSREC letter of appointment confirming your role, "
                    "Ethics ID and effective date, signed by the Chair."
                ),
                "kind_label": "PDF",
                "icon": "letter",
                "accent": "navy",
                "open_url": reverse("pages:appointment_letter"),
                "download_url": reverse("pages:appointment_letter"),
                "issued_on": getattr(user, "membership_confirmed_at", None),
            },
            {
                "key": "membership_certificate",
                "title": "Membership Certificate",
                "description": (
                    "Your certificate of membership of the Metascholar Research Ethics "
                    "Committee, confirming you are in good standing under its Charter."
                ),
                "kind_label": "Certificate",
                "icon": "certificate",
                "accent": "teal",
                "open_url": reverse("pages:membership_certificate"),
                "download_url": reverse("pages:membership_certificate") + "?format=pdf",
                "issued_on": getattr(user, "membership_confirmed_at", None),
            },
        ]

    return {
        "is_member": member,
        "doc_role_kind": kind,
        "doc_role_label": role_label,
        "doc_ethics_id": getattr(user, "membership_ethics_id", None) or "",
        "doc_issued_on": getattr(user, "membership_confirmed_at", None),
        "doc_institution": getattr(user, "institution", "") or "",
        "personal_documents": documents,
    }
