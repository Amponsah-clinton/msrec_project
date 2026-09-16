from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from accounts.sessions import active_sessions_for
from applicant_dashboard import storage as application_storage
from notifications.models import Notification
from notifications.services import notify
from pages import documents_storage
from pages.models import CommitteeMeeting, MeetingDocument, PolicyDocument

from . import storage
from .models import ReviewAssignment
from .pdf import render_assessment_pdf

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
def coi_pending(request):
    """Every accepted-but-not-yet-completed assignment -- COI declaration
    happens inside the Reviewer Declaration section at the top of the
    Ethical Review Assessment Form itself (see _handle_submit_assessment),
    not as a separate step, so "pending" here means exactly the assignments
    that haven't reached that form's submit yet. Excludes New assignments
    on purpose -- there's nothing to declare a conflict against until the
    reviewer has actually accepted the assignment."""
    assignments = list(
        _assignments_for(request.user)
        .filter(status=ReviewAssignment.Status.ACCEPTED)
        .order_by("due_date")
    )
    for assignment in assignments:
        _annotate_due(assignment)

    return render(request, "dashboards/reviewer/coi-pending.html", {
        "assignments": assignments,
        "due_soon_count": sum(1 for a in assignments if a.due_date and 0 <= a.days_remaining <= 7),
        "no_due_count": sum(1 for a in assignments if not a.due_date),
    })


@login_required
@reviewer_required
def coi_previous(request):
    """Every assignment whose COI declaration was already made -- i.e.
    every Completed assignment, since coi_declared flips True at the same
    moment status flips to Completed. completed_at doubles as "when this
    declaration was made" -- there's no separate coi_declared_at column,
    because nothing today can complete the assessment without declaring
    COI in the same submit."""
    assignments = list(
        _assignments_for(request.user)
        .filter(status=ReviewAssignment.Status.COMPLETED, coi_declared=True)
        .order_by("-completed_at")
    )
    return render(request, "dashboards/reviewer/coi-previous.html", {
        "assignments": assignments,
        "conflict_count": sum(1 for a in assignments if a.coi_has_conflict),
        "clear_count": sum(1 for a in assignments if not a.coi_has_conflict),
    })


@login_required
@reviewer_required
def committee_meetings(request):
    """Every scheduled meeting that hasn't happened yet, soonest first --
    a straight, un-tabbed read of pages.models.CommitteeMeeting (managed
    from Django admin by the Secretariat)."""
    meetings = list(
        CommitteeMeeting.objects.filter(scheduled_at__gte=timezone.now()).order_by("scheduled_at")
    )
    return render(request, "dashboards/reviewer/committee-meetings.html", {
        "meetings": meetings,
    })


@login_required
@reviewer_required
def meeting_documents(request):
    """Every document attached to any meeting, most recent meeting first --
    the packet/agenda/minutes library, separate from the meetings list
    itself. Downloads are a direct public URL into the "ethics" bucket
    (pages/documents_storage.py) -- reviewer-only in practice because
    this page itself is gated, not because the link is secret."""
    documents = list(
        MeetingDocument.objects.select_related("meeting")
        .order_by("-meeting__scheduled_at", "-uploaded_at")
    )
    for doc in documents:
        doc.download_url = documents_storage.public_url(doc.file_path) if doc.file_path else None

    return render(request, "dashboards/reviewer/meeting-documents.html", {
        "documents": documents,
    })


def _policy_documents_page(request, *, category, page_title, page_subtitle):
    documents = list(PolicyDocument.objects.filter(category=category))
    for doc in documents:
        doc.download_url = documents_storage.public_url(doc.file_path) if doc.file_path else None

    return render(request, "dashboards/reviewer/policy-documents.html", {
        "documents": documents,
        "page_title": page_title,
        "page_subtitle": page_subtitle,
        "active_key": category,
    })


@login_required
@reviewer_required
def policy_sops(request):
    return _policy_documents_page(
        request, category=PolicyDocument.Category.SOP, page_title="MSREC SOPs",
        page_subtitle="Standard operating procedures that govern how MSREC reviews are run",
    )


@login_required
@reviewer_required
def policy_guidance(request):
    return _policy_documents_page(
        request, category=PolicyDocument.Category.GUIDANCE, page_title="Reviewer Guidance",
        page_subtitle="Practical guidance for conducting a thorough, consistent ethics review",
    )


@login_required
@reviewer_required
def policy_ethics(request):
    return _policy_documents_page(
        request, category=PolicyDocument.Category.ETHICS, page_title="Ethics Guidelines",
        page_subtitle="MSREC's foundational ethics standards and guidance documents",
    )


@login_required
@reviewer_required
def my_reviews_counts(request):
    """Polled by live-counts.js to keep the My Reviews tab badges current
    without a page reload -- e.g. the Secretariat assigns a new review
    while this page is already open."""
    return JsonResponse(_counts(_assignments_for(request.user)))


@login_required
@reviewer_required
def respond_to_assignment(request):
    """A reviewer's Accept/Decline on a brand-new assignment. Declining
    doesn't get silently absorbed anywhere: it flips the row to
    Status.DECLINED (which drops it out of _assignments_for and this
    reviewer's tabs for good), and that same status change is exactly
    what secretariat_dashboard._open_assignments()/_needs_assignment_qs()
    read to put the application back on the Assign Reviewer tab as
    needing a (new) reviewer -- plus an explicit in-app Notification so
    the Secretariat isn't left to infer "declined" from an application
    quietly reappearing in the unassigned list."""
    tab = request.POST.get("tab", "new") if request.method == "POST" else "new"
    redirect_url = f"{reverse('reviewer_dashboard:my_reviews')}?tab={tab}"
    if request.method != "POST":
        return redirect(redirect_url)

    action = request.POST.get("action")
    assignment_id = request.POST.get("assignment_id", "")
    if action not in {"accept", "decline"} or not assignment_id.isdigit():
        messages.error(request, "That request could not be processed.")
        return redirect(redirect_url)

    assignment = get_object_or_404(
        ReviewAssignment.objects.select_related("application", "reviewer"),
        pk=assignment_id, reviewer=request.user, status=ReviewAssignment.Status.NEW,
    )
    ref = assignment.application.reference_no or assignment.application.title

    if action == "accept":
        assignment.status = ReviewAssignment.Status.ACCEPTED
        assignment.accepted_at = timezone.now()
        assignment.save(update_fields=["status", "accepted_at"])
        messages.success(request, f"You've accepted the review for {ref}. It's now in your Accepted tab.")
    else:
        assignment.status = ReviewAssignment.Status.DECLINED
        assignment.declined_at = timezone.now()
        assignment.save(update_fields=["status", "declined_at"])
        notify(
            Notification.Audience.SECRETARIAT,
            f"{request.user.full_name} declined the review for {ref} -- it needs a new reviewer.",
            icon=Notification.Icon.WARN,
            link_url_name="secretariat_dashboard:reviewer_assignment",
        )
        messages.success(request, f"You've declined the review for {ref}. The Secretariat has been notified.")

    return redirect(redirect_url)


def _handle_submit_assessment(request, assignment):
    """Validate and save a reviewer's Ethical Review Assessment Form
    (Reviewer Declaration, the 10-row checklist, comments and
    recommendation) and close the assignment out as Completed. Mirrors
    the paper METASCHOLAR reviewer assessment form section-for-section."""
    coi_choice = request.POST.get("coi_choice", "")
    coi_details = request.POST.get("coi_details", "").strip()
    confidentiality_confirmed = bool(request.POST.get("confidentiality_confirmed"))
    recommendation = request.POST.get("recommendation", "")

    if coi_choice not in {"none", "conflict"}:
        messages.error(request, "Please declare whether you have a conflict of interest.")
        return False
    if coi_choice == "conflict" and not coi_details:
        messages.error(request, "Please describe the conflict of interest you declared.")
        return False
    if not confidentiality_confirmed:
        messages.error(request, "You must confirm confidentiality to submit this assessment.")
        return False

    checklist = {}
    for key, _label in ReviewAssignment.CHECKLIST_ITEMS:
        value = request.POST.get(f"checklist_{key}", "")
        if value not in ReviewAssignment.CHECKLIST_CHOICES:
            messages.error(request, "Please complete every row of the Ethical Review checklist.")
            return False
        checklist[key] = value

    if recommendation not in ReviewAssignment.Recommendation.values:
        messages.error(request, "Please select a recommendation.")
        return False

    assignment.coi_has_conflict = coi_choice == "conflict"
    assignment.coi_details = coi_details if assignment.coi_has_conflict else ""
    assignment.coi_declared = True
    assignment.confidentiality_confirmed = True
    assignment.checklist = checklist
    assignment.key_concerns = request.POST.get("key_concerns", "").strip()
    assignment.documents_comment = request.POST.get("documents_comment", "").strip()
    assignment.recommendation = recommendation
    assignment.recommendation_reason = request.POST.get("recommendation_reason", "").strip()
    assignment.review_notes = request.POST.get("review_notes", "").strip()
    assignment.status = ReviewAssignment.Status.COMPLETED
    assignment.completed_at = timezone.now()
    assignment.save(update_fields=[
        "coi_has_conflict", "coi_details", "coi_declared", "confidentiality_confirmed",
        "checklist", "key_concerns", "documents_comment", "recommendation",
        "recommendation_reason", "review_notes", "status", "completed_at",
    ])

    ref = assignment.application.reference_no or assignment.application.title
    notify(
        Notification.Audience.SECRETARIAT,
        f"{request.user.full_name} submitted their assessment for {ref}: "
        f"{assignment.get_recommendation_display()}.",
        icon=Notification.Icon.SUCCESS,
        link_url_name="secretariat_dashboard:reviewer_assignment",
    )
    messages.success(request, f"Your assessment for {ref} has been submitted. Thank you.")
    return True


@login_required
@reviewer_required
def review_application(request, assignment_id):
    """Ethical Review Assessment Form for a reviewer who has accepted the
    assignment: the application's own text (Research Information, PI
    details, documents, every submitted answer) for reference, plus the
    Reviewer Declaration / checklist / recommendation form itself on
    POST. A still-New or already-Declined assignment 404s here, same as
    pk-scoping to `reviewer=request.user` keeps one reviewer from opening
    another's assignment by guessing an id. Once Completed, the same
    template renders the submitted answers read-only instead of the form."""
    assignment = get_object_or_404(
        ReviewAssignment.objects.select_related("application", "application__applicant"),
        pk=assignment_id, reviewer=request.user,
        status__in=[ReviewAssignment.Status.ACCEPTED, ReviewAssignment.Status.COMPLETED],
    )

    if request.method == "POST":
        if assignment.status != ReviewAssignment.Status.ACCEPTED:
            messages.error(request, "This assessment has already been submitted.")
        elif _handle_submit_assessment(request, assignment):
            return redirect("reviewer_dashboard:review_application", assignment_id=assignment.pk)

    application = assignment.application
    documents = [
        {**doc, "url": application_storage.public_url(doc.get("path"))}
        for doc in (application.documents or [])
    ]
    return render(request, "dashboards/reviewer/review-application.html", {
        "assignment": assignment,
        "application": application,
        "documents": documents,
        "checklist_items": ReviewAssignment.CHECKLIST_ITEMS,
        "recommendation_choices": ReviewAssignment.Recommendation.choices,
        # Sticky re-population after a failed validation -- empty (falsy)
        # on GET and once the assessment is Completed, so template lookups
        # like `posted.checklist_rationale` harmlessly fall through to
        # `assignment.checklist.rationale` via the `default` filter.
        "posted": request.POST if request.method == "POST" else None,
    })


@login_required
@reviewer_required
def review_application_pdf(request, assignment_id):
    """Downloadable PDF of a submitted Ethical Review Assessment Form --
    only exists once there's something to export, so this 404s on
    anything but a Completed assignment (same pk + reviewer scoping as
    review_application itself, for the same reason)."""
    assignment = get_object_or_404(
        ReviewAssignment.objects.select_related("application", "application__applicant", "reviewer"),
        pk=assignment_id, reviewer=request.user, status=ReviewAssignment.Status.COMPLETED,
    )
    pdf_bytes = render_assessment_pdf(assignment)
    ref = assignment.application.reference_no or f"assignment-{assignment.pk}"
    filename = f"MSREC Ethical Review Assessment - {ref}.pdf".replace("/", "-")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


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
