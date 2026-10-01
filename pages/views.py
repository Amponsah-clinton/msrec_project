from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from payments import fees
from . import resources_storage, storage, verification
from .models import ApplicantFAQ, ClientLogo, GovernanceMember, Inquiry, ResourceDocument, SiteSettings, Testimonial

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

    client_logos = list(ClientLogo.objects.all())
    for logo in client_logos:
        logo.image_url = storage.public_url(logo.image_path)

    testimonials = list(Testimonial.objects.all())
    for testimonial in testimonials:
        testimonial.image_url = storage.public_url(testimonial.image_path)

    from hall_of_fame.models import HallOfFameNomination
    from hall_of_fame import storage as hof_storage
    hof_featured = []
    for nom in HallOfFameNomination.objects.filter(status="published").order_by("-recognition_year", "full_name")[:6]:
        hof_featured.append({
            "pk": nom.pk,
            "full_name": nom.full_name,
            "professional_title": nom.professional_title,
            "institution": nom.institution,
            "recognition_year": nom.recognition_year,
            "photo_url": hof_storage.public_url(nom.photo_path) if nom.photo_path else None,
            "initials": "".join(w[0] for w in nom.full_name.split()[:2]).upper() if nom.full_name else "?",
            "avatar_color": _AVATAR_COLORS[nom.pk % len(_AVATAR_COLORS)],
        })

    return render(request, "pages/index.html", {
        # Same "What review costs" cards as the /applicants/ page's Fees
        # band -- the homepage's Review Fees section now reuses that
        # design (and its data) instead of the plainer fee_groups list it
        # used to render, so a visitor sees one consistent fee story
        # wherever they land.
        "fee_cards": _applicants_fee_cards(schedule),
        "exemption_fee": schedule.get("exemption"),
        "client_logos": client_logos,
        "testimonials": testimonials,
        "hero_image_url": SiteSettings.get_solo().hero_image_url,
        "hof_featured": hof_featured,
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


def _applicants_fee_cards(schedule):
    return [
        {**card, "amount": _fee_card_range(schedule, card["keys"])}
        for card in APPLICANTS_FEE_CARDS
    ]


def applicants(request):
    schedule = fees.schedule()
    return render(request, "pages/applicants.html", {
        "fee_cards": _applicants_fee_cards(schedule),
        "faqs": list(ApplicantFAQ.objects.filter(is_active=True)),
    })


# Public, unauthenticated lookup -- capped per client so the approval
# registry can't be enumerated or the verification codes brute-forced.
VERIFY_LIMIT = 30
VERIFY_WINDOW_SECONDS = 60


def _verify_rate_limited(request):
    key = f"verify-rate:{request.META.get('REMOTE_ADDR', 'unknown')}"
    cache.add(key, 0, VERIFY_WINDOW_SECONDS)
    try:
        return cache.incr(key) > VERIFY_LIMIT
    except ValueError:  # key expired between add() and incr()
        cache.set(key, 1, VERIFY_WINDOW_SECONDS)
        return False


def verify(request):
    return render(request, "pages/verify.html")


def verify_lookup(request):
    """GET /verify/lookup/?q=<approval number | verification code | verify URL>"""
    if _verify_rate_limited(request):
        response = JsonResponse(
            {"ok": False, "error": "Too many lookups. Please wait a minute and try again."}, status=429
        )
        response["Retry-After"] = str(VERIFY_WINDOW_SECONDS)
        return response

    result = verification.lookup(request.GET.get("q", ""))
    if result is None:
        return JsonResponse({"ok": False, "error": "Enter an approval number or verification code first."}, status=400)
    response = JsonResponse({"ok": True, **result})
    response["Cache-Control"] = "no-store"
    return response


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
    """Public Board & Committee page -- every card from live Supabase data
    (see build_governance_data). The admin management page at
    admin_dashboard uses the exact same builder, so its tab counts tally
    with this page to the number."""
    data = build_governance_data()
    return render(request, "pages/board_committee.html", {
        "members": data["members"],
        "reviewers": data["reviewers"],
        "counts": data["counts"],
    })


def build_governance_data():
    """Single source of truth for the Board & Committee page, shared by the
    public page and the admin management page so their counts always tally.

    Every card is an admin-curated GovernanceMember row -- nothing is pulled
    automatically from login accounts. A person only appears here once an
    admin adds them on the Board & Committee management page, under whichever
    group (Board / Committee / Secretariat / Reviewer) applies. Returns
    {"members", "reviewers", "counts"}; `members` is every non-reviewer card,
    `reviewers` the reviewer-group cards.
    """
    members = [
        _gov_card(m) for m in GovernanceMember.objects.filter(is_active=True)
        .exclude(group=GovernanceMember.Group.REVIEWER)
        .select_related("user")
    ]
    reviewers = [
        _gov_card(m) for m in GovernanceMember.objects.filter(
            is_active=True, group=GovernanceMember.Group.REVIEWER
        ).select_related("user")
    ]
    for reviewer in reviewers:
        reviewer["also_member"] = False

    counts = {
        "all": len(members) + len(reviewers),
        "board": sum(1 for m in members if m["group"] == GovernanceMember.Group.BOARD),
        "committee": sum(1 for m in members if m["group"] == GovernanceMember.Group.COMMITTEE),
        "secretariat": sum(1 for m in members if m["group"] == GovernanceMember.Group.SECRETARIAT),
        "reviewer": len(reviewers),
    }
    return {"members": members, "reviewers": reviewers, "counts": counts}


def reviewers(request):
    """The old standalone Reviewers page now lives as a tab under Board &
    Committee's Member Profiles -- kept as a redirect so existing links
    and bookmarks still land somewhere sensible."""
    return redirect(reverse("pages:board_committee") + "#bc-profiles")


def _member_photo_url(member):
    """A GovernanceMember's own uploaded photo, falling back to the
    profile photo on their linked login account (if any)."""
    from accounts.photos import profile_photo_url

    if member.photo_path:
        return storage.public_url(member.photo_path)
    if member.user_id:
        return profile_photo_url(member.user.profile_photo_path)
    return None


def _gov_card(member):
    """A curated GovernanceMember row as a uniform card dict. `editable` so
    the admin page can offer Edit/Delete on it."""
    return {
        "user_id": member.user_id,
        "group": member.group,
        "group_label": member.get_group_display(),
        "full_name": member.full_name,
        "display_name": member.display_name,
        "role_title": member.role_title,
        "tag": member.tag,
        "photo_url": _member_photo_url(member),
        "initials": member.initials,
        "avatar_color": _AVATAR_COLORS[member.pk % len(_AVATAR_COLORS)],
        # Admin management metadata (ignored by the public page).
        "editable": True,
        "pk": member.pk,
        "title": member.title,
        "display_order": member.display_order,
        "is_active": member.is_active,
        "created_at": member.created_at,
    }


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
