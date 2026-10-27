import os
from decimal import Decimal, InvalidOperation

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    """{% static %} plus ?v=<last modified>, so a browser fetches the new
    file as soon as it changes instead of running a cached old copy."""
    url = static(path)
    found = finders.find(path)
    if found:
        url += f"?v={int(os.path.getmtime(found))}"
    return url


@register.filter
def money(value):
    """2500 -> "2,500.00"; blank for no amount."""
    if value in (None, ""):
        return ""
    try:
        return f"{Decimal(value):,.2f}"
    except (InvalidOperation, ValueError, TypeError):
        return value


@register.filter
def get(mapping, key):
    """errors|get:"client_name" -- a dict lookup by a key held in a string."""
    try:
        return mapping.get(key, "")
    except AttributeError:
        return ""
