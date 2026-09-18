from django.http import JsonResponse
from django.shortcuts import render

from payments import fees
from . import resources_storage, storage
from .models import GovernanceMember, Inquiry, ResourceDocument

REASON_VALUES = {value for value, _ in Inquiry.Reason.choices}

# Groups the 9 Application Category tiers (payments.fees.
# APPLICANT_CATEGORY_LABELS) for the homepage's Review Fees section --
# same three-column rhythm the old hardcoded "Student / Standard /
# External" pricing cards had, but each column is now a real group of
# real, live-editable prices instead of three made-up numbers. Keyed
# here (not read from FeeSetting order) since the homepage's grouping
# is about applicant *type*, not the admin Finance page's flat list.
HOME_FEE_GROUPS = [
    ("Student Researchers", ["ug_diploma", "masters_mphil", "phd"]),
    ("Ghanaian Researchers", ["gh_independent", "gh_institutional", "gh_consultancy"]),
    ("International & Clinical", ["intl_student", "intl_funded", "clinical_trial"]),
]


def _fee_group_rows(schedule, keys):
    return [{"label": fees.label_for(key), "fee": schedule.get(key)} for key in keys]


def index(request):
    schedule = fees.schedule()
    fee_groups = [
        {"title": title, "rows": _fee_group_rows(schedule, keys)}
        for title, keys in HOME_FEE_GROUPS
    ]
    return render(request, "pages/index.html", {
        "fee_groups": fee_groups,
        "exemption_fee": schedule.get("exemption"),
    })


# Post-approval item order for the dedicated Fees page -- matches the
# order they'll eventually appear in the sidebar's Post-Approval
# Management group (see _secretariat_nav.html), not FeeSetting's own
# admin-editor order.
POST_APPROVAL_KEYS = [
    "minor_amendment", "major_amendment", "continuing_review",
    "corrected_resubmission", "closure",
]


def fees_schedule(request):
    # Expedited/Full Committee Review (payments.fees.REVIEW_TYPE_LABELS)
    # deliberately aren't shown here: a new application is priced by
    # Application Category, not by review pathway (MSREC assigns the
    # pathway during screening) -- see fees.fee_for_application(). The
    # one pathway that DOES carry its own flat rate regardless of
    # category is Determination/Exemption, called out on its own below.
    schedule = fees.schedule()
    return render(request, "pages/fees.html", {
        "fee_groups": [
            {"title": title, "rows": _fee_group_rows(schedule, keys)}
            for title, keys in HOME_FEE_GROUPS
        ],
        "exemption_fee": schedule.get("exemption"),
        "post_approval_rows": _fee_group_rows(schedule, POST_APPROVAL_KEYS),
    })


# The /applicants/ page's "What review costs" section groups the 9
# Application Category tiers into the same 4 illustrative cards it's
# always shown (Student / Standard Institutional / External-Industry /
# Amendment-Continuing) -- real, live-editable prices from the fee
# schedule instead of the placeholder $0/$150/$450/$50 the cards used to
# hardcode. A card spanning more than one category shows the low-high
# range across them rather than picking one arbitrarily.
APPLICANTS_FEE_CARDS = [
    {
        "title": "Student Applicant",
        "note": "For registered students at Metascholar-affiliated institutions.",
        "bullets": ["Full review pathway included", "Supervisor sign-off required"],
        "featured": False,
        "keys": ["ug_diploma", "masters_mphil", "phd"],
    },
    {
        "title": "Standard Institutional",
        "note": "For faculty, staff and institutional research.",
        "bullets": ["Full review pathway included", "One free amendment"],
        "featured": True,
        "keys": ["gh_independent", "gh_institutional", "gh_consultancy"],
    },
    {
        "title": "External / Industry",
        "note": "For externally sponsored or industry-funded research.",
        "bullets": ["Full review pathway included", "Data-sharing agreement review"],
        "featured": False,
        "keys": ["intl_student", "intl_funded", "clinical_trial"],
    },
    {
        "title": "Amendment / Continuing",
        "note": "For changes to an approved study, or annual continuing review.",
        "bullets": ["Proportional review only", "No new full submission needed"],
        "featured": False,
        "keys": ["minor_amendment", "continuing_review"],
    },
]


def _fee_card_range(schedule, keys):
    amounts = sorted({schedule[k].amount for k in keys if schedule.get(k)})
    if not amounts:
        return None
    return {"currency": fees.CURRENCY, "low": amounts[0], "high": amounts[-1]}


def applicants(request):
    schedule = fees.schedule()
    fee_cards = [
        {**card, "amount": _fee_card_range(schedule, card["keys"])}
        for card in APPLICANTS_FEE_CARDS
    ]
    return render(request, "pages/applicants.html", {"fee_cards": fee_cards})


def contact(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip()
        reason = request.POST.get("reason", "").strip()
        message = request.POST.get("message", "").strip()

        errors = {}
        if not name:
            errors["name"] = "Please enter your name."
        if not email:
            errors["email"] = "Please enter your email address."
        if reason not in REASON_VALUES:
            errors["reason"] = "Please choose a reason for contact."
        if not message:
            errors["message"] = "Please enter a message."

        if errors:
            return JsonResponse({"ok": False, "errors": errors}, status=400)

        Inquiry.objects.create(name=name, email=email, reason=reason, message=message)
        return JsonResponse({"ok": True})

    return render(request, "pages/contact.html")


# Deterministic avatar background colors, cycled by id -- same "no two
# adjacent cards look identical" variety the old hardcoded markup had
# (each person had its own --av-bg hex), without needing a color column.
_AVATAR_COLORS = ["#2a4747", "#7a4fb5", "#2f5fa8", "#1f7a5c", "#d97b29", "#c0392b", "#196D8A"]


def board_committee(request):
    members = list(GovernanceMember.objects.filter(is_active=True))
    for member in members:
        member.photo_url = storage.public_url(member.photo_path)
        member.avatar_color = _AVATAR_COLORS[member.pk % len(_AVATAR_COLORS)]

    counts = {
        "all": len(members),
        "board": sum(1 for m in members if m.group == GovernanceMember.Group.BOARD),
        "committee": sum(1 for m in members if m.group == GovernanceMember.Group.COMMITTEE),
        "secretariat": sum(1 for m in members if m.group == GovernanceMember.Group.SECRETARIAT),
    }

    return render(request, "pages/board_committee.html", {
        "members": members,
        "counts": counts,
    })


def resources(request):
    """Resource Centre page. Renders admin-uploaded ResourceDocument rows
    (grouped by category) above the site's own static forms/templates/
    guidance in each section -- see templates/pages/resources.html."""
    docs = list(ResourceDocument.objects.filter(is_published=True))
    for doc in docs:
        doc.download_url_ = resources_storage.public_url(doc.file_path)

    by_category = {value: [] for value, _label in ResourceDocument.Category.choices}
    for doc in docs:
        by_category[doc.category].append(doc)

    return render(request, "pages/resources.html", {"resources_by_category": by_category})
