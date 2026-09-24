"""One shared, branded HTML email template for every outbound email this
project sends (role-approval notices, Contact-page replies, and anything
added later) -- so a message from MSREC always looks like it came from a
real institution instead of a bare console.EmailBackend-style plaintext
dump. Deliberately plain and print-like (solid brand teal, a thin border,
generous whitespace) rather than anything gradient-heavy or "template
generator" looking.

Lives in `notifications` because sending an email is just another channel
for "tell a user something happened" -- the same idea as
notifications.services.notify(), one layer down.
"""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

logger = logging.getLogger(__name__)

# The logo travels INSIDE each email as an inline (CID) image rather than
# as a link to the website: a link only works if the site is publicly
# reachable (never true from a dev machine) and if the mail client chooses
# to load remote images, which many don't by default. Embedded, it shows
# in Gmail, Outlook and Apple Mail with no "load images" prompt.
LOGO_FILE = settings.BASE_DIR / "static" / "assets" / "img" / "MSREC_LOGO.png"
LOGO_CID = "msrec-logo"
LOGO_DISPLAY_WIDTH = 40
_logo_cache = {}


def _logo_png():
    """(png_bytes, display_height) -- the logo downscaled once per process
    (the source file is ~470 KB, far more than a 40px header needs).
    None if the file can't be read, in which case emails just omit it."""
    if "png" not in _logo_cache:
        try:
            from io import BytesIO

            from PIL import Image

            with Image.open(LOGO_FILE) as im:
                im = im.convert("RGBA")
                im.thumbnail((LOGO_DISPLAY_WIDTH * 3, LOGO_DISPLAY_WIDTH * 3), Image.LANCZOS)
                buf = BytesIO()
                im.save(buf, format="PNG", optimize=True)
                height = round(LOGO_DISPLAY_WIDTH * im.height / im.width)
            _logo_cache["png"] = (buf.getvalue(), height)
        except Exception:
            logger.exception("Couldn't prepare the email logo")
            _logo_cache["png"] = None
    return _logo_cache["png"]


def _logo_img_html():
    logo = _logo_png()
    if not logo:
        return ""
    return (
        f'<img src="cid:{LOGO_CID}" width="{LOGO_DISPLAY_WIDTH}" height="{logo[1]}" alt="MSREC" '
        f'style="display:block;border:0;outline:none;">'
    )


def _attach_logo(message):
    """Embeds the logo referenced by cid:msrec-logo in the HTML part."""
    logo = _logo_png()
    if not logo:
        return
    from email.mime.image import MIMEImage

    image = MIMEImage(logo[0], "png")
    image.add_header("Content-ID", f"<{LOGO_CID}>")
    image.add_header("Content-Disposition", "inline", filename="msrec-logo.png")
    message.mixed_subtype = "related"
    message.attach(image)


# Same palette as the dashboard (static/dashboard/css/style.css :root) --
# an email client can't read CSS custom properties, so these are the
# literal values, kept in sync by hand.
TEAL = "#159a96"
TEAL_DARK = "#0f7a76"
NAVY = "#1b2a4a"
TEXT_MAIN = "#1f2733"
TEXT_SUB = "#5b6472"
TEXT_FAINT = "#8a93a3"
BORDER = "#e6e9ef"
PAGE_BG = "#f0f2f6"
QUOTE_BG = "#f7f8fa"


def _p(text):
    return f'<p style="margin:0 0 16px;font-size:15px;line-height:1.7;color:{TEXT_MAIN};">{escape(text)}</p>'


def render_email_html(*, heading, paragraphs, cta_text=None, cta_url=None,
                       quote_label=None, quote_text=None, preheader="",
                       callout_label=None, callout_value=None, callout_note=None, callout_after=None,
                       access=None):
    """Returns the full HTML document for one branded email.

    `paragraphs` -- list of plain-text lines, each becomes its own <p>.
    `cta_text`/`cta_url` -- an optional solid-color button (e.g. "Log in").
    `quote_label`/`quote_text` -- an optional bordered quote block, for
    e.g. quoting an applicant's original Contact-page message back to them.
    `preheader` -- short hidden text shown as the preview line in an inbox
    list (Gmail/Outlook/Apple Mail all support this convention).
    """
    lines = [line for line in paragraphs if line]
    split = len(lines) if callout_after is None else max(0, min(callout_after, len(lines)))
    body_html = "".join(_p(line) for line in lines[:split])
    after_html = "".join(_p(line) for line in lines[split:])

    # A prominent, solid-colour box for one key value (e.g. an Ethics ID).
    callout_html = ""
    if callout_value:
        note_html = (
            f'<p style="margin:6px 0 0;font-size:12.5px;color:{TEXT_SUB};">{escape(callout_note)}</p>'
            if callout_note else ""
        )
        callout_html = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:6px 0 22px;">
          <tr>
            <td style="background:{QUOTE_BG};border:1px solid {BORDER};border-radius:8px;padding:16px 18px;">
              <p style="margin:0 0 4px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:{TEXT_FAINT};">{escape(callout_label or "")}</p>
              <p style="margin:0;font-family:Consolas,'Courier New',monospace;font-size:24px;font-weight:700;letter-spacing:.04em;color:{NAVY};">{escape(callout_value)}</p>
              {note_html}
            </td>
          </tr>
        </table>"""

    quote_html = ""
    if quote_text:
        label_html = (
            f'<p style="margin:0 0 8px;font-size:11px;font-weight:700;'
            f'text-transform:uppercase;letter-spacing:.04em;color:{TEXT_FAINT};">{escape(quote_label or "")}</p>'
            if quote_label else ""
        )
        quote_html = f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0 20px;">
          <tr>
            <td style="background:{QUOTE_BG};border:1px solid {BORDER};border-radius:6px;padding:14px 16px;">
              {label_html}
              <p style="margin:0;font-size:14px;line-height:1.65;color:{TEXT_SUB};white-space:pre-line;">{escape(quote_text)}</p>
            </td>
          </tr>
        </table>"""

    # The recipient's login details (see _access_details) replace a plain
    # "Log in" button, which would otherwise appear twice.
    if access and _is_login_link(cta_url, access):
        cta_text = cta_url = None

    cta_html = ""
    if cta_text and cta_url:
        cta_html = f"""
        <table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0 26px;">
          <tr>
            <td style="border-radius:8px;background:{TEAL};">
              <a href="{escape(cta_url)}"
                 style="display:inline-block;padding:12px 26px;font-size:14px;font-weight:600;
                        color:#ffffff;text-decoration:none;border-radius:8px;">
                {escape(cta_text)}
              </a>
            </td>
          </tr>
        </table>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="color-scheme" content="light">
<title>{escape(heading)}</title>
</head>
<body style="margin:0;padding:0;background:{PAGE_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(preheader)}</div>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAGE_BG};padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border:1px solid {BORDER};border-radius:12px;overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="padding:28px 32px 20px;border-bottom:1px solid {BORDER};">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="vertical-align:middle;padding-right:10px;">
                    {_logo_img_html()}
                  </td>
                  <td style="vertical-align:middle;">
                    <div style="font-size:15px;font-weight:700;color:{NAVY};letter-spacing:.01em;line-height:1.3;">MSREC</div>
                    <div style="font-size:11px;color:{TEXT_FAINT};line-height:1.3;">Metascholar Research Ethics Committee</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:32px 32px 8px;">
              <h1 style="margin:0 0 18px;font-size:19px;font-weight:700;color:{TEXT_MAIN};line-height:1.4;">{escape(heading)}</h1>
              {body_html}
              {callout_html}
              {after_html}
              {quote_html}
              {cta_html}
              {_access_html(access)}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px 28px;border-top:1px solid {BORDER};">
              <p style="margin:0 0 4px;font-size:12.5px;color:{TEXT_SUB};">Metascholar Research Ethics Committee (MSREC)</p>
              <p style="margin:0;font-size:12px;color:{TEXT_FAINT};">This is an automated message &mdash; please do not reply to this email. For any help, contact <a href="mailto:msrec@metascholar.edu" style="color:{TEAL_DARK};text-decoration:none;">msrec@metascholar.edu</a>.</p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def render_email_text(*, heading, paragraphs, cta_text=None, cta_url=None,
                       quote_label=None, quote_text=None,
                       callout_label=None, callout_value=None, callout_note=None, access=None):
    """Plain-text alternative -- required alongside the HTML part so mail
    clients that don't render HTML (and spam filters that dislike an
    HTML-only message) still get something readable."""
    lines = [heading, "=" * min(len(heading), 60), ""]
    lines.extend(p for p in paragraphs if p)
    if callout_value:
        lines += ["", f"{callout_label}: {callout_value}" if callout_label else callout_value]
        if callout_note:
            lines.append(callout_note)
    if quote_text:
        lines.append("")
        if quote_label:
            lines.append(f"{quote_label}:")
        lines.append(quote_text)
    if access and _is_login_link(cta_url, access):
        cta_text = cta_url = None
    if cta_text and cta_url:
        lines.append("")
        lines.append(f"{cta_text}: {cta_url}")
    if access:
        lines += [
            "",
            "YOUR MSREC LOGIN",
            f"Login email: {access['email']}",
            f"Password: {access['password']}" if access.get("password") else f"Password: {ACCESS_PASSWORD_NOTE}",
            f"Forgot your password? Reset it here: {access['reset_url']}",
            f"Log in to MSREC: {access['login_url']}",
        ]
    lines.append("")
    lines.append("— MSREC Secretariat")
    return "\n".join(lines)


# Passwords are stored only as one-way hashes, so a password the member
# chose themselves can never be read back and put in an email. The one
# exception is the approval email: it issues a freshly generated password
# (see admin_dashboard.views._send_role_approved_email) and passes it in as
# `login_password`, so that email shows the real, working password.
# Every other email shows this note plus a reset link instead.
ACCESS_PASSWORD_NOTE = "the password you created for your MSREC account (for your security it is never sent by email)"


def _is_login_link(url, access):
    from urllib.parse import urlparse

    return bool(url) and urlparse(url).path == urlparse(access["login_url"]).path


def _access_html(access):
    if not access:
        return ""
    row = (
        '<tr><td style="padding:6px 0;font-size:12.5px;color:{faint};width:112px;vertical-align:top;">{label}</td>'
        '<td style="padding:6px 0;font-size:14px;color:{main};vertical-align:top;">{value}</td></tr>'
    )
    email_value = f'<strong style="font-weight:700;">{escape(access["email"])}</strong>'
    if access.get("password"):
        password_value = (
            f'<span style="display:inline-block;font-family:Consolas,\'Courier New\',monospace;font-size:17px;'
            f'font-weight:700;letter-spacing:.06em;color:{NAVY};background:{QUOTE_BG};border:1px solid {BORDER};'
            f'border-radius:6px;padding:4px 10px;">{escape(access["password"])}</span><br>'
            f'<span style="font-size:12.5px;color:{TEXT_SUB};">You can change it any time from your dashboard '
            f'(Profile &amp; Security).</span>'
        )
    else:
        password_value = (
            f'{escape(ACCESS_PASSWORD_NOTE[0].upper() + ACCESS_PASSWORD_NOTE[1:])}.<br>'
            f'<a href="{escape(access["reset_url"])}" style="color:{TEAL_DARK};font-weight:600;">Forgot it? Reset your password</a>'
        )
    return f"""
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:6px 0 24px;">
          <tr>
            <td style="border:1px solid {BORDER};border-radius:10px;padding:16px 18px;background:#ffffff;">
              <p style="margin:0 0 8px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:{TEXT_FAINT};">Your MSREC login</p>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                {row.format(faint=TEXT_FAINT, main=TEXT_MAIN, label="Login email", value=email_value)}
                {row.format(faint=TEXT_FAINT, main=TEXT_MAIN, label="Password", value=password_value)}
              </table>
              <table role="presentation" cellpadding="0" cellspacing="0" style="margin:14px 0 2px;">
                <tr>
                  <td style="border-radius:8px;background:{TEAL};">
                    <a href="{escape(access["login_url"])}"
                       style="display:inline-block;padding:12px 26px;font-size:14px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:8px;">
                      Log in to MSREC
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>"""


def _access_details(recipient_list):
    """{email: access-dict} for every recipient who is an MSREC Reviewer or
    Committee member (approved, or holding one of those dashboard roles) --
    they get their login details in every email. Anyone else maps to
    nothing and gets the email unchanged."""
    from django.conf import settings
    from django.db.models import Q
    from django.urls import reverse

    from accounts.models import User

    wanted = {address.strip().lower() for address in recipient_list if address}
    if not wanted:
        return {}
    approved = User.RequestStatus.APPROVED
    members = (
        User.objects.filter(email__in=wanted, is_active=True)
        .filter(
            Q(reviewer_status=approved) | Q(committee_status=approved)
            | Q(role__in=[User.Role.REVIEWER, User.Role.COMMITTEE, User.Role.CHAIR])
        )
        .values_list("email", flat=True)
    )
    base = settings.SITE_URL.rstrip("/")
    login_url = base + reverse("pages:login")
    reset_url = base + reverse("pages:forgot_password")
    return {
        email.lower(): {"email": email, "login_url": login_url, "reset_url": reset_url}
        for email in members
    }


def send_branded_email(*, subject, to, heading, paragraphs, cta_text=None,
                        cta_url=None, quote_label=None, quote_text=None,
                        preheader="", fail_silently=True, attachments=None,
                        callout_label=None, callout_value=None, callout_note=None, callout_after=None,
                        login_password=None):
    """Sends one branded email (HTML + plain-text fallback) to `to`
    (a single address, or a list of addresses). Returns True/False --
    callers should reflect that in whatever they tell the person who
    triggered the send, rather than assuming delivery succeeded just
    because fail_silently swallowed the exception.

    `attachments` -- optional list of (filename, content_bytes, mimetype)
    tuples, e.g. a generated certificate PDF (see reviewer_dashboard/
    certificate.py's award_certificate view). Rare enough across the app
    that every other caller just omits it."""
    recipient_list = [to] if isinstance(to, str) else list(to)
    callout = {"callout_label": callout_label, "callout_value": callout_value, "callout_note": callout_note}

    def deliver(recipients, access):
        text_body = render_email_text(
            heading=heading, paragraphs=paragraphs, cta_text=cta_text, cta_url=cta_url,
            quote_label=quote_label, quote_text=quote_text, access=access, **callout,
        )
        html_body = render_email_html(
            heading=heading, paragraphs=paragraphs, cta_text=cta_text, cta_url=cta_url,
            quote_label=quote_label, quote_text=quote_text, preheader=preheader or heading,
            callout_after=callout_after, access=access, **callout,
        )
        message = EmailMultiAlternatives(subject=subject, body=text_body, to=recipients)
        message.attach_alternative(html_body, "text/html")
        _attach_logo(message)
        for filename, content, mimetype in (attachments or []):
            message.attach(filename, content, mimetype)
        try:
            sent = message.send(fail_silently=fail_silently)
        except Exception:
            logger.exception("Failed to send email %r to %r", subject, recipients)
            if not fail_silently:
                raise
            sent = 0
        if not sent:
            logger.warning("Email %r to %r was not sent (0 messages delivered)", subject, recipients)
        return bool(sent)

    # Reviewers and Committee members always get their own copy carrying
    # their login details; everyone else shares one message as before.
    try:
        access_by_email = _access_details(recipient_list)
    except Exception:
        logger.exception("Couldn't look up login details for %r", recipient_list)
        access_by_email = {}
    if login_password:
        # Only ever passed for a single, specific recipient (the approval
        # email); never shared across a multi-recipient message.
        for access in access_by_email.values():
            access["password"] = login_password
    others = [r for r in recipient_list if r.strip().lower() not in access_by_email]
    results = [deliver([r], access_by_email[r.strip().lower()]) for r in recipient_list
               if r.strip().lower() in access_by_email]
    if others:
        results.append(deliver(others, None))
    return bool(results) and all(results)


def send_password_changed_email(user, request=None):
    """Security alert sent whenever an account's password changes, so the
    owner can spot a change they didn't make. Never raises -- a mail
    failure must not undo or block the password change itself."""
    from django.urls import reverse
    from django.utils import timezone

    when = timezone.localtime().strftime("%d %b %Y, %H:%M %Z")
    details = [f"Time: {when}"]
    if request is not None:
        ip = request.META.get("REMOTE_ADDR", "")
        if ip:
            details.append(f"IP address: {ip}")
    try:
        return send_branded_email(
            subject="Your MSREC password was changed",
            to=user.email,
            heading="Your password was changed",
            paragraphs=[
                f"Hello {user.first_name or 'there'},",
                "The password for your MSREC account was just changed.",
                "  |  ".join(details),
                "If this was you, no further action is needed.",
                "If you did NOT make this change, reset your password immediately "
                "and contact msrec@metascholar.edu.",
            ],
            cta_text="Reset my password",
            cta_url=f"{settings.SITE_URL.rstrip('/')}{reverse('pages:forgot_password')}",
            preheader="Your MSREC password was changed. If this wasn't you, act now.",
        )
    except Exception:
        logger.exception("Password-changed alert failed for user %s", user.pk)
        return False
