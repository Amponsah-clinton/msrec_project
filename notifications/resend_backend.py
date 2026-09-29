"""HTTP-based Django email backend that delivers via the Resend API.

Why this exists: many hosts (shared cPanel, some VPS providers, most cloud
container platforms) block outbound SMTP ports (25/465/587). In that case
the stdlib SMTP backend silently hangs or times out and no email --
signup "pending approval" notice, admin approval welcome, password reset --
ever reaches the recipient. Resend's HTTPS endpoint works from anywhere
that can make an outbound HTTPS call, so falling back to it whenever
RESEND_API_KEY is present is what makes those transactional emails
actually get delivered.

Enabled from config/settings.py: when RESEND_API_KEY is set, EMAIL_BACKEND
points here; otherwise settings falls back to SMTP (if EMAIL_HOST is set)
or the console backend.
"""
import base64
import json
import logging
import ssl
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _addr_list(values):
    return [v for v in (values or []) if v]


class ResendEmailBackend(BaseEmailBackend):
    """Send each EmailMessage via a single HTTPS POST to Resend's /emails.

    Honours fail_silently the same way the SMTP backend does: on failure
    the exception is logged and swallowed when fail_silently is True, so a
    view like signup() or the role-approval handler is never taken down by
    a transient email outage.
    """

    def __init__(self, fail_silently=False, api_key=None, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.api_key = api_key or getattr(settings, "RESEND_API_KEY", "") or ""
        self.timeout = getattr(settings, "EMAIL_TIMEOUT", 10) or 10

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            logger.warning("ResendEmailBackend has no RESEND_API_KEY configured; dropping %d message(s)",
                           len(email_messages))
            if not self.fail_silently:
                raise RuntimeError("RESEND_API_KEY is not set")
            return 0
        sent = 0
        for message in email_messages:
            if self._send_one(message):
                sent += 1
        return sent

    def _payload(self, message):
        from_addr = message.from_email or getattr(settings, "DEFAULT_FROM_EMAIL", "")
        text_body = message.body or ""
        html_body = None
        for content, mimetype in getattr(message, "alternatives", []) or []:
            if mimetype == "text/html":
                html_body = content
                break

        payload = {
            "from": from_addr,
            "to": _addr_list(message.to),
            "subject": message.subject or "",
        }
        if message.cc:
            payload["cc"] = _addr_list(message.cc)
        if message.bcc:
            payload["bcc"] = _addr_list(message.bcc)
        if message.reply_to:
            payload["reply_to"] = _addr_list(message.reply_to)
        if html_body:
            payload["html"] = html_body
            if text_body:
                payload["text"] = text_body
        else:
            payload["text"] = text_body

        attachments = []
        for att in message.attachments or []:
            # Django delivers attachments either as (filename, content, mimetype)
            # tuples or as MIMEBase instances; only the tuple form is used by
            # this project (notifications.emails.send_branded_email).
            if isinstance(att, tuple):
                filename, content, _mimetype = (att + (None,) * 3)[:3]
                if isinstance(content, str):
                    content_bytes = content.encode("utf-8")
                else:
                    content_bytes = content or b""
                attachments.append({
                    "filename": filename or "attachment.bin",
                    "content": base64.b64encode(content_bytes).decode("ascii"),
                })
        if attachments:
            payload["attachments"] = attachments
        return payload

    def _send_one(self, message):
        try:
            payload = self._payload(message)
        except Exception:
            logger.exception("Resend: couldn't build payload for %r", getattr(message, "subject", ""))
            if not self.fail_silently:
                raise
            return False

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            RESEND_ENDPOINT,
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=ctx) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if 200 <= resp.status < 300:
                    return True
                logger.warning("Resend rejected email to %r: HTTP %s -- %s",
                               message.to, resp.status, body[:500])
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            logger.warning("Resend HTTP %s for email to %r: %s", exc.code, message.to, body[:500])
            if not self.fail_silently:
                raise
        except Exception:
            logger.exception("Resend request failed for email to %r", message.to)
            if not self.fail_silently:
                raise
        return False
