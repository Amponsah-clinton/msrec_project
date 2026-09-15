"""Server-side Paystack API calls, over stdlib urllib -- same pattern (and
same reasoning) as accounts/storage.py's Supabase Storage calls: this only
needs two endpoints, nowhere near enough surface to justify adding the
`paystack` package as a dependency.

Everything the applicant's browser does (the Inline popup, the client-side
"payment succeeded" callback) is UI only -- a Payment row is only ever
marked SUCCESS after this module's verify_transaction() gets a genuine
"success" status *and* the right amount/currency/reference back from
Paystack's own servers, called here with the secret key. Never trust the
client alone; that's how a site "runs at a loss."
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.paystack.co"


class PaystackError(Exception):
    pass


def secret_key():
    """The secret key actually used for server-side Paystack calls --
    SiteSettings' DB-editable override (admin_dashboard's Settings page)
    when set, otherwise the env-configured settings.PAYSTACK_SECRET_KEY.
    A local import avoids a pages<->payments import-time circular
    dependency (pages.models doesn't import payments, but keeping this
    lazy costs nothing and rules it out for good)."""
    from pages.models import SiteSettings
    return SiteSettings.get_solo().effective_paystack_secret_key


def _request(method, path, *, data=None):
    url = f"{API_BASE}{path}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {secret_key()}",
            "Content-Type": "application/json",
            # Paystack's API sits behind Cloudflare, which blocks Python's
            # default urllib User-Agent ("Python-urllib/3.x") as a bot
            # signature (Cloudflare error 1010) before the request ever
            # reaches Paystack -- a browser-shaped User-Agent is required,
            # not optional, for this module to work at all.
            "User-Agent": "Mozilla/5.0 (compatible; MSREC/1.0; +https://msrec.org)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        # Paystack still returns a JSON body (with "message") on 4xx --
        # surface that instead of a bare HTTP status.
        try:
            payload = json.loads(exc.read())
            raise PaystackError(payload.get("message", str(exc))) from exc
        except (ValueError, json.JSONDecodeError):
            raise PaystackError(str(exc)) from exc
    except urllib.error.URLError as exc:
        logger.exception("Paystack request failed: %s %s", method, path)
        raise PaystackError("Could not reach Paystack. Please try again.") from exc

    if not payload.get("status"):
        raise PaystackError(payload.get("message", "Paystack request was not successful."))
    return payload


def verify_transaction(reference):
    """GET /transaction/verify/:reference -- the only source of truth for
    whether a payment actually succeeded. Returns Paystack's `data` dict
    (status, amount, currency, paid_at, channel, ...)."""
    payload = _request("GET", f"/transaction/verify/{urllib.parse.quote(reference)}")
    return payload["data"]
