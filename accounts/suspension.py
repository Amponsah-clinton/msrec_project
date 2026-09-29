"""What an account receives when an admin or the Secretariat suspends or bans
it: an email (send_suspension_email) with a formal letter attached -- an A4
PDF on MSREC letterhead carrying the reason that was typed in the Suspend
dialog on the Accounts page.

The wording, letterhead artwork and signatory come from
pages.models.SuspensionLetterTemplate (Site Settings > Suspension Letter),
with {placeholders} filled from the account. The letter is rendered on
demand from User.suspended_at / suspension_kind / suspension_reason, never
stored, so it can be downloaded again from the Accounts page at any time.

The page layout, letterhead fallback and fit-to-one-A4-page logic are
shared with the Appointment Letter (accounts/letters.py). The Suspend
dialog checks the fit live as the reason is typed (admin_dashboard.views.
suspension_letter_fit), so whoever writes it knows before sending.
"""
import logging
import re
from types import SimpleNamespace

from django.utils import timezone

from applicant_dashboard.approval_documents import COMMITTEE_NAME, fill, paragraphs

from . import letters, membership

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
    ("restored_at", "When access is restored (date + time, for a temporary suspension; blank on a ban)"),
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
    return letters.unknown_placeholders(PLACEHOLDER_KEYS, *texts)


_date = letters.date_text


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
    """Who signs: the signatory set in Site Settings > Suspension Letter,
    otherwise the Chair (see letters.signatory)."""
    return letters.signatory(_template(template))


def _datetime_text(dt):
    """Formats an aware datetime for the letter and email: e.g.
    "5 October 2026 at 4:30 PM". Returns "" for None. Uses django's
    date filter under the hood so it renders identically on Windows
    (where strftime's %-d / %-I don't exist) and Linux."""
    if not dt:
        return ""
    from django.utils.dateformat import format as django_format
    local = timezone.localtime(dt)
    return django_format(local, "j F Y \\a\\t g:i A")


def values(user, *, reason, effective_at, sign, restored_at=None):
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
        "restored_at": _datetime_text(restored_at) if restored_at else "",
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


reason_blocks = letters.text_blocks


def letter_content(user, template=None, *, kind=None, reason=None, effective_at=None, restored_at=None):
    t = _template(template)
    kind = kind or user.suspension_kind or "suspend"
    reason = clean_reason(user.suspension_reason if reason is None else reason)
    effective_at = effective_at or user.suspended_at or timezone.now()
    if restored_at is None and not is_ban(kind):
        restored_at = getattr(user, "suspended_until", None)
    sign = signatory(t)
    v = values(user, reason=reason, effective_at=effective_at, sign=sign, restored_at=restored_at)

    body_template = t.ban_body if is_ban(kind) else t.suspend_body
    # ("text", str) paragraphs, and at most one ("box", ...) reason panel --
    # wherever {reason} stands alone as its own paragraph.
    body, placed = [], False
    for para in paragraphs(body_template):
        if para.strip() == REASON_TOKEN:
            if reason and not placed:
                body.append(("box", ("Reason", reason_blocks(reason))))
                placed = True
            continue
        if REASON_TOKEN in para:
            placed = True
        body.append(("text", fill(para, v)))
    if reason and not placed:
        # The template doesn't mention {reason} at all -- the typed reason
        # must still reach the letter, so it goes after the body.
        body.append(("box", ("Reason", reason_blocks(reason))))
    # Same safety net for the restored-on moment: if the letter template
    # doesn't mention {restored_at}, tack it on so a suspended user always
    # sees when they can sign back in.
    if restored_at and not is_ban(kind) and "{restored_at}" not in (body_template or ""):
        body.append(("box", ("Access restored on", [v["restored_at"]])))

    return {
        "values": v,
        "kind": kind,
        "doc_label": doc_label(kind),
        "ethics_id": v["ethics_id"],
        "date": effective_at,
        "flag": "PRIVATE & CONFIDENTIAL",
        "subject": fill(t.ban_subject if is_ban(kind) else t.suspend_subject, v),
        "salutation": fill(t.salutation, v),
        "body": body,
        "closing": [fill(p, v) for p in paragraphs(t.closing)],
        "sign_off": fill(t.sign_off, v),
        "signatory": sign,
        "effective_at": effective_at,
    }


def render_letter(user, template=None, *, kind=None, reason=None, effective_at=None, restored_at=None):
    """(pdf_bytes, page_count, scale) -- see letters.render."""
    t = _template(template)
    content = letter_content(user, t, kind=kind, reason=reason, effective_at=effective_at, restored_at=restored_at)
    return letters.render(user, content, t)


def render_letter_pdf(user, template=None, *, kind=None, reason=None, effective_at=None, restored_at=None):
    return render_letter(user, template, kind=kind, reason=reason, effective_at=effective_at, restored_at=restored_at)[0]


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
    restored_at = getattr(user, "suspended_until", None)
    restored_text = _datetime_text(restored_at) if restored_at else ""
    if banned:
        paragraphs_out = [
            f"Dear {user.first_name or user.full_name},",
            f"This is to inform you that your MSREC account has been permanently withdrawn (banned) by the "
            f"Secretariat/Administration, with effect from {effective}. You will no longer be able to sign in, "
            f"and any Reviewer or Committee responsibilities have been withdrawn.",
        ]
    else:
        if restored_text:
            second = (
                f"This is to inform you that your MSREC account has been temporarily suspended by the "
                f"Secretariat/Administration, with effect from {effective}. You will not be able to sign in, "
                f"and any Reviewer or Committee duties are paused, until access is automatically restored on "
                f"{restored_text}."
            )
        else:
            second = (
                f"This is to inform you that your MSREC account has been suspended by the Secretariat/"
                f"Administration, with effect from {effective}. You will not be able to sign in, and any "
                f"Reviewer or Committee duties are paused, until the account is reactivated."
            )
        paragraphs_out = [
            f"Dear {user.first_name or user.full_name},",
            second,
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
