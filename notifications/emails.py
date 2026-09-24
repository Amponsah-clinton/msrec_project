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

LOGO_PATH = "/static/assets/img/MSREC_LOGO.png"


def _logo_url():
    # Email clients need an absolute, publicly reachable URL -- served by
    # the site itself (WhiteNoise) so it can't go stale like a third-party link.
    return f"{settings.SITE_URL.rstrip('/')}{LOGO_PATH}"

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
                       quote_label=None, quote_text=None, preheader=""):
    """Returns the full HTML document for one branded email.

    `paragraphs` -- list of plain-text lines, each becomes its own <p>.
    `cta_text`/`cta_url` -- an optional solid-color button (e.g. "Log in").
    `quote_label`/`quote_text` -- an optional bordered quote block, for
    e.g. quoting an applicant's original Contact-page message back to them.
    `preheader` -- short hidden text shown as the preview line in an inbox
    list (Gmail/Outlook/Apple Mail all support this convention).
    """
    body_html = "".join(_p(line) for line in paragraphs if line)

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
                    <img src="{_logo_url()}" width="36" height="36" alt="MSREC" style="display:block;border-radius:8px;">
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
              {quote_html}
              {cta_html}
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
                       quote_label=None, quote_text=None):
    """Plain-text alternative -- required alongside the HTML part so mail
    clients that don't render HTML (and spam filters that dislike an
    HTML-only message) still get something readable."""
    lines = [heading, "=" * min(len(heading), 60), ""]
    lines.extend(p for p in paragraphs if p)
    if quote_text:
        lines.append("")
        if quote_label:
            lines.append(f"{quote_label}:")
        lines.append(quote_text)
    if cta_text and cta_url:
        lines.append("")
        lines.append(f"{cta_text}: {cta_url}")
    lines.append("")
    lines.append("— MSREC Secretariat")
    return "\n".join(lines)


def send_branded_email(*, subject, to, heading, paragraphs, cta_text=None,
                        cta_url=None, quote_label=None, quote_text=None,
                        preheader="", fail_silently=True, attachments=None):
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
    text_body = render_email_text(
        heading=heading, paragraphs=paragraphs, cta_text=cta_text, cta_url=cta_url,
        quote_label=quote_label, quote_text=quote_text,
    )
    html_body = render_email_html(
        heading=heading, paragraphs=paragraphs, cta_text=cta_text, cta_url=cta_url,
        quote_label=quote_label, quote_text=quote_text, preheader=preheader or heading,
    )

    message = EmailMultiAlternatives(subject=subject, body=text_body, to=recipient_list)
    message.attach_alternative(html_body, "text/html")
    for filename, content, mimetype in (attachments or []):
        message.attach(filename, content, mimetype)
    try:
        sent = message.send(fail_silently=fail_silently)
    except Exception:
        logger.exception("Failed to send email %r to %r", subject, recipient_list)
        if not fail_silently:
            raise
        sent = 0
    if not sent:
        logger.warning("Email %r to %r was not sent (0 messages delivered)", subject, recipient_list)
    return bool(sent)


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
