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
    # GovernanceMember rows with group=REVIEWER are shown under the
    # Reviewers tab (via _reviewer_profiles) rather than as plain members,
    # so they're excluded here.
    members = list(
        GovernanceMember.objects.filter(is_active=True)
        .exclude(group=GovernanceMember.Group.REVIEWER)
        .select_related("user")
    )
    for member in members:
        member.photo_url = _member_photo_url(member)
        member.avatar_color = _AVATAR_COLORS[member.pk % len(_AVATAR_COLORS)]

    # Every Committee member is also an approved Reviewer, so anyone
    # already shown as a Board/Committee/Secretariat card is flagged and
    # hidden from the "All" tab -- they still appear under "Reviewers".
    # Matched on the linked account where there is one, else on name; a
    # matched pair also shares whichever photo either side has.
    by_user = {m.user_id: m for m in members if m.user_id}
    by_name = {m.full_name.strip().lower(): m for m in members}
    reviewers = _reviewer_profiles()
    for reviewer in reviewers:
        member = by_user.get(reviewer["user_id"]) or by_name.get(reviewer["full_name"].strip().lower())
        reviewer["also_member"] = member is not None
        if member is not None:
            reviewer["photo_url"] = reviewer["photo_url"] or member.photo_url
            member.photo_url = member.photo_url or reviewer["photo_url"]

    counts = {
        "all": len(members) + sum(1 for r in reviewers if not r["also_member"]),
        "board": sum(1 for m in members if m.group == GovernanceMember.Group.BOARD),
        "committee": sum(1 for m in members if m.group == GovernanceMember.Group.COMMITTEE),
        "secretariat": sum(1 for m in members if m.group == GovernanceMember.Group.SECRETARIAT),
        "reviewer": len(reviewers),
    }

    return render(request, "pages/board_committee.html", {
        "members": members,
        "reviewers": reviewers,
        "counts": counts,
    })


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


def _reviewer_profiles():
    """MSREC's reviewers, as card dicts for the Board & Committee page's
    Reviewers tab -- pulled straight from the real, currently-approved
    Reviewer accounts (accounts.models.User, reviewer_status=APPROVED),
    the same live data every other part of this app treats as the source
    of truth for "who is a reviewer" (e.g. secretariat_dashboard's
    Reviewer Directory). A newly approved reviewer appears automatically,
    with no separate admin step.

    Any admin-curated GovernanceMember rows with group=REVIEWER (e.g. a
    featured profile with a fuller bio) are listed first, ahead of the
    auto-generated list, for whoever the Secretariat chooses to highlight.
    """
    from accounts.models import User
    from accounts.photos import profile_photo_url

    featured = list(
        GovernanceMember.objects.filter(is_active=True, group=GovernanceMember.Group.REVIEWER)
        .select_related("user")
    )
    featured_names = {m.full_name.strip().lower() for m in featured}
    members = []
    for member in featured:
        members.append({
            "user_id": member.user_id,
            "full_name": member.full_name,
            "display_name": member.display_name,
            "role_title": member.role_title,
            "tag": member.tag,
            "photo_url": _member_photo_url(member),
            "initials": member.initials,
            "avatar_color": _AVATAR_COLORS[member.pk % len(_AVATAR_COLORS)],
        })

    reviewer_accounts = (
        User.objects.filter(reviewer_status=User.RequestStatus.APPROVED, is_active=True)
        .order_by("first_name", "last_name")
    )
    for user in reviewer_accounts:
        if user.full_name.strip().lower() in featured_names:
            continue  # already shown as a featured profile above
        profile = user.reviewer_profile or {}
        position = (profile.get("reviewerPosition") or "").strip()
        institution = (profile.get("reviewerInstitution") or "").strip()
        discipline = (profile.get("reviewerDiscipline") or "").strip()
        role_title = ", ".join(part for part in (position, institution) if part) or "Ethics Reviewer"
        members.append({
            "user_id": user.pk,
            "full_name": user.full_name,
            "display_name": user.full_name,
            "role_title": role_title,
            "tag": discipline,
            "photo_url": profile_photo_url(user.profile_photo_path),
            "initials": user.initials,
            "avatar_color": _AVATAR_COLORS[user.pk % len(_AVATAR_COLORS)],
        })
    return members


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
