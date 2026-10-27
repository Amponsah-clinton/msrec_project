from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


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
