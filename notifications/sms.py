"""BMS / mNotify SMS integration.

The API contract (https://developer.bms.africa/):
    * base URL   : https://api.mnotify.com/api
    * auth       : ?key=<BMS_API_KEY> as a query parameter (not a header)
    * send bulk  : POST /sms/quick   with JSON
                   {recipient: [...], sender, message, is_schedule: false, schedule_date: ""}
    * check bal  : GET  /balance/sms

Ghana numbers reach the API in local ten-digit form (leading zero, e.g.
"0241234567"). We accept anything a user might paste ("+233 24 123 4567",
"+233241234567", "233241234567", "0241234567") and coerce here so callers
don't have to think about it.

Same fail-silently contract as notifications.emails.send_branded_email: an
outbound network or credit error never blocks the workflow that triggered
it. The caller gets back a dict describing what happened, but doesn't have
to check it -- a failed SMS just logs and moves on.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Iterable
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.mnotify.com/api"
QUICK_ENDPOINT = f"{BASE_URL}/sms/quick"
BALANCE_ENDPOINT = f"{BASE_URL}/balance/sms"

# BMS caps a sender ID at 11 characters. Anything longer is rejected by
# the API with a validation error, so trim locally rather than surface
# their generic 400 to the operator.
SENDER_MAX_LEN = 11

# A single-segment GSM-7 SMS is 160 chars; concatenated segments cost one
# credit each and top out at 153 chars per segment. Unicode drops the
# limit to 70 (single) / 67 (concat). We only surface this to the UI as
# "you're about to send N segments -- N credits" so the operator can
# shorten before hitting Send.
GSM_SINGLE = 160
GSM_MULTI = 153
UNICODE_SINGLE = 70
UNICODE_MULTI = 67

# The mNotify GSM-7 character set (default alphabet + basic extensions).
# Anything outside falls back to UCS-2 pricing, so the operator sees a
# realistic segment count even when a copy-paste smart quote or emoji
# sneaks in.
_GSM_CHARSET = set(
    "@£$¥èéùìòÇ\nØø\rÅå"
    "Δ_ΦΓΛΩΠΨΣΘΞÆæßÉ"
    " !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
    "¿abcdefghijklmnopqrstuvwxyzäöñüà"
    "\f^{}\\[~]|€"
)


def _api_key():
    return (getattr(settings, "BMS_API_KEY", "") or "").strip()


def _sender_id():
    raw = (getattr(settings, "BMS_SENDER_ID", "") or "MSREC").strip() or "MSREC"
    return raw[:SENDER_MAX_LEN]


def is_configured():
    return bool(_api_key())


# ---- phone-number normalisation -------------------------------------

_DIGITS_RE = re.compile(r"\D+")


def clean_phone(raw):
    """Local Ghana form ("0201234567") or "" if this isn't a Ghanaian
    mobile number we can send to. Accepts +233..., 233..., leading 0,
    with or without spaces/dashes/parentheses."""
    if raw is None:
        return ""
    digits = _DIGITS_RE.sub("", str(raw))
    if not digits:
        return ""
    if digits.startswith("233"):
        digits = "0" + digits[3:]
    # A Ghana mobile is exactly 10 digits starting with 02 or 05.
    if len(digits) == 10 and digits[0] == "0" and digits[1] in "25":
        return digits
    return ""


def clean_phones(raws: Iterable[str]):
    """De-duplicated, order-preserving list of clean numbers."""
    out, seen = [], set()
    for raw in raws:
        c = clean_phone(raw)
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


# ---- segment / cost preview -----------------------------------------


def segments(message):
    """(count, encoding) -- how many segments (= credits) this message
    will cost, and whether it's GSM-7 or Unicode. Matches BMS's own
    counting so what the UI shows before Send is what the API charges."""
    text = message or ""
    encoding = "gsm" if all(ch in _GSM_CHARSET for ch in text) else "unicode"
    if encoding == "gsm":
        limit_single, limit_multi = GSM_SINGLE, GSM_MULTI
    else:
        limit_single, limit_multi = UNICODE_SINGLE, UNICODE_MULTI
    length = len(text)
    if length == 0:
        return 0, encoding
    if length <= limit_single:
        return 1, encoding
    # Ceiling division for concatenated segments.
    return (length + limit_multi - 1) // limit_multi, encoding


# ---- network calls --------------------------------------------------


def _post_json(url, payload, timeout=15):
    key = _api_key()
    if not key:
        return {"ok": False, "error": "BMS_API_KEY is not set in the environment."}
    full = f"{url}?key={key}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        full,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status_code = response.status
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        status_code = exc.code
    except URLError as exc:
        logger.exception("BMS SMS network error: %s", exc)
        return {"ok": False, "error": f"Network error: {exc.reason}"}
    except Exception as exc:  # noqa: BLE001 -- surface anything as a soft failure
        logger.exception("BMS SMS unexpected error")
        return {"ok": False, "error": str(exc)}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw": raw}

    # BMS marks success with status: "success" (their code "2000" is only
    # returned on some endpoints, and the docs are inconsistent about it).
    # Trust status: "success" as the primary signal; fall back to code.
    ok = status_code == 200 and (
        (data.get("status") == "success")
        or str(data.get("code") or "") == "2000"
    )
    return {"ok": ok, "status": status_code, "data": data}


def _get_json(url, timeout=15):
    key = _api_key()
    if not key:
        return {"ok": False, "error": "BMS_API_KEY is not set in the environment."}
    full = f"{url}?key={key}"
    req = urllib_request.Request(full, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib_request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status_code = response.status
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        status_code = exc.code
    except URLError as exc:
        logger.exception("BMS balance network error: %s", exc)
        return {"ok": False, "error": f"Network error: {exc.reason}"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("BMS balance unexpected error")
        return {"ok": False, "error": str(exc)}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw": raw}
    ok = status_code == 200 and (
        (data.get("status") == "success")
        or str(data.get("code") or "") == "2000"
    )
    return {"ok": ok, "status": status_code, "data": data}


# ---- public callable API --------------------------------------------


def send_sms(recipients, message, sender=None):
    """Send one message to one or many Ghana numbers. Returns a status
    dict; never raises.

    result = {
        "ok"           : True/False,
        "sent_to"      : ["0241234567", ...],   # normalised numbers actually posted
        "rejected"     : ["...bad number..."],  # inputs we couldn't clean
        "credit_used"  : int or None,
        "credit_left"  : int or None,
        "campaign_id"  : str or None,           # BMS calls this _id
        "provider"     : { raw JSON from BMS }, # for logs / debug panel
        "error"        : "<human message>",     # only when ok is False
    }
    """
    recipients = clean_phones(list(recipients or []))
    raw_input = list(recipients or [])
    rejected = []
    message = (message or "").strip()

    result = {
        "ok": False,
        "sent_to": [],
        "rejected": rejected,
        "credit_used": None,
        "credit_left": None,
        "campaign_id": None,
        "provider": None,
        "error": None,
    }

    if not recipients:
        result["error"] = "No valid Ghana phone numbers to send to."
        return result
    if not message:
        result["error"] = "The message body is empty."
        return result

    payload = {
        "recipient": recipients,
        "sender": (sender or _sender_id())[:SENDER_MAX_LEN],
        "message": message,
        "is_schedule": False,
        "schedule_date": "",
    }
    response = _post_json(QUICK_ENDPOINT, payload)
    result["provider"] = response.get("data")
    if not response.get("ok"):
        data = response.get("data") or {}
        result["error"] = (
            response.get("error")
            or data.get("message")
            or f"BMS returned HTTP {response.get('status')} without a success code."
        )
        return result

    data = response.get("data") or {}
    summary = data.get("summary") or {}
    result["ok"] = True
    result["sent_to"] = summary.get("numbers_sent") or recipients
    result["credit_used"] = summary.get("credit_used")
    result["credit_left"] = summary.get("credit_left")
    result["campaign_id"] = summary.get("_id")
    return result


def sms_balance():
    """Remaining SMS credits, or None if we can't reach the API."""
    response = _get_json(BALANCE_ENDPOINT)
    if not response.get("ok"):
        return None
    data = response.get("data") or {}
    return data.get("balance") or (data.get("data") or {}).get("balance") or data.get("sms_balance")


# ---- user-focused helpers used by other flows -----------------------


def can_sms_user(user):
    """Whether we're allowed to text this user AT ALL: they have a valid
    Ghana phone and haven't opted out. Any email flow that wants an SMS
    twin gates on this so the SMS doesn't fire for users we can't
    actually reach."""
    if not user or not getattr(user, "phone", None):
        return False
    if hasattr(user, "sms_notifications_enabled") and not user.sms_notifications_enabled:
        return False
    return bool(clean_phone(user.phone))


def send_user_sms(user, message):
    """Convenience: send `message` to `user` if we can reach them, or
    return a benign no-op result if we can't. Same shape as send_sms."""
    if not can_sms_user(user):
        return {"ok": False, "sent_to": [], "rejected": [], "credit_used": None,
                "credit_left": None, "campaign_id": None, "provider": None,
                "error": "User has no reachable phone number or has opted out of SMS."}
    return send_sms([user.phone], message)
