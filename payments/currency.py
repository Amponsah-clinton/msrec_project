"""Approximate US dollar equivalents for GHS prices.

Paystack charges MSREC's fees in Ghana Cedis -- that never changes, and
payments.paystack's verify_transaction() still checks the amount and
currency it was told to expect. The dollar figure this module produces is
a *guide* for participants registering from outside Ghana, shown beside the
cedi price so they know roughly what their card will be billed. It is never
the amount charged, and it is never stored on a payment row.

The rate (GHS per 1 USD) comes from, in order:

  1. USD_GHS_RATE in the environment -- a deliberate override. Set this to
     pin the quoted rate (e.g. to build in a little FX headroom) or when
     the host has no outbound internet.
  2. A live lookup, cached for RATE_TTL.

If neither yields a rate, every function here returns None and callers show
the cedi price alone. Showing nothing is always better than showing a
number that might be wrong, so nothing here ever guesses or falls back to a
stale hardcoded figure.

The lookup is cached hard in both directions -- a success for six hours, a
failure for fifteen minutes -- because this is read on the checkout page.
A payment page must never hang on, or hammer, a third-party rates API.
"""
import json
import logging
import os
import urllib.error
import urllib.request
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from django.core.cache import cache

logger = logging.getLogger(__name__)

# api.exchangerate-api.com's free, key-less endpoint. One field is read off
# it (rates.GHS); anything else in the response is ignored.
RATE_URL = "https://open.er-api.com/v6/latest/USD"
REQUEST_TIMEOUT = 3

CACHE_KEY = "msrec:usd_ghs_rate"
RATE_TTL = 6 * 60 * 60
FAILURE_TTL = 15 * 60
# Cached in place of a rate when the lookup fails, so a down API is asked
# again in FAILURE_TTL rather than on the next page view.
_NO_RATE = "none"

# A rate outside this range is a sign the response isn't what we think it
# is (a different base currency, a placeholder, a parse error), so it is
# discarded rather than shown to someone about to pay.
MIN_RATE = Decimal("1")
MAX_RATE = Decimal("1000")


def _env_rate():
    raw = (os.getenv("USD_GHS_RATE") or "").strip()
    if not raw:
        return None
    try:
        rate = Decimal(raw)
    except (InvalidOperation, ValueError):
        logger.warning("USD_GHS_RATE is not a number: %r", raw)
        return None
    return rate if MIN_RATE <= rate <= MAX_RATE else None


def _fetch_rate():
    """GHS per 1 USD from the live API, or None. Never raises."""
    req = urllib.request.Request(
        RATE_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; MSREC/1.0; +https://msrec.org)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError):
        logger.info("USD rate lookup failed", exc_info=True)
        return None

    try:
        rate = Decimal(str(payload["rates"]["GHS"]))
    except (KeyError, TypeError, InvalidOperation):
        logger.info("USD rate response had no usable GHS rate")
        return None
    return rate if MIN_RATE <= rate <= MAX_RATE else None


def usd_rate():
    """GHS per 1 USD, or None when no rate can be established."""
    pinned = _env_rate()
    if pinned is not None:
        return pinned

    cached = cache.get(CACHE_KEY)
    if cached == _NO_RATE:
        return None
    if cached is not None:
        return Decimal(cached)

    rate = _fetch_rate()
    if rate is None:
        cache.set(CACHE_KEY, _NO_RATE, FAILURE_TTL)
        return None
    cache.set(CACHE_KEY, str(rate), RATE_TTL)
    return rate


def to_usd(ghs_amount):
    """`ghs_amount` in cedis as an approximate USD Decimal (2dp), or None.

    Only converts from GHS: a price already quoted in another currency is
    returned as None rather than being converted as if it were cedis.
    """
    if ghs_amount is None:
        return None
    try:
        amount = Decimal(str(ghs_amount))
    except (InvalidOperation, ValueError):
        return None
    if amount <= 0:
        return None

    rate = usd_rate()
    if not rate:
        return None
    return (amount / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def usd_display(ghs_amount, currency="GHS"):
    """"US$12.50" for a cedi amount, or "" when there's nothing to show.

    `currency` is the currency `ghs_amount` is actually in -- anything but
    GHS returns "", since converting it would be a guess.
    """
    if (currency or "GHS").upper() != "GHS":
        return ""
    usd = to_usd(ghs_amount)
    return f"US${usd}" if usd is not None else ""
