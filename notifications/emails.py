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
from django.core.mail import EmailMultiAlternatives
from django.utils.html import escape

LOGO_URL = "https://res.cloudinary.com/dmqizfpyz/image/upload/v1789467077/logo1_oozjis.png"

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
                    <img src="{LOGO_URL}" width="36" height="36" alt="MSREC" style="display:block;border-radius:8px;">
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
              <p style="margin:0;font-size:12px;color:{TEXT_FAINT};">This is an automated message &mdash; please don't reply directly to this email. For help, contact <a href="mailto:msrec@metascholar.edu" style="color:{TEAL_DARK};text-decoration:none;">msrec@metascholar.edu</a>.</p>
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
                        preheader="", fail_silently=True):
    """Sends one branded email (HTML + plain-text fallback) to `to`
    (a single address, or a list of addresses). Returns True/False --
    callers should reflect that in whatever they tell the person who
    triggered the send, rather than assuming delivery succeeded just
    because fail_silently swallowed the exception."""
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
    try:
        sent = message.send(fail_silently=fail_silently)
    except Exception:
        if not fail_silently:
            raise
        sent = 0
    return bool(sent)
