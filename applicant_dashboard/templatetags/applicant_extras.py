from datetime import date, datetime

from django import template

register = template.Library()


@register.filter
def as_date(value):
    """Parse an ISO date string into a real date so `|date:"d M Y"` can
    format it.

    Post-approval answers live in a jsonb blob (PostApprovalSubmission.
    form_data), so a `<input type="date">` arrives as the string
    "2026-05-18". Django's own `date` filter needs a date object and
    silently renders nothing for a string, which is why these were showing
    as raw ISO. Returns the value untouched if it isn't parseable, so a
    free-text answer still displays as whatever the applicant typed.
    """
    if isinstance(value, (datetime, date)):
        return value
    if not value:
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return value
