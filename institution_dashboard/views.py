import logging

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import User
from applicant_dashboard.models import Application

from .models import InstitutionSecretary

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------

def is_institution_secretary(user):
    # The `role` column is the permission here -- an Institutional Secretary
    # account is only ever created with role=inst_secretary (see
    # admin_dashboard.views._handle_create_institution_secretary), so there's
    # no separate approval status to consult (unlike reviewer/committee).
    return user.is_authenticated and user.role == User.Role.INSTITUTION_SECRETARY


institution_secretary_required = user_passes_test(
    is_institution_secretary, login_url="pages:login"
)


# ---------------------------------------------------------------------
# Institution matching helpers
# ---------------------------------------------------------------------

def _norm(value):
    return (value or "").strip().lower()


def _member_institution(user):
    """The institution to match a member on. Reviewers and Committee members
    capture their institution in their role profile at signup
    (reviewerInstitution / committeeInstitution); everyone else uses the
    shared User.institution field. Falls back across all three so a match
    is found wherever the value actually landed."""
    candidates = [
        user.institution,
        (user.reviewer_profile or {}).get("reviewerInstitution"),
        (user.committee_profile or {}).get("committeeInstitution"),
    ]
    return [c for c in candidates if (c or "").strip()]


def _matches_institution(user, institution):
    target = _norm(institution)
    return any(_norm(c) == target for c in _member_institution(user))


# ---------------------------------------------------------------------
# Activation (public: set password from the emailed invite link)
# ---------------------------------------------------------------------

def activate(request, token):
    """Public landing page for the link in an Institutional Secretary invite
    email -- no login required (the account exists but has no usable
    password yet). Let the invitee set a password; doing so activates the
    account, signs them in and drops them on their dashboard."""
    secretary = (
        InstitutionSecretary.objects.filter(invite_token=token)
        .select_related("user").first()
    )
    if secretary is None:
        return render(request, "pages/institution_activate.html", {"valid": False}, status=404)

    user = secretary.user

    if request.method == "POST":
        password = request.POST.get("new_password", "")
        confirm = request.POST.get("confirm_password", "")
        errors = False
        if password != confirm:
            messages.error(request, "Passwords do not match.")
            errors = True
        if password:
            try:
                validate_password(password, user=user)
            except DjangoValidationError as exc:
                for message in exc.messages:
                    messages.error(request, message)
                errors = True
        else:
            messages.error(request, "Choose a password.")
            errors = True

        if errors:
            return render(request, "pages/institution_activate.html", {
                "valid": True, "secretary": secretary, "user": user,
            }, status=400)

        user.set_password(password)
        user.is_active = True
        user.save(update_fields=["password", "is_active"])

        # Burn the token so the link can't be reused, and record activation.
        secretary.invite_token = None
        secretary.activated_at = timezone.now()
        secretary.save(update_fields=["invite_token", "activated_at", "updated_at"])

        auth_login(request, user)
        request.session["ua"] = request.META.get("HTTP_USER_AGENT", "")[:300]
        request.session["login_ip"] = request.META.get("REMOTE_ADDR", "")
        request.session["login_at"] = timezone.now().isoformat()
        messages.success(request, "Your password is set — welcome to MSREC.")
        return redirect("institution_dashboard:home")

    # Already activated and the link somehow still points here: send them to login.
    if secretary.is_activated:
        return render(request, "pages/institution_activate.html", {
            "valid": True, "secretary": secretary, "user": user, "already_active": True,
        })

    return render(request, "pages/institution_activate.html", {
        "valid": True, "secretary": secretary, "user": user,
    })


# ---------------------------------------------------------------------
# Dashboard pages
# ---------------------------------------------------------------------

def _institution(request):
    return (request.user.institution or "").strip()


def _school_applications(institution):
    """Every non-draft application whose applicant belongs to `institution`,
    newest first. Matched on the applicant's own institution (what the
    Institution dropdown saved at signup)."""
    return list(
        Application.objects.filter(applicant__institution__iexact=institution)
        .exclude(status=Application.Status.DRAFT)
        .select_related("applicant")
        .order_by("-submitted_at", "-id")
    )


@login_required
@institution_secretary_required
def home(request):
    institution = _institution(request)
    apps = _school_applications(institution)
    approved = [a for a in apps if a.status == Application.Status.APPROVED]

    committee = [
        u for u in User.objects.filter(committee_status=User.RequestStatus.APPROVED)
        if _matches_institution(u, institution)
    ]
    reviewers = [
        u for u in User.objects.filter(reviewer_status=User.RequestStatus.APPROVED)
        if _matches_institution(u, institution)
    ]

    return render(request, "dashboards/institution/home.html", {
        "institution": institution,
        "application_count": len(apps),
        "approved_count": len(approved),
        "committee_count": len(committee),
        "reviewer_count": len(reviewers),
        "recent_applications": apps[:6],
    })


@login_required
@institution_secretary_required
def applications(request):
    institution = _institution(request)
    apps = _school_applications(institution)
    return render(request, "dashboards/institution/applications.html", {
        "institution": institution,
        "applications": apps,
        "total": len(apps),
    })


@login_required
@institution_secretary_required
def committee_members(request):
    institution = _institution(request)
    members = [
        u for u in User.objects.filter(committee_status=User.RequestStatus.APPROVED)
        .order_by("first_name", "last_name")
        if _matches_institution(u, institution)
    ]
    return render(request, "dashboards/institution/committee-members.html", {
        "institution": institution,
        "members": members,
        "total": len(members),
    })


@login_required
@institution_secretary_required
def reviewers(request):
    institution = _institution(request)
    members = [
        u for u in User.objects.filter(reviewer_status=User.RequestStatus.APPROVED)
        .order_by("first_name", "last_name")
        if _matches_institution(u, institution)
    ]
    return render(request, "dashboards/institution/reviewers.html", {
        "institution": institution,
        "reviewers": members,
        "total": len(members),
    })


@login_required
@institution_secretary_required
def other_institutions(request):
    """Every other institution's applications, grouped by institution -- so a
    secretary can see wider activity across the platform. Their own school is
    excluded (that's the Applications page), as are applicants with no
    institution recorded."""
    mine = _norm(_institution(request))
    rows = (
        Application.objects.exclude(status=Application.Status.DRAFT)
        .select_related("applicant")
        .order_by("-submitted_at", "-id")
    )
    groups = {}
    for app in rows:
        inst = (app.applicant.institution or "").strip()
        if not inst or _norm(inst) == mine:
            continue
        groups.setdefault(inst, []).append(app)

    grouped = [
        {"institution": name, "applications": apps, "count": len(apps)}
        for name, apps in sorted(groups.items(), key=lambda kv: kv[0].lower())
    ]
    return render(request, "dashboards/institution/other-institutions.html", {
        "my_institution": _institution(request),
        "groups": grouped,
        "institution_count": len(grouped),
        "application_count": sum(g["count"] for g in grouped),
    })
