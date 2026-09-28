"""What an account receives when an admin or the Secretariat suspends or bans
it: an email (send_suspension_email) with a formal letter attached -- an A4
PDF on MSREC letterhead carrying the reason that was typed in the Suspend
dialog on the Accounts page.

The wording, letterhead artwork and signatory come from
pages.models.SuspensionLetterTemplate (Site Settings > Suspension Letter),
with {placeholders} filled from the account. The letter is rendered on
demand from User.suspended_at / suspension_kind / suspension_reason, never
stored, so it can be downloaded again from the Accounts page at any time.

Fitting the page: the letter is laid out at full size first; if the reason
pushes it onto a second page it is re-laid a step at a time with slightly
smaller type and spacing (never below ~9 pt) until it fits on one A4 sheet.
Only a reason too long for that flows onto a second page, at full size,
with a running head. The Suspend dialog checks this live as the reason is
typed (admin_dashboard.views.suspension_letter_fit), so whoever writes it
knows before sending whether it fits.
"""
import logging
import re
from io import BytesIO
from types import SimpleNamespace

from django.utils import timezone
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, NextPageTemplate, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

from applicant_dashboard.approval_documents import (
    BODY, COMMITTEE_NAME, FOOTER_MAX_H, HAIR, HEADER_MAX_H, INK, INK_SOFT, LETTER_H, LETTER_W, MARGIN_X,
    _NumberedCanvas, _draw_header_image, _draw_letterhead, _draw_running_head, _esc, _letter_image,
    _PLACEHOLDER_RE, _signature_flowable, fill, paragraphs,
)

from . import membership

logger = logging.getLogger(__name__)

REASON_MAX = 1500
REASON_TOKEN = "{reason}"

# Shown as click-to-insert chips on the settings page, in this order.
PLACEHOLDERS = [
    ("recipient_name", "The account holder's full name"),
    ("first_name", "The account holder's first name"),
    ("account", "“your MSREC account (email)”, plus the appointment and Ethics ID for members"),
    ("reason", "The reason typed when suspending (on its own line it prints as a boxed paragraph)"),
    ("effective_date", "Date the suspension / ban took effect"),
    ("role", "Ethics Reviewer, Committee Member, Applicant, ..."),
    ("ethics_id", "MSREC Ethics ID (members only, otherwise blank)"),
    ("email", "The account's email address"),
    ("committee_name", COMMITTEE_NAME),
    ("signatory_name", "Who signs the letter"),
    ("signatory_title", "The signatory's position"),
    ("today", "Today's date"),
]
PLACEHOLDER_KEYS = {key for key, _ in PLACEHOLDERS}

SAMPLE_REASON = (
    "Following a complaint received on 3 September 2026, the Secretariat found that confidential protocol "
    "documents assigned to you for review were shared outside the Committee, in breach of the MSREC "
    "Confidentiality Agreement and Section 4.2 of the Standard Operating Procedures."
)


def unknown_placeholders(*texts):
    found = set()
    for text in texts:
        found.update(k for k in _PLACEHOLDER_RE.findall(text or "") if k not in PLACEHOLDER_KEYS)
    return sorted(found)


def _date(value):
    return f"{value.day} {value:%B %Y}" if value else ""


def _template(template=None):
    if template is not None:
        return template
    from pages.models import SuspensionLetterTemplate
    return SuspensionLetterTemplate.get_solo()


def is_ban(kind):
    from .models import User
    return kind == User.SuspensionKind.BAN


def doc_label(kind):
    return "Notice of Account Withdrawal" if is_ban(kind) else "Notice of Suspension"


def _role_label(user):
    if membership.is_member(user):
        return membership.membership_role(user)[1]
    from .models import User
    try:
        return User.Role(user.role).label
    except ValueError:
        return "Member"


def signatory(template=None):
    """Who signs: dict(name, title, image bytes|None). A signatory set in
    Site Settings > Suspension Letter wins; otherwise the Chair."""
    from pages import storage as pages_storage
    from pages.certificate_signatory import chair_details, chair_signature_bytes

    t = _template(template)
    name = (t.sign_name or "").strip()
    if name:
        image = pages_storage.download_object(t.sign_path) if t.sign_path else None
        return {"name": name, "title": (t.sign_title or "").strip(), "image": image}
    chair = chair_details()
    return {"name": chair["name"], "title": chair["title"], "image": chair_signature_bytes(chair)}


def values(user, *, reason, effective_at, sign):
    """Every {placeholder} value for one account."""
    ethics_id = getattr(user, "membership_ethics_id", None) or ""
    role = _role_label(user)
    if ethics_id:
        account = (f"your appointment as {role} of the {COMMITTEE_NAME} (Ethics ID {ethics_id}) and "
                   f"your MSREC account ({user.email})")
    else:
        account = f"your MSREC account ({user.email})"
    return {
        "recipient_name": user.full_name,
        "first_name": user.first_name or user.full_name,
        "account": account,
        "reason": " ".join((reason or "").split()),
        "effective_date": _date(timezone.localtime(effective_at) if effective_at else None),
        "role": role,
        "ethics_id": ethics_id,
        "email": user.email,
        "committee_name": COMMITTEE_NAME,
        "signatory_name": sign["name"],
        "signatory_title": sign["title"],
        "today": _date(timezone.localtime()),
    }


def clean_reason(text):
    """Normalises a typed reason: unified newlines, no trailing spaces, at
    most one blank line between paragraphs, capped at REASON_MAX."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:REASON_MAX]


def reason_blocks(reason):
    """The typed reason as a list of paragraphs, each a list of lines --
    the admin's own paragraph breaks and line breaks are kept, so a short
    list typed one item per line stays a list on the letter."""
    blocks = []
    for block in re.split(r"\n\s*\n", reason or ""):
        lines = [" ".join(line.split()) for line in block.split("\n") if line.strip()]
        if lines:
            blocks.append(lines)
    return blocks


def letter_content(user, template=None, *, kind=None, reason=None, effective_at=None):
    t = _template(template)
    kind = kind or user.suspension_kind or "suspend"
    reason = clean_reason(user.suspension_reason if reason is None else reason)
    effective_at = effective_at or user.suspended_at or timezone.now()
    sign = signatory(t)
    v = values(user, reason=reason, effective_at=effective_at, sign=sign)

    body_template = t.ban_body if is_ban(kind) else t.suspend_body
    # ("text", str) paragraphs, and at most one ("reason", blocks) box --
    # wherever {reason} stands alone as its own paragraph.
    body, placed = [], False
    for para in paragraphs(body_template):
        if para.strip() == REASON_TOKEN:
            if reason and not placed:
                body.append(("reason", reason_blocks(reason)))
                placed = True
            continue
        if REASON_TOKEN in para:
            placed = True
        body.append(("text", fill(para, v)))
    if reason and not placed:
        # The template doesn't mention {reason} at all -- the typed reason
        # must still reach the letter, so it goes after the body.
        body.append(("reason", reason_blocks(reason)))

    return {
        "values": v,
        "kind": kind,
        "doc_label": doc_label(kind),
        "subject": fill(t.ban_subject if is_ban(kind) else t.suspend_subject, v),
        "salutation": fill(t.salutation, v),
        "body": body,
        "closing": [fill(p, v) for p in paragraphs(t.closing)],
        "sign_off": fill(t.sign_off, v),
        "signatory": sign,
        "effective_at": effective_at,
    }


def _letterhead_images(template):
    """The suspension letter's own header / footer artwork, falling back to
    the approval letter's, then (None) to the built-in text letterhead."""
    from pages import storage as pages_storage
    from pages.models import ApprovalDocumentTemplate

    t = _template(template)
    approval = ApprovalDocumentTemplate.get_solo()
    header_path = t.header_path or approval.letter_header_path
    footer_path = t.footer_path or approval.letter_footer_path
    header = _letter_image(pages_storage.download_object(header_path), HEADER_MAX_H) if header_path else None
    footer = _letter_image(pages_storage.download_object(footer_path), FOOTER_MAX_H) if footer_path else None
    return header, footer


# Each step shrinks type and spacing together; 0.82 keeps body text at 9 pt.
FIT_SCALES = (1.0, 0.95, 0.9, 0.86, 0.82)


def render_letter(user, template=None, *, kind=None, reason=None, effective_at=None):
    """(pdf_bytes, page_count, scale) -- the largest scale in FIT_SCALES
    that keeps the letter on one page, or full size if none does."""
    from pages.models import SiteSettings

    content = letter_content(user, template, kind=kind, reason=reason, effective_at=effective_at)
    header, footer = _letterhead_images(template)
    site = SiteSettings.get_solo()

    first = None
    for scale in FIT_SCALES:
        pdf, pages = _build(user, content, header, footer, site, scale)
        if first is None:
            first = (pdf, pages, scale)
        if pages == 1:
            return pdf, pages, scale
    return first


def render_letter_pdf(user, template=None, *, kind=None, reason=None, effective_at=None):
    return render_letter(user, template, kind=kind, reason=reason, effective_at=effective_at)[0]


def _build(user, content, header_image, footer_image, site, scale):
    v = content["values"]
    s = lambda value: value * scale  # noqa: E731
    size, leading = s(11), s(15.2)
    styles = {
        "body": ParagraphStyle("body", fontName="Times-Roman", fontSize=size, leading=leading, textColor=BODY,
                               alignment=TA_JUSTIFY, spaceAfter=s(7)),
        "plain": ParagraphStyle("plain", fontName="Times-Roman", fontSize=size, leading=leading, textColor=BODY),
        "subject": ParagraphStyle("subject", fontName="Times-Bold", fontSize=s(11.4), leading=s(15.5),
                                  textColor=INK, spaceBefore=2, spaceAfter=s(8)),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8.6, leading=12, textColor=INK_SOFT),
        "flag": ParagraphStyle("flag", fontName="Helvetica-Bold", fontSize=7.4, leading=10, textColor=INK_SOFT),
        "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=7, leading=10, textColor=INK_SOFT,
                                spaceAfter=s(2.5)),
        "reason": ParagraphStyle("reason", fontName="Times-Roman", fontSize=size, leading=leading, textColor=BODY,
                                 alignment=TA_JUSTIFY),
    }
    frame_w = LETTER_W - 2 * MARGIN_X

    story = [NextPageTemplate("later")]
    meta = Table(
        [[Paragraph(f"Ethics ID: <font name='Helvetica-Bold' color='#14233f'>{_esc(v['ethics_id'])}</font>"
                    if v["ethics_id"] else "", styles["meta"]),
          Paragraph(_esc(_date(timezone.localtime(content["effective_at"]))),
                    ParagraphStyle("right", parent=styles["meta"], alignment=2))]],
        colWidths=[frame_w / 2] * 2,
    )
    meta.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [meta, Spacer(1, s(4) * mm), Paragraph("PRIVATE &amp; CONFIDENTIAL", styles["flag"]), Spacer(1, s(2) * mm)]

    addressee = [user.full_name, getattr(user, "position", ""), getattr(user, "institution", ""), user.email]
    for index, line in enumerate(x for x in addressee if (x or "").strip()):
        font = "Times-Bold" if index == 0 else "Times-Roman"
        story.append(Paragraph(f"<font name='{font}'>{_esc(line.strip())}</font>", styles["plain"]))
    story += [Spacer(1, s(5) * mm), Paragraph(_esc(content["salutation"]), styles["plain"]), Spacer(1, s(2) * mm),
              Paragraph(_esc(content["subject"]), styles["subject"])]

    for kind, item in content["body"]:
        if kind == "text":
            story.append(Paragraph(_esc(item), styles["body"]))
        else:
            story += [_reason_box(item, styles, frame_w, s), Spacer(1, s(3.5) * mm)]

    closing = [Paragraph(_esc(p), styles["body"]) for p in content["closing"]]
    sign = content["signatory"]
    block = [Spacer(1, s(2) * mm), Paragraph(_esc(content["sign_off"]), styles["plain"]), Spacer(1, s(1.5) * mm),
             _signature_flowable(sign["image"], max_h=s(15) * mm), Spacer(1, 1 * mm)]
    rule = Table([[""]], colWidths=[70 * mm], rowHeights=[1])
    rule.hAlign = "LEFT"
    rule.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 0.5, INK)]))
    block.append(rule)
    if sign["name"]:
        block.append(Paragraph(f"<b>{_esc(sign['name'])}</b>", styles["plain"]))
    if sign["title"]:
        block.append(Paragraph(_esc(sign["title"]), styles["plain"]))
    # The closing paragraph always travels with the signature, so a
    # signature never sits alone at the top of a page.
    story.append(KeepTogether(closing + block))

    buffer = BytesIO()
    doc = BaseDocTemplate(
        buffer, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X, topMargin=22 * mm, bottomMargin=22 * mm,
        title=f"MSREC {content['doc_label']} - {user.full_name}", author=COMMITTEE_NAME,
    )
    first_top = (header_image[3] + 8 * mm) if header_image else 44 * mm
    bottom = (footer_image[3] + 10 * mm) if footer_image else 20 * mm
    first = Frame(MARGIN_X, bottom, frame_w, LETTER_H - first_top - bottom, id="first",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    later = Frame(MARGIN_X, bottom, frame_w, LETTER_H - 24 * mm - bottom, id="later",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    draw_first = ((lambda c, d: _draw_header_image(c, header_image)) if header_image
                  else (lambda c, d: _draw_letterhead(c, site)))
    running = v["ethics_id"] or user.full_name
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first], onPage=draw_first),
        PageTemplate(id="later", frames=[later], onPage=lambda c, d: _draw_running_head(c, running)),
    ])
    footer_text = f"{COMMITTEE_NAME}  ·  {content['doc_label']}  ·  {running}"
    doc.build(story, canvasmaker=lambda *a, **k: _NumberedCanvas(*a, footer_text=footer_text,
                                                                 footer_image=footer_image, **k))
    return buffer.getvalue(), doc.page


def _reason_box(blocks, styles, frame_w, s):
    """The typed reason in a lightly tinted panel with a navy rule down its
    left edge -- one table row per paragraph, so a very long reason can
    still break between paragraphs rather than overflowing the page."""
    rows = [[Paragraph("REASON", styles["label"])]]
    for lines in blocks:
        rows.append([Paragraph("<br/>".join(_esc(line) for line in lines), styles["reason"])])
    box = Table(rows, colWidths=[frame_w])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), "#f4f6f9"),
        ("LINEBEFORE", (0, 0), (0, -1), 2, INK),
        ("LINEBELOW", (0, -1), (-1, -1), 0.4, HAIR),
        ("LEFTPADDING", (0, 0), (-1, -1), s(4) * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), s(4) * mm),
        ("TOPPADDING", (0, 0), (-1, -1), s(1.2) * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), s(1.2) * mm),
        ("TOPPADDING", (0, 0), (-1, 0), s(3) * mm),
        ("BOTTOMPADDING", (0, -1), (-1, -1), s(3.2) * mm),
    ]))
    return box


def letter_filename(user, kind=None):
    kind = kind or user.suspension_kind
    stem = "Notice-of-Account-Withdrawal" if is_ban(kind) else "Notice-of-Suspension"
    ref = (getattr(user, "membership_ethics_id", None) or f"{user.pk}").replace("/", "-")
    return f"MSREC-{stem}-{ref}.pdf"


def send_suspension_email(user):
    """The email sent the moment an account is suspended or banned, with
    the letter attached and the reason quoted. A PDF problem never stops
    the email itself going out."""
    from notifications.emails import send_branded_email

    banned = is_ban(user.suspension_kind)
    reason = clean_reason(user.suspension_reason)
    effective = _date(timezone.localtime(user.suspended_at)) if user.suspended_at else "today"
    if banned:
        paragraphs_out = [
            f"Dear {user.first_name or user.full_name},",
            f"This is to inform you that your MSREC account has been permanently withdrawn (banned) by the "
            f"Secretariat/Administration, with effect from {effective}. You will no longer be able to sign in, "
            f"and any Reviewer or Committee responsibilities have been withdrawn.",
        ]
    else:
        paragraphs_out = [
            f"Dear {user.first_name or user.full_name},",
            f"This is to inform you that your MSREC account has been suspended by the Secretariat/"
            f"Administration, with effect from {effective}. You will not be able to sign in, and any Reviewer "
            f"or Committee duties are paused, until the account is reactivated.",
        ]

    attachments = []
    try:
        attachments.append((letter_filename(user), render_letter_pdf(user), "application/pdf"))
        paragraphs_out.append(f"A formal {doc_label(user.suspension_kind)} is attached to this email.")
    except Exception:
        logger.exception("Couldn't render the suspension letter for user %s", user.pk)
    paragraphs_out.append(
        "If you believe this was done in error, or would like more information, please contact the Secretariat."
    )
    subject = ("MSREC — your account has been permanently withdrawn" if banned
               else "MSREC — your account has been suspended")
    return send_branded_email(
        subject=subject,
        to=user.email,
        heading="Your MSREC account has been " + ("permanently withdrawn" if banned else "suspended"),
        paragraphs=paragraphs_out,
        quote_label="Reason" if reason else None,
        quote_text=reason or None,
        preheader=subject.replace("MSREC — y", "Y") + ".",
        attachments=attachments,
    )


def sample_user():
    """A realistic stand-in for the settings-page preview."""
    now = timezone.now()
    return SimpleNamespace(
        pk=0, full_name="Dr. Kwame Asante Boateng", first_name="Kwame", email="k.boateng@example.com",
        position="Senior Lecturer", institution="Kwame Nkrumah University of Science and Technology",
        role="reviewer", membership_ethics_id=f"MSREC/ER/{now.year}/0017", committee_status="not_requested",
        committee_profile={}, suspended_at=now, suspension_kind="suspend", suspension_reason=SAMPLE_REASON,
    )
