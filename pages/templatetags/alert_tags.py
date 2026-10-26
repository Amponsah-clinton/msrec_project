"""Template filters backing templates/_alerts.html.

Keeps the mapping from a django.contrib.messages level to an alert
variant, and the title/body split, in Python instead of spreading a
chain of {% if message.tags == ... %} across the partial.
"""

from django import template
from django.contrib.messages import constants

from pages.alerts import unpack

register = template.Library()

# "error" and "debug" have no alert of their own: an error is the danger
# box, and a debug message is informational.
LEVEL_VARIANTS = {
    constants.DEBUG: "info",
    constants.INFO: "info",
    constants.SUCCESS: "success",
    constants.WARNING: "warning",
    constants.ERROR: "danger",
}


@register.filter
def alert_variant(message):
    """success | danger | warning | info for one message."""
    level = getattr(message, "level", constants.INFO)
    # Levels in between the constants (a custom level, or one raised
    # above ERROR) round down to the nearest standard severity rather
    # than silently falling back to "info".
    if level in LEVEL_VARIANTS:
        return LEVEL_VARIANTS[level]
    for threshold in sorted(LEVEL_VARIANTS, reverse=True):
        if level >= threshold:
            return LEVEL_VARIANTS[threshold]
    return "info"


@register.filter
def alert_title(message):
    """The message's heading, or "" when it was added without one."""
    return unpack(message)[0]


@register.filter
def alert_text(message):
    """The message's body line, minus any packed heading."""
    return unpack(message)[1]
