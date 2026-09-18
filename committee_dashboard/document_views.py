"""Committee member Governance Documents -- Charter, Terms of Reference,
SOPs and Committee Policies.

There's no table of its own: every page reads pages.PolicyDocument (the
Supabase `policy_documents` table) filtered by category, live on each
request. An admin adds a document under Settings -> Policy Library and it
appears on the matching page immediately, with no publishing step.
"""
from datetime import timedelta
from pathlib import PurePosixPath

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from accounts.models import User
from notifications import services as notification_services
from notifications.models import Notification
from pages import documents_storage
from pages.models import PolicyDocument

NEW_FOR = timedelta(days=14)

Cat = PolicyDocument.Category

# url kwarg `page` -> what that page shows.
DOC_PAGES = {
    "charter": {
        "category": Cat.CHARTER, "title": "Committee Charter",
        "blurb": "The founding document that sets out MSREC's mandate, authority, independence and composition.",
        "empty": "The Committee Charter has not been published yet.",
    },
    "terms": {
        "category": Cat.TERMS, "title": "Terms of Reference",
        "blurb": "What the committee is responsible for, how it is appointed and how it conducts its business.",
        "empty": "No Terms of Reference have been published yet.",
    },
    "sops": {
        "category": Cat.SOP, "title": "Standard Operating Procedures",
        "blurb": "The step-by-step procedures MSREC follows to review, decide and monitor research.",
        "empty": "No SOPs have been published yet.",
    },
    "policies": {
        "category": Cat.COMMITTEE_POLICY, "title": "Committee Policies",
        "blurb": "Policies that apply to committee members, such as conflict of interest, confidentiality and conduct.",
        "empty": "No committee policies have been published yet.",
    },
}
TAB_ORDER = ["charter", "terms", "sops", "policies"]

# extension -> (label, tile colour class in governance-docs.css)
FILE_KINDS = {
    "pdf": ("PDF", "pdf"),
    "doc": ("DOC", "doc"), "docx": ("DOCX", "doc"),
    "xls": ("XLS", "xls"), "xlsx": ("XLSX", "xls"),
    "ppt": ("PPT", "ppt"), "pptx": ("PPTX", "ppt"),
}


def _is_committee(user):
    return (
        user.is_authenticated
        and user.role == User.Role.COMMITTEE
        and user.committee_status == User.RequestStatus.APPROVED
    )


committee_required = user_passes_test(_is_committee, login_url="pages:login")


@login_required
@committee_required
def documents(request, page):
    config = DOC_PAGES[page]
    now = timezone.now()

    docs = list(PolicyDocument.objects.filter(category=config["category"]))
    for doc in docs:
        doc.download_url = documents_storage.public_url(doc.file_path) if doc.file_path else None
        ext = PurePosixPath(doc.file_path).suffix.lstrip(".").lower() if doc.file_path else ""
        doc.kind_label, doc.kind_class = FILE_KINDS.get(ext, (ext.upper() or "FILE", "file"))
        doc.is_new = now - doc.created_at <= NEW_FOR
        doc.is_updated = not doc.is_new and doc.updated_at - doc.created_at > timedelta(minutes=5)

    counts = {
        row["category"]: row["n"]
        for row in PolicyDocument.objects.filter(
            category__in=[DOC_PAGES[k]["category"] for k in TAB_ORDER]
        ).values("category").annotate(n=Count("id"))
    }
    tabs = [
        {"key": key, "title": DOC_PAGES[key]["title"], "count": counts.get(DOC_PAGES[key]["category"], 0)}
        for key in TAB_ORDER
    ]

    audience = Notification.Audience.COMMITTEE
    return render(request, "dashboards/committee/governance_documents.html", {
        "notifications": notification_services.for_user(request.user, audience, limit=6),
        "unread_count": notification_services.unread_count(request.user, audience),
        "page": page,
        "config": config,
        "documents": docs,
        "tabs": tabs,
        "new_count": sum(1 for d in docs if d.is_new),
    })
