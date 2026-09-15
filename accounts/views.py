import uuid

from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from notifications.emails import send_branded_email

from . import storage
from .forms import LoginForm, SignupForm
from .models import User

# Extra, role-specific fields collected on the signup form. These aren't
# validated as strict Django fields (see forms.SignupForm's docstring) --
# they're saved as-is into the matching *_profile JSONField for a human
# reviewer to read, so a stray missing/extra key never breaks signup.
APPLICANT_PROFILE_FIELDS = [
    "applicantCategory", "primaryResearchArea", "academicProgramme", "degreeLevel",
    "supervisorName", "supervisorInstitution", "supervisorEmail",
]
REVIEWER_PROFILE_FIELDS = [
    "independentReviewer", "reviewerPosition", "reviewerInstitution", "reviewerDiscipline",
    "reviewerYearsProfessional", "reviewerYearsResearch", "reviewerPriorExperience",
    "reviewerCommitteeExperience", "reviewerExpertise", "reviewerResearchAreas",
    "reviewerTraining", "reviewerOrcid", "reviewerRegistration", "reviewerBio",
]
COMMITTEE_PROFILE_FIELDS = [
    "committeePosition", "committeeInstitution", "committeeYears", "committeeEthicsExperience",
    "committeeEthicsDetails", "committeeBackground", "committeeTraining", "committeeOrcid",
    "committeeRegistration", "committeeReference", "committeeBio",
]


def _collect_profile(post, fields, multi_fields=()):
    data = {}
    for key in fields:
        if key in multi_fields:
            values = post.getlist(key)
            if values:
                data[key] = values
        else:
            value = post.get(key, "").strip()
            if value:
                data[key] = value
    return data


def _send_role_pending_email(user):
    """Sent once, right at signup, to whoever ticked Reviewer and/or
    Committee Member -- so "nothing happened, I was just dropped on the
    Applicant dashboard" never reads as the system having lost their
    request. The one-time flash message next to it only survives that
    first page load; this is the durable record admin_dashboard's later
    approval email (_send_role_approved_email) follows up on."""
    role_labels = [User.Role(role).label for role in user.requested_roles]
    roles_text = " and ".join(role_labels)
    if user.wants_applicant:
        access_note = (
            "You already have full Applicant access, so you can start (or continue) an application "
            f"right away. We'll email you as soon as your {roles_text} request has been decided."
        )
    else:
        # Didn't tick Applicant -- don't claim access they never asked
        # for. See accounts.models.User.awaiting_role_only.
        access_note = (
            f"You don't have applicant access, since you didn't request it — this account exists "
            f"solely for your {roles_text} request. We'll email you as soon as it's been decided."
        )
    send_branded_email(
        subject=f"MSREC — your {roles_text} request has been received",
        to=user.email,
        heading="We've received your request",
        paragraphs=[
            f"Hi {user.full_name},",
            f"Thanks for signing up to MSREC. Your request to join as "
            f"{roles_text} has been received — it's now awaiting review by an MSREC admin.",
            access_note,
        ],
        preheader=f"Your {roles_text} request is pending admin review.",
    )


def signup(request):
    if request.user.is_authenticated:
        return redirect(request.user.dashboard_url_name())

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            roles = cd["role"]

            user = User(
                email=cd["email"],
                first_name=cd["firstName"],
                middle_name=cd.get("middleName", ""),
                last_name=cd["lastName"],
                title=cd.get("title", ""),
                phone=cd["phone"],
                country_residence=cd["countryResidence"],
                highest_qualification=cd["highestQualification"],
                no_institution=cd.get("noInstitution", False),
                institution=cd.get("institution", ""),
                department=cd.get("department", ""),
                position=cd.get("position", ""),
                institution_country=cd.get("institutionCountry", ""),
                institution_address=cd.get("institutionAddress", ""),
                profile_url=cd.get("profileUrl", ""),
                role=User.Role.APPLICANT,
                wants_applicant="applicant" in roles,
            )

            # Note: primaryResearchArea / reviewerExpertise / reviewerResearchAreas are
            # tag-inputs (see signup.js initTagInput) -- each posts as ONE hidden field
            # holding a comma-joined string, not repeated same-name inputs, so they are
            # NOT multi_fields here. committeeExpertiseCategory is real checkboxes
            # (repeated name="committeeExpertiseCategory" per option) and does need getlist.
            if "reviewer" in roles:
                user.wants_reviewer = True
                user.reviewer_status = User.RequestStatus.PENDING
                user.reviewer_profile = _collect_profile(request.POST, REVIEWER_PROFILE_FIELDS)
            if "committee" in roles:
                user.wants_committee = True
                user.committee_status = User.RequestStatus.PENDING
                user.committee_profile = _collect_profile(
                    request.POST, COMMITTEE_PROFILE_FIELDS,
                    multi_fields=("committeeExpertiseCategory",),
                )
            if "applicant" in roles:
                user.applicant_profile = _collect_profile(request.POST, APPLICANT_PROFILE_FIELDS)

            # Signup documents (profile photo + role CVs) -> Supabase Storage
            # "signup" bucket, grouped under one folder per submission. A
            # Storage outage must never block account creation, so a failed
            # upload just means that particular field stays unset (see
            # accounts/storage.py) -- it doesn't fail the signup.
            upload_folder = uuid.uuid4().hex
            photo_path = storage.upload_signup_file(
                request.FILES.get("profilePhoto"), folder=upload_folder, field_name="profilePhoto"
            )
            if photo_path:
                user.profile_photo_path = photo_path

            if "applicant" in roles:
                cv_path = storage.upload_signup_file(
                    request.FILES.get("applicantCv"), folder=upload_folder, field_name="applicantCv"
                )
                if cv_path:
                    user.applicant_profile["cv_path"] = cv_path
            if "reviewer" in roles:
                cv_path = storage.upload_signup_file(
                    request.FILES.get("reviewerCv"), folder=upload_folder, field_name="reviewerCv"
                )
                if cv_path:
                    user.reviewer_profile["cv_path"] = cv_path
            if "committee" in roles:
                cv_path = storage.upload_signup_file(
                    request.FILES.get("committeeCv"), folder=upload_folder, field_name="committeeCv"
                )
                if cv_path:
                    user.committee_profile["cv_path"] = cv_path

            user.set_password(cd["password"])
            user.save()

            auth_login(request, user)
            request.session["ua"] = request.META.get("HTTP_USER_AGENT", "")[:300]
            request.session["login_ip"] = request.META.get("REMOTE_ADDR", "")
            request.session["login_at"] = timezone.now().isoformat()

            if user.has_pending_requests:
                _send_role_pending_email(user)
                role_labels = [User.Role(role).label for role in user.requested_roles]
                roles_text = " and ".join(role_labels)
                if user.wants_applicant:
                    messages.success(
                        request,
                        f"Welcome to MSREC! Your account is ready. Your {roles_text} request is "
                        "pending admin approval — we've emailed you a confirmation, and we'll notify "
                        "you again as soon as it's reviewed.",
                    )
                else:
                    messages.success(
                        request,
                        f"Welcome to MSREC! Your {roles_text} request has been submitted and is pending "
                        "admin approval — we've emailed you a confirmation, and we'll notify you again "
                        "as soon as it's reviewed.",
                    )
            else:
                messages.success(request, "Welcome to MSREC! Your account has been created.")
            return redirect(user.dashboard_url_name())

        for error in form.non_field_errors():
            messages.error(request, error)
        for field, errors in form.errors.items():
            if field == "__all__":
                continue
            label = form.fields[field].label or field
            for error in errors:
                messages.error(request, f"{label}: {error}")
        return render(request, "pages/signup.html", {"form": form}, status=400)

    form = SignupForm()
    return render(request, "pages/signup.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect(request.user.dashboard_url_name())

    if request.method == "POST":
        form = LoginForm(request.POST, request=request)
        if form.is_valid():
            user = form.get_user()
            auth_login(request, user)
            # Stashed on the session itself (not a DB row) -- Profile &
            # Security's Active Sessions panel (accounts/sessions.py) reads
            # these back to describe/list every session belonging to this
            # user without needing a dedicated login-history table.
            request.session["ua"] = request.META.get("HTTP_USER_AGENT", "")[:300]
            request.session["login_ip"] = request.META.get("REMOTE_ADDR", "")
            request.session["login_at"] = timezone.now().isoformat()
            messages.success(request, f"Welcome back, {user.first_name}.")
            next_url = request.POST.get("next") or request.GET.get("next")
            return redirect(next_url or user.dashboard_url_name())
        for error in form.non_field_errors():
            messages.error(request, error)
        return render(request, "pages/login.html", {"form": form}, status=400)

    form = LoginForm(request=request)
    return render(request, "pages/login.html", {"form": form})


def logout_view(request):
    auth_logout(request)
    messages.success(request, "You've been signed out.")
    return redirect(reverse("pages:login"))


@login_required
def role_status(request):
    """Landing page for an account that requested Reviewer and/or
    Committee only (no Applicant) and hasn't been approved into either
    yet -- see User.awaiting_role_only / dashboard_url_name(). Redirects
    away the moment there's a real dashboard to send them to instead
    (approved, or they've since gained Applicant access some other way),
    so this page is never stale once a decision lands."""
    user = request.user
    if not user.awaiting_role_only:
        return redirect(user.dashboard_url_name())
    return render(request, "pages/role-status.html")
