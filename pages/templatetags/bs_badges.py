"""Maps the colour names the dashboards' Python code emits ("green", "orange",
...) to Bootstrap badge colour classes, so a template can write

    <span class="badge {{ row.badge|bs_badge }}">...</span>

The colour names themselves are unchanged (they're also used by the PDF
exports), only their rendering on the web is Bootstrap's.
"""

from django import template

register = template.Library()

BS_COLORS = {
    "blue": "text-bg-primary",
    "green": "text-bg-success",
    "red": "text-bg-danger",
    "orange": "text-bg-warning",
    "amber": "text-bg-warning",
    "teal": "text-bg-info",
    "gray": "text-bg-secondary",
    "grey": "text-bg-secondary",
    "purple": "text-bg-purple",
    "navy": "text-bg-dark",
}

# Inquiry.Reason -> the colour each reason has always had in the inbox.
INQUIRY_REASON_COLORS = {
    "secretariat": "navy",
    "application-support": "blue",
    "application_support": "blue",
    "complaints": "red",
    "ethics-concerns": "purple",
    "ethics_concerns": "purple",
    "technical-support": "teal",
    "technical_support": "teal",
}


@register.filter
def bs_badge(color):
    """'green' -> 'text-bg-success'. Unknown names fall back to secondary."""
    return BS_COLORS.get(str(color or "").strip().lower(), "text-bg-secondary")


@register.filter
def inquiry_badge(reason):
    """An Inquiry.reason value -> its Bootstrap colour class."""
    return bs_badge(INQUIRY_REASON_COLORS.get(str(reason or "").strip().lower(), "gray"))


# Every state word the dashboards render as a badge, with the colour it has
# always had -- so `class="badge {{ meeting.status|state_badge }}"` needs no
# per-component colour rules.
STATE_COLORS = {
    # RSVP / meetings
    "accepted": "green", "pending": "orange", "declined": "red", "tentative": "purple",
    "scheduled": "blue", "completed": "green", "cancelled": "red", "canceled": "red",
    "live": "red", "overdue": "red", "due-soon": "orange", "due_soon": "orange",
    "on-track": "teal", "on_track": "teal",
    # appointments / training expiry
    "current": "green", "expiring": "orange", "expired": "red", "ongoing": "gray",
    # reviewer availability
    "available": "green", "limited": "orange", "unavailable": "red",
    # inquiries
    "new": "orange", "resolved": "teal",
}


@register.filter
def state_badge(state):
    """A state word ('accepted', 'expiring', ...) -> its Bootstrap colour class.
    Unknown or empty states render as a neutral secondary badge."""
    return bs_badge(STATE_COLORS.get(str(state or "").strip().lower(), "gray"))


ACCOUNT_CATEGORY_COLORS = {
    "pending": "orange", "applicants": "blue", "reviewers": "teal",
    "committee": "purple", "admins": "navy",
}


@register.filter
def acct_role_badge(category):
    """Admin Accounts 'category' (pending/applicants/...) -> Bootstrap colour class."""
    return bs_badge(ACCOUNT_CATEGORY_COLORS.get(str(category or "").strip().lower(), "gray"))
