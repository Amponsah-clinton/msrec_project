from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import User
from accounts.sessions import active_sessions_for

from . import storage
from .models import ReviewAssignment

TABS = {"all", "new", "accepted", "due_overdue", "completed"}

# Must match the pill checkboxes' `value`s on Profile & Expertise -- kept
# as an allowlist so a tampered POST can't stuff arbitrary strings into
# reviewer_profile.preferredCategories.
REVIEWER_CATEGORY_CHOICES = {
    "Expedited Review", "Full Committee Review", "Exempt Review", "Continuing Review",
}

# Suggested chips on the Areas of Expertise picker -- whichever the
# reviewer hasn't already chosen are offered as one-click add buttons.
EXPERTISE_SUGGESTIONS = [
    "Clinical Trials", "Social & Behavioural Sciences", "Maternal & Child Health",
    "Infectious Disease", "Health Systems", "Public Health", "Biomedical Research", "Epidemiology",
]


def is_reviewer(user):
    return (
        user.is_authenticated
        and user.role == User.Role.REVIEWER
        and user.reviewer_status == User.RequestStatus.APPROVED
    )


reviewer_required = user_passes_test(is_reviewer, login_url="pages:login")


def _assignments_for(user):
    # Declined assignments are the reviewer's own closed-out "no" -- they
    # don't belong in any of the four tabs, so they're excluded up front
    # rather than needing every caller to remember to filter them out.
    return (
        ReviewAssignment.objects.filter(reviewer=user)
        .exclude(status=ReviewAssignment.Status.DECLINED)
        .select_related("application")
    )


def _counts(assignments):
    counts = {"all": 0, "new": 0, "accepted": 0, "due_overdue": 0, "completed": 0}
    for assignment in assignments:
        counts["all"] += 1
        counts[assignment.tab] += 1
    return counts


def _annotate_due(assignment):
    """Attach days_remaining (negative once overdue) and a CSS urgency
    bucket so the template can style the due date without doing date math
    itself."""
    if assignment.due_date:
        assignment.days_remaining = (assignment.due_date - timezone.localdate()).days
        assignment.days_overdue = -assignment.days_remaining if assignment.days_remaining < 0 else 0
        if assignment.days_remaining < 0 or assignment.days_remaining <= 3:
            assignment.due_urgency = "danger"
        elif assignment.days_remaining <= 7:
            assignment.due_urgency = "warn"
        else:
            assignment.due_urgency = "muted"
    else:
        assignment.days_remaining = None
        assignment.days_overdue = 0
        assignment.due_urgency = "muted"
    return assignment


@login_required
@reviewer_required
def dashboard_home(request):
    assignments = list(_assignments_for(request.user).order_by("due_date"))
    for assignment in assignments:
        assignment.tab_value = assignment.tab
        _annotate_due(assignment)

    counts = _counts(assignments)
    pending_coi = [a for a in assignments if a.tab != "completed" and not a.coi_declared]

    # Soonest-due active assignment gets the "urgent" banner -- accepted and
    # already due/overdue take priority over one that's merely new.
    active = [a for a in assignments if a.tab in ("accepted", "due_overdue") and a.due_date]
    urgent = min(active, key=lambda a: a.due_date, default=None)

    # Assigned Reviews table: everything still open, soonest due first,
    # capped to a short list -- "My Reviews" is where the full set lives.
    open_assignments = [a for a in assignments if a.tab != "completed"][:5]

    return render(request, "dashboards/reviewer.html", {
        "stat_new": counts["new"],
        "stat_accepted": counts["accepted"],
        "stat_in_progress": counts["due_overdue"],
        "stat_completed": counts["completed"],
        "pending_coi_count": len(pending_coi),
        "urgent_assignment": urgent,
        "open_assignments": open_assignments,
    })


@login_required
@reviewer_required
def my_reviews(request):
    active_tab = request.GET.get("tab", "all")
    if active_tab not in TABS:
        active_tab = "all"

    assignments = list(_assignments_for(request.user).order_by("-assigned_at"))
    for assignment in assignments:
        assignment.tab_value = assignment.tab

    return render(request, "dashboards/reviewer/my-reviews.html", {
        "assignments": assignments,
        "counts": _counts(assignments),
        "active_tab": active_tab,
    })


@login_required
@reviewer_required
def my_reviews_counts(request):
    """Polled by live-counts.js to keep the My Reviews tab badges current
    without a page reload -- e.g. the Secretariat assigns a new review
    while this page is already open."""
    return JsonResponse(_counts(_assignments_for(request.user)))


# ---------------------------------------------------------------------
# Profile & Expertise
# ---------------------------------------------------------------------

def _handle_update_profile(request):
    user = request.user
    title = request.POST.get("title", "").strip()
    first_name = request.POST.get("first_name", "").strip()
    last_name = request.POST.get("last_name", "").strip()
    phone = request.POST.get("phone", "").strip()
    orcid = request.POST.get("orcid", "").strip()
    email = request.POST.get("email", "").strip().lower()

    if not first_name or not last_name:
        messages.error(request, "First and last name are required.")
        return
    if not email:
        messages.error(request, "Email is required.")
        return
    if User.objects.exclude(pk=user.pk).filter(email=email).exists():
        messages.error(request, "Another account already uses that email address.")
        return

    institution = request.POST.get("institution", "").strip()
    position = request.POST.get("position", "").strip()
    degree = request.POST.get("degree", "").strip()
    years_experience = request.POST.get("years_experience", "").strip()
    expertise = request.POST.get("expertise", "").strip()
    bio = request.POST.get("bio", "").strip()
    max_reviews = request.POST.get("max_concurrent_reviews", "").strip()
    preferred_categories = [
        c for c in request.POST.getlist("preferred_categories") if c in REVIEWER_CATEGORY_CHOICES
    ]

    # The Secretariat's Reviewer Directory reads reviewer_profile.reviewer*
    # keys first, falling back to these same top-level columns (see
    # secretariat_dashboard's reviewer-directory.html) -- and
    # admin_dashboard's Accounts page edits the top-level columns
    # directly. Writing both here is what keeps every screen that shows a
    # reviewer's institution/position in sync with this one save.
    user.title = title
    user.first_name = first_name
    user.last_name = last_name
    user.phone = phone
    user.orcid = orcid
    user.email = email
    user.institution = institution
    user.position = position

    # Binary self-report: a reviewer can only declare themselves
    # available or unavailable. "Limited" stays a Secretariat-only
    # capacity override (see accounts.models.User.reviewer_availability).
    available = bool(request.POST.get("available_for_assignments"))
    if user.reviewer_availability != User.Availability.LIMITED or available:
        user.reviewer_availability = (
            User.Availability.AVAILABLE if available else User.Availability.UNAVAILABLE
        )

    profile = dict(user.reviewer_profile or {})
    profile["reviewerInstitution"] = institution
    profile["reviewerPosition"] = position
    profile["reviewerDiscipline"] = degree
    profile["reviewerYearsResearch"] = years_experience
    profile["reviewerExpertise"] = expertise
    profile["reviewerBio"] = bio
    profile["reviewerOrcid"] = orcid
    profile["maxConcurrentReviews"] = max_reviews
    profile["preferredCategories"] = preferred_categories
    user.reviewer_profile = profile

    user.save(update_fields=[
        "title", "first_name", "last_name", "phone", "orcid", "email",
        "institution", "position", "reviewer_availability", "reviewer_profile",
    ])
    messages.success(request, "Profile updated.")


def _handle_update_avatar(request):
    uploaded = request.FILES.get("avatar")
    if not uploaded:
        messages.error(request, "Choose an image to upload first.")
        return
    if not (uploaded.content_type or "").startswith("image/"):
        messages.error(request, "Please upload an image file (JPG, PNG or WEBP).")
        return

    object_path = storage.upload_avatar_file(uploaded, user_id=request.user.pk)
    if not object_path:
        messages.error(request, "Couldn't upload your photo right now. Please try again.")
        return

    request.user.profile_photo_path = object_path
    request.user.save(update_fields=["profile_photo_path"])
    messages.success(request, "Profile photo updated.")


def _handle_remove_avatar(request):
    user = request.user
    if user.profile_photo_path:
        storage.delete_object(user.profile_photo_path)
        user.profile_photo_path = ""
        user.save(update_fields=["profile_photo_path"])
    messages.success(request, "Profile photo removed.")


@login_required
@reviewer_required
def profile_expertise(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_profile":
            _handle_update_profile(request)
        elif action == "update_avatar":
            _handle_update_avatar(request)
        elif action == "remove_avatar":
            _handle_remove_avatar(request)
        else:
            messages.error(request, "That request could not be processed.")
        return redirect("reviewer_dashboard:profile_expertise")

    user = request.user
    profile = user.reviewer_profile or {}
    assignments = _assignments_for(user)
    review_stats = {
        "completed": assignments.filter(status=ReviewAssignment.Status.COMPLETED).count(),
        "active": assignments.exclude(status=ReviewAssignment.Status.COMPLETED).count(),
    }

    all_ever = ReviewAssignment.objects.filter(reviewer=user).count()
    declined = ReviewAssignment.objects.filter(
        reviewer=user, status=ReviewAssignment.Status.DECLINED
    ).count()
    review_stats["acceptance_rate"] = (
        round((all_ever - declined) / all_ever * 100) if all_ever else 100
    )

    chosen_expertise = user.reviewer_expertise_tags
    expertise_suggestions = [tag for tag in EXPERTISE_SUGGESTIONS if tag not in chosen_expertise]

    # How much of the profile a reviewer has actually filled in -- each
    # field below is worth an equal share, photo included, so "100%"
    # means the Secretariat has everything it could plausibly use to
    # match this reviewer to a protocol.
    completeness_fields = [
        user.profile_photo_path, user.phone, user.orcid,
        profile.get("reviewerInstitution") or user.institution,
        profile.get("reviewerPosition") or user.position,
        profile.get("reviewerDiscipline"), profile.get("reviewerYearsResearch"),
        chosen_expertise, profile.get("reviewerBio"),
    ]
    profile_completeness = round(100 * sum(1 for f in completeness_fields if f) / len(completeness_fields))

    return render(request, "dashboards/reviewer/profile-expertise.html", {
        "profile": profile,
        "review_stats": review_stats,
        "profile_completeness": profile_completeness,
        "max_concurrent_reviews": profile.get("maxConcurrentReviews") or "4",
        "preferred_categories": profile.get("preferredCategories") or [],
        "expertise_suggestions": expertise_suggestions,
    })


# ---------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------

def _handle_update_password(request):
    user = request.user
    current_password = request.POST.get("current_password", "")
    new_password = request.POST.get("new_password", "")
    confirm_password = request.POST.get("confirm_password", "")

    if not current_password or not user.check_password(current_password):
        messages.error(request, "Your current password is incorrect.")
        return
    if not new_password or new_password != confirm_password:
        messages.error(request, "New password and confirmation don't match.")
        return
    try:
        validate_password(new_password, user=user)
    except ValidationError as exc:
        for msg in exc.messages:
            messages.error(request, msg)
        return

    user.set_password(new_password)
    user.save(update_fields=["password"])
    # Rotates the session auth hash -- without this, changing your own
    # password would immediately log you out of the page you just used
    # to change it.
    update_session_auth_hash(request, user)
    messages.success(request, "Password updated.")


def _handle_update_security_prefs(request):
    user = request.user
    user.two_factor_app = bool(request.POST.get("two_factor_app"))
    user.two_factor_sms = bool(request.POST.get("two_factor_sms"))
    user.notify_new_signin = bool(request.POST.get("notify_new_signin"))

    profile = dict(user.reviewer_profile or {})
    profile["twoFactorEmail"] = bool(request.POST.get("two_factor_email"))
    profile["blockUnrecognisedCountries"] = bool(request.POST.get("block_unrecognised_countries"))
    user.reviewer_profile = profile

    user.save(update_fields=["two_factor_app", "two_factor_sms", "notify_new_signin", "reviewer_profile"])
    messages.success(request, "Security preferences updated.")


def _handle_revoke_session(request):
    session_key = request.POST.get("session_key", "")
    if session_key and session_key != request.session.session_key:
        session = Session.objects.filter(pk=session_key).first()
        if session and session.get_decoded().get("_auth_user_id") == str(request.user.pk):
            session.delete()
            messages.success(request, "That session has been signed out.")
            return
    messages.error(request, "That session could not be found.")


@login_required
@reviewer_required
def security(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_password":
            _handle_update_password(request)
        elif action == "update_security_prefs":
            _handle_update_security_prefs(request)
        elif action == "revoke_session":
            _handle_revoke_session(request)
        else:
            messages.error(request, "That request could not be processed.")
        return redirect("reviewer_dashboard:security")

    user = request.user
    profile = user.reviewer_profile or {}
    sessions = active_sessions_for(user, current_session_key=request.session.session_key)
    two_factor_email = profile.get("twoFactorEmail", True)

    # A simple, transparent score: password (always counted, since an
    # account can't exist without one) + one third each for having any
    # 2FA method on, keeping sign-in alerts on, and not running more
    # sessions than just this one device.
    score = 40
    if user.two_factor_app or user.two_factor_sms or two_factor_email:
        score += 30
    if user.notify_new_signin:
        score += 15
    if len(sessions) <= 1:
        score += 15
    if score >= 85:
        score_label = "Strong"
    elif score >= 55:
        score_label = "Good"
    else:
        score_label = "Needs Attention"

    return render(request, "dashboards/reviewer/security.html", {
        "sessions": sessions,
        "two_factor_email": two_factor_email,
        "security_score": score,
        "security_score_label": score_label,
        "block_unrecognised_countries": profile.get("blockUnrecognisedCountries", False),
    })


# ---------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------

def _handle_update_notification_prefs(request):
    user = request.user
    profile = dict(user.reviewer_profile or {})
    profile["notifyEmail"] = bool(request.POST.get("notify_email"))
    profile["notifySms"] = bool(request.POST.get("notify_sms"))
    profile["notifyWeeklyDigest"] = bool(request.POST.get("notify_weekly_digest"))
    profile["notifyCommitteeInvites"] = bool(request.POST.get("notify_committee_invites"))

    quiet_from = request.POST.get("quiet_hours_from", "").strip()
    quiet_to = request.POST.get("quiet_hours_to", "").strip()
    if quiet_from:
        profile["quietHoursFrom"] = quiet_from
    if quiet_to:
        profile["quietHoursTo"] = quiet_to

    user.reviewer_profile = profile
    user.save(update_fields=["reviewer_profile"])
    messages.success(request, "Notification preferences updated.")


@login_required
@reviewer_required
def notifications(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_notification_prefs":
            _handle_update_notification_prefs(request)
        else:
            messages.error(request, "That request could not be processed.")
        return redirect("reviewer_dashboard:notifications")

    profile = request.user.reviewer_profile or {}
    return render(request, "dashboards/reviewer/notifications.html", {
        "notify_email": profile.get("notifyEmail", True),
        "notify_sms": profile.get("notifySms", True),
        "notify_weekly_digest": profile.get("notifyWeeklyDigest", False),
        "notify_committee_invites": profile.get("notifyCommitteeInvites", True),
        "quiet_hours_from": profile.get("quietHoursFrom", "21:00"),
        "quiet_hours_to": profile.get("quietHoursTo", "07:00"),
    })
