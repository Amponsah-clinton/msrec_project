"""Template tags backing the shared admin topbar.

The notification bell used to be ~30 lines of invented notices pasted into
each admin template, which meant five copies of the same fiction and a
badge reading "5" above a list of two. It is derived here instead, from
work that is actually outstanding right now: a role request nobody has
decided, an inquiry nobody has answered, an application nobody has picked
up. That has two consequences worth knowing:

  * There is nothing to "mark as read". An item leaves the bell when the
    work behind it is done, not when someone dismisses it, so the old
    mark-all-read control is gone rather than lying about what it does.
  * The badge and the list can never disagree -- the badge IS the length
    of the list.

This deliberately does not use the `notifications` app: that model is a
broadcast-to-an-audience log (audience='secretariat' only today), and its
rows are written when an event happens. What an admin needs in the bell
is the opposite -- the current backlog, which is a question about present
state, not about past events.
"""

import re

from django import template

from accounts.models import User
from applicant_dashboard import oversight
from applicant_dashboard.models import Application
from pages.models import Inquiry

register = template.Library()


# Initialisms that should stay upper-case when a form field's name is turned
# back into a human label. Everything not listed here is simply capitalised.
# "no" is deliberately absent: in these field names it is the abbreviation
# for "number" ("irbReferenceNo"), not the word NO.
_ACRONYMS = {"pi", "irb", "hod", "orcid", "id", "url", "coi", "sop", "dsmb"}


@register.filter
def field_label(key):
    """Turn an application form's field name into something readable.

    The "All submitted answers" list renders whatever keys the form posted,
    which are camelCase (`piName`, `studyPurpose`, `irbReferenceNo`). Shown
    raw they read as debug output, so split on the capitals and fix up the
    initialisms: `irbReferenceNo` -> `IRB Reference No`.
    """
    if not isinstance(key, str):
        return key
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", key.replace("_", " ").replace("-", " "))
    words = [w for w in spaced.split() if w]
    return " ".join(
        w.upper() if w.lower() in _ACRONYMS else w[:1].upper() + w[1:]
        for w in words
    )


def _attention_items():
    pending_roles = (
        User.objects.filter(reviewer_status=User.RequestStatus.PENDING)
        | User.objects.filter(committee_status=User.RequestStatus.PENDING)
    ).distinct().count()

    new_inquiries = Inquiry.objects.filter(status=Inquiry.Status.NEW).count()

    awaiting_screening = (
        oversight.staff_queryset()
        .filter(status=Application.Status.SUBMITTED)
        .count()
    )

    items = []
    if pending_roles:
        items.append({
            "tone": "warn",
            "text": (
                f"{pending_roles} role request{'s' if pending_roles != 1 else ''} "
                f"awaiting your approval."
            ),
            "url_name": "admin_dashboard:accounts",
            "query": "?tab=pending",
        })
    if awaiting_screening:
        items.append({
            "tone": "info",
            "text": (
                f"{awaiting_screening} application{'s' if awaiting_screening != 1 else ''} "
                f"submitted and not yet screened."
            ),
            "url_name": "admin_dashboard:applications",
            "query": "?tab=submitted",
        })
    if new_inquiries:
        items.append({
            "tone": "info",
            "text": (
                f"{new_inquiries} unanswered "
                f"{'inquiries' if new_inquiries != 1 else 'inquiry'} from the contact form."
            ),
            "url_name": "admin_dashboard:inquiries",
            "query": "?tab=new",
        })

    return items


@register.inclusion_tag("dashboards/admin/_bell.html")
def admin_bell():
    items = _attention_items()
    return {"items": items, "unread_count": len(items)}


@register.inclusion_tag("dashboards/admin/_attention_panel.html")
def admin_attention_panel():
    """The dashboard home's version of the same list -- same source, so the
    panel and the bell can never tell the admin two different stories."""
    return {"items": _attention_items()}
