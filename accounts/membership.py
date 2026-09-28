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
    return f"MSREC-Appointment-Letter-{user.membership_ethics_id.replace('/', '-')}.pdf"


def _appointment_letter_body(user):
    kind, label = membership_role(user)
    if kind == "committee":
        duty = (
            "In this capacity you are entrusted with the independent, impartial and confidential ethical "
            "review of research protocols referred to the Committee, and with taking part in Committee "
            "meetings, deliberations and decisions, in accordance with MSREC's governing Charter and Standard "
            "Operating Procedures."
        )
    else:
        duty = (
            "In this capacity you are entrusted with the independent, impartial and confidential ethical "
            "review of research protocols assigned to you, in accordance with MSREC's governing Charter and "
            "Standard Operating Procedures."
        )
    effective = user.membership_confirmed_at.strftime("%d %B %Y").lstrip("0") if user.membership_confirmed_at else ""
    return [
        f"Dear {user.first_name or user.full_name},",
        f"RE: APPOINTMENT AS {label.upper()}, METASCHOLAR RESEARCH ETHICS COMMITTEE",
        f"We are pleased to confirm that, following review and approval, you have been appointed as "
        f"{('a' if label[:1].lower() not in 'aeiou' else 'an')} {label} of the Metascholar Research Ethics "
        f"Committee (MSREC), effective {effective}.",
        f"Your MSREC Ethics ID is {user.membership_ethics_id}. Please quote this reference in all "
        f"correspondence with the Committee.",
        duty,
        "A Membership Certificate confirming this appointment is enclosed. We look forward to your valued "
        "contribution to the Committee's work in support of independent, rigorous and ethical research.",
    ]


def render_appointment_letter_pdf(user):
    """One-page appointment letter on MSREC letterhead, issued alongside the
    Membership Certificate when a Reviewer/Committee request is approved
    (see admin_dashboard.views._send_role_approved_email). Rendered on
    demand, never stored -- same contract as render_certificate_pdf above,
    so an edited Chair signature or address applies to letters already
    "issued" as well as new ones."""
    return _render_committee_letter_pdf(
        user, doc_date=user.membership_confirmed_at, body_lines=_appointment_letter_body(user),
        doc_label="Appointment Letter",
    )


def suspension_notice_filename(user):
    return f"MSREC-Notice-of-Suspension-{user.membership_ethics_id.replace('/', '-')}.pdf"


def _suspension_notice_body(user):
    kind, label = membership_role(user)
    effective = user.suspended_at.strftime("%d %B %Y").lstrip("0") if user.suspended_at else ""
    return [
        f"Dear {user.first_name or user.full_name},",
        "RE: SUSPENSION OF MSREC MEMBERSHIP",
        f"We are writing to inform you that your appointment as {label} of the Metascholar Research Ethics "
        f"Committee (MSREC), Ethics ID {user.membership_ethics_id}, has been suspended by the Secretariat/"
        f"Administration with effect from {effective}.",
        "For the duration of this suspension you do not have access to your MSREC dashboard, and you may not "
        "undertake any review or Committee activity on behalf of MSREC.",
        "If you have any questions regarding this decision, or believe it was made in error, please contact "
        "the Secretariat.",
    ]


def render_suspension_notice_pdf(user):
    """One-page notice of suspension, the disciplinary counterpart to the
    Appointment Letter above -- issued when an admin/secretariat member
    suspends a Reviewer/Committee member's account (see
    admin_dashboard.views._handle_suspend). Rendered on demand from
    User.suspended_at, so it stays regenerable with the correct date even
    after the account is later reactivated."""
    return _render_committee_letter_pdf(
        user, doc_date=user.suspended_at, body_lines=_suspension_notice_body(user),
        doc_label="Notice of Suspension",
    )


def _render_committee_letter_pdf(user, *, doc_date, body_lines, doc_label):
    """Shared one-page letterhead renderer behind every formal letter this
    module issues to a Reviewer/Committee member (Appointment Letter,
    Notice of Suspension, ...): MSREC letterhead, a right-aligned date,
    the member's own name/institution as addressee, `body_lines` (a
    [salutation, subject, *paragraphs] list, see _appointment_letter_body/
    _suspension_notice_body above) and the Chair's signature block.
    `doc_date` prints as the letter's date and falls back to now() if
    unset (e.g. previewing before the underlying timestamp is recorded)."""
    from io import BytesIO

    from django.utils import timezone
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import Frame, HRFlowable, Image, Paragraph, Spacer

    from pages.certificate_signatory import chair_details, chair_signature_bytes
    from pages.models import SiteSettings
    from reviewer_dashboard.certificate import INK, INK_SOFT, _logo_reader, xml_escape

    W, H = A4
    margin = 22 * mm
    site = SiteSettings.get_solo()
    chair = chair_details()
    signature_png = chair_signature_bytes(chair)

    buffer = BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"MSREC {doc_label} - {user.membership_ethics_id}")
    c.setAuthor("Metascholar Research Ethics Committee")

    # Letterhead: logo + committee name/address, matching the certificate's ink.
    top = H - 14 * mm
    logo_h = 19 * mm
    text_x = margin
    try:
        reader = _logo_reader()
        iw, ih = reader.getSize()
        c.drawImage(reader, margin, top - logo_h, width=logo_h * iw / ih, height=logo_h, mask="auto")
        text_x = margin + logo_h * iw / ih + 5 * mm
    except Exception:
        pass

    c.setFillColor(INK)
    c.setFont("Times-Bold", 15.5)
    c.drawString(text_x, top - 6 * mm, "Metascholar Research Ethics Committee")
    address = [line.strip() for line in (site.footer_address or "").splitlines() if line.strip()]
    if address and address[0].lower() == "metascholar research ethics committee":
        address = address[1:]
    c.setFont("Helvetica", 8.2)
    c.setFillColor(INK_SOFT)
    y = top - 11 * mm
    for line in address[:3]:
        c.drawString(text_x, y, line)
        y -= 3.7 * mm

    rule_y = H - 38 * mm
    c.setStrokeColor(INK)
    c.setLineWidth(0.9)
    c.line(margin, rule_y, W - margin, rule_y)
    c.setLineWidth(0.3)
    c.line(margin, rule_y - 1.1 * mm, W - margin, rule_y - 1.1 * mm)

    # Date, right-aligned just under the rule.
    c.setFont("Helvetica", 9.5)
    c.setFillColor(INK_SOFT)
    date_text = (doc_date or timezone.now()).strftime("%d %B %Y").lstrip("0")
    c.drawRightString(W - margin, rule_y - 10 * mm, date_text)

    body = [
        Paragraph(f"<font name='Helvetica-Bold' color='#14233f'>{xml_escape(user.full_name)}</font>",
                  ParagraphStyle("addr1", fontName="Times-Roman", fontSize=11, leading=14.5)),
    ]
    if user.institution:
        body.append(Paragraph(xml_escape(user.institution),
                               ParagraphStyle("addr2", fontName="Times-Roman", fontSize=11, leading=14.5)))
    body.append(Spacer(1, 6 * mm))

    salutation, subject, *paragraphs_text = body_lines
    body.append(Paragraph(xml_escape(salutation), ParagraphStyle("sal", fontName="Times-Roman", fontSize=11,
                                                                   leading=15, spaceAfter=6)))
    body.append(Paragraph(xml_escape(subject), ParagraphStyle("subj", fontName="Times-Bold", fontSize=11.4,
                                                                leading=15, textColor=INK, spaceAfter=8)))
    for para in paragraphs_text:
        body.append(Paragraph(xml_escape(para), ParagraphStyle("body", fontName="Times-Roman", fontSize=11,
                                                                  leading=15.5, alignment=TA_JUSTIFY, spaceAfter=8)))

    body.append(Spacer(1, 8 * mm))
    body.append(Paragraph("Yours sincerely,", ParagraphStyle("signoff", fontName="Times-Roman", fontSize=11,
                                                               leading=15)))
    body.append(Spacer(1, 3 * mm))

    # Signature block flows right after the closing -- however long the
    # letter's body ran -- rather than sitting at a fixed page coordinate,
    # which risked colliding with the footer for a short address/role.
    if signature_png:
        try:
            reader = ImageReader(BytesIO(signature_png))
            iw, ih = reader.getSize()
            scale = min(56 * mm / iw, 15 * mm / ih)
            image = Image(BytesIO(signature_png), width=iw * scale, height=ih * scale)
            image.hAlign = "LEFT"
            body.append(image)
        except Exception:
            body.append(Spacer(1, 14 * mm))
    else:
        body.append(Spacer(1, 14 * mm))
    body.append(Spacer(1, 1 * mm))
    body.append(HRFlowable(width=70 * mm, thickness=0.5, color=INK, hAlign="LEFT", spaceAfter=2))
    if chair["name"]:
        body.append(Paragraph(f"<b>{xml_escape(chair['name'])}</b>",
                               ParagraphStyle("signame", fontName="Times-Bold", fontSize=11, leading=14,
                                              textColor=INK)))
    if chair["title"]:
        body.append(Paragraph(xml_escape(chair["title"]),
                               ParagraphStyle("sigtitle", fontName="Helvetica", fontSize=8.5, leading=12,
                                              textColor=INK_SOFT)))

    frame = Frame(margin, 20 * mm, W - 2 * margin, rule_y - 15 * mm - 20 * mm, showBoundary=0,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    frame.addFromList(body, c)

    c.setStrokeColor(INK_SOFT)
    c.setLineWidth(0.5)
    c.line(margin, 16 * mm, W - margin, 16 * mm)
    footer = f"Metascholar Research Ethics Committee  ·  {doc_label}  ·  {user.membership_ethics_id}"
    c.setFont("Helvetica", 7.5)
    c.setFillColor(INK_SOFT)
    c.drawCentredString(W / 2, 11.5 * mm, footer)

    c.showPage()
    c.save()
    return buffer.getvalue()
