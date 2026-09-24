"""The one endpoint behind the chat widget: POST /assistant/chat/.

Stateless: the browser sends the recent conversation with each question
(kept in its own sessionStorage), so nothing a visitor types is stored on
the server or logged. CSRF-protected like every other POST in the app, and
rate-limited per visitor so the public endpoint can't be used to run up
the AI provider bill.
"""
import json
import logging
import re

from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from . import knowledge, llm

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 1500
MAX_HISTORY = 12
MAX_TOTAL_CHARS = 12000
MAX_NAV_ITEMS = 40

# (window seconds, max requests) -- both must pass.
RATE_LIMITS = [(60, 8), (3600, 60)]

SAFE_PATH = re.compile(r"^/[A-Za-z0-9/_\-.?=&#%]*$")


def _client_key(request):
    if request.user.is_authenticated:
        return f"u{request.user.pk}"
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    return f"ip{ip}"


def _rate_limited(request):
    who = _client_key(request)
    for window, limit in RATE_LIMITS:
        key = f"assistant:rl:{window}:{who}"
        added = cache.add(key, 1, timeout=window)
        if not added:
            try:
                count = cache.incr(key)
            except ValueError:  # expired between add() and incr()
                cache.set(key, 1, timeout=window)
                count = 1
            if count > limit:
                return True
    return False


def _clean_text(value, limit):
    if not isinstance(value, str):
        return ""
    return value.replace("\x00", "").strip()[:limit]


def _clean_messages(raw):
    if not isinstance(raw, list):
        return None
    messages = []
    for item in raw[-MAX_HISTORY:]:
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            continue
        content = _clean_text(item.get("content"), MAX_MESSAGE_CHARS if item.get("role") == "user" else 4000)
        if content:
            messages.append({"role": item["role"], "content": content})
    # Must start with the user and end with the user's new question.
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    if not messages or messages[-1]["role"] != "user":
        return None
    # Trim oldest turns until the transcript fits the budget.
    while len(messages) > 1 and sum(len(m["content"]) for m in messages) > MAX_TOTAL_CHARS:
        messages.pop(0)
        while messages and messages[0]["role"] != "user":
            messages.pop(0)
    return messages or None


def _clean_nav(raw):
    if not isinstance(raw, list):
        return []
    nav, seen = [], set()
    for item in raw[:MAX_NAV_ITEMS]:
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("label"), 60)
        href = _clean_text(item.get("href"), 200)
        if label and href and SAFE_PATH.match(href) and href not in seen:
            seen.add(href)
            nav.append({"label": re.sub(r"[\[\]()]", "", label), "href": href})
    return nav


@require_POST
def chat(request):
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)

    messages = _clean_messages(body.get("messages"))
    if not messages:
        return JsonResponse({"error": "Please type a question."}, status=400)

    if _rate_limited(request):
        return JsonResponse(
            {"error": "You're sending messages quite quickly — please wait a moment and try again."},
            status=429,
        )

    page_raw = body.get("page") if isinstance(body.get("page"), dict) else {}
    page = {
        "title": _clean_text(page_raw.get("title"), 120),
        "path": _clean_text(page_raw.get("path"), 200) if SAFE_PATH.match(_clean_text(page_raw.get("path"), 200) or "/") else "",
    }
    # Sidebar links only mean anything for a signed-in user.
    nav = _clean_nav(body.get("nav")) if request.user.is_authenticated else []

    system = knowledge.build_system_prompt(request, page, nav, messages)
    reply, provider = llm.complete(system, messages)
    if not reply:
        logger.error("Assistant: every provider failed")
        return JsonResponse(
            {"error": "I can't reach my knowledge service right now. Please try again shortly, or contact the Secretariat via the Contact page."},
            status=503,
        )
    return JsonResponse({"reply": reply})
