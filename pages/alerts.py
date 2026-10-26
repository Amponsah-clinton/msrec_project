"""Flash messages that can carry a heading as well as a body line.

django.contrib.messages only stores one string per message, but the
alert design (see templates/_alerts.html) has two slots: a bold heading
and a quieter line under it. Rather than add a parallel messaging
mechanism, the heading is packed in front of the body with a separator
the template splits back out -- so the message still survives the normal
cookie/session round trip and every existing plain messages.success(...)
call in the project keeps rendering exactly as before, just as a
single-line alert.

    from pages import alerts
    alerts.success(request, "Your application has been submitted.",
                   title="Application received")

The separator is U+001F UNIT SEPARATOR: a control character, so it can
never show up in a message somebody actually wrote.
"""

from django.contrib import messages

TITLE_SEP = "\x1f"


def pack(text, title=""):
    """Combine a heading and a body into one stored message string."""
    if not title:
        return str(text)
    return f"{title}{TITLE_SEP}{text}"


def unpack(stored):
    """Split a stored message back into (title, body).

    A message stored without a heading -- i.e. anything added through
    plain django.contrib.messages -- comes back as ("", body).
    """
    stored = str(stored)
    title, sep, body = stored.partition(TITLE_SEP)
    if not sep:
        return "", stored
    return title, body


def notify(request, level, text, title="", extra_tags=""):
    messages.add_message(request, level, pack(text, title), extra_tags=extra_tags)


def success(request, text, title="", extra_tags=""):
    notify(request, messages.SUCCESS, text, title, extra_tags)


def error(request, text, title="", extra_tags=""):
    notify(request, messages.ERROR, text, title, extra_tags)


def warning(request, text, title="", extra_tags=""):
    notify(request, messages.WARNING, text, title, extra_tags)


def info(request, text, title="", extra_tags=""):
    notify(request, messages.INFO, text, title, extra_tags)
