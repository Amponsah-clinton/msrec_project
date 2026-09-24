"""Talks to the language-model providers behind the MSREC Assistant.

Providers are tried in order and the first one that answers wins:

  1. Gemini  -- GEMINI_MODEL           (default gemini-2.5-flash: fast)
  2. Gemini  -- GEMINI_FALLBACK_MODEL  (default gemini-3.6-flash)
  3. Groq    -- GROQ_MODEL             (default llama-3.3-70b-versatile)

A provider with no API key configured is skipped, and a timeout, rate
limit or server error just moves on to the next one, so a single
provider's outage never takes the assistant down. Plain HTTPS via urllib
(the same approach as every other external call in this project), so no
extra SDK dependency.

Keys live only in the environment (.env locally, the host's settings in
production) and are never logged or sent to the browser.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT = 25
MAX_OUTPUT_TOKENS = 900
TEMPERATURE = 0.35


def _post(url, payload, headers):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "msrec-assistant/1.0", **headers},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _gemini(model, system, messages):
    key = getattr(settings, "GEMINI_API_KEY", "")
    if not key or not model:
        return None
    generation = {"temperature": TEMPERATURE, "maxOutputTokens": MAX_OUTPUT_TOKENS}
    # Keep "thinking" minimal: this is a help desk, and on newer models an
    # unbounded thinking budget can consume the whole output allowance.
    if model.startswith("gemini-2.5"):
        generation["thinkingConfig"] = {"thinkingBudget": 0}
    elif model.startswith("gemini-3"):
        generation["thinkingConfig"] = {"thinkingLevel": "low"}
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [
            {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
            for m in messages
        ],
        "generationConfig": generation,
    }
    data = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        payload,
        {"x-goog-api-key": key},
    )
    candidates = data.get("candidates") or []
    if not candidates:
        return None
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return text.strip() or None


def _groq(model, system, messages):
    key = getattr(settings, "GROQ_API_KEY", "")
    if not key or not model:
        return None
    data = _post(
        "https://api.groq.com/openai/v1/chat/completions",
        {
            "model": model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": TEMPERATURE,
            "max_tokens": MAX_OUTPUT_TOKENS,
        },
        {"Authorization": f"Bearer {key}"},
    )
    choices = data.get("choices") or []
    if not choices:
        return None
    return ((choices[0].get("message") or {}).get("content") or "").strip() or None


def complete(system, messages):
    """`messages`: [{"role": "user"|"assistant", "content": str}, ...],
    ending with the user's turn. Returns (reply_text, provider_label), or
    (None, None) if every provider failed."""
    chain = [
        ("gemini:" + settings.GEMINI_MODEL, _gemini, settings.GEMINI_MODEL),
        ("gemini:" + settings.GEMINI_FALLBACK_MODEL, _gemini, settings.GEMINI_FALLBACK_MODEL),
        ("groq:" + settings.GROQ_MODEL, _groq, settings.GROQ_MODEL),
    ]
    for label, call, model in chain:
        try:
            reply = call(model, system, messages)
        except urllib.error.HTTPError as exc:
            logger.warning("Assistant provider %s failed: HTTP %s", label, exc.code)
            continue
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            logger.warning("Assistant provider %s failed: %s", label, exc.__class__.__name__)
            continue
        if reply:
            return reply, label
    return None, None
