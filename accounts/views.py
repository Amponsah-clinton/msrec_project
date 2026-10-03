import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from notifications.emails import send_branded_email, send_password_changed_email
from notifications.models import Notification
from notifications.services import notify

from . import storage
from .forms import LoginForm, SignupForm
from .models import PasswordResetCode, User

logger = logging.getLogger(__name__)

# Session key holding the email address a Forgot Password flow is in
# progress for -- set by forgot_password(), read (and cleared) by
# reset_password(). Keeping it server-side in the session rather than in
# the URL/a hidden form field means the email is never something a
# person could edit client-side to target a different account.
PASSWORD_RESET_SESSION_KEY = "pwreset_email"
PASSWORD_RESET_ATTEMPTS_KEY = "pwreset_attempts"

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
    "reviewerYearsProfessional", "reviewerYearsResearch",
    "reviewerExpertise", "reviewerResearchAreas", "reviewerBio",
]
COMMITTEE_PROFILE_FIELDS = [
    "committeePosition", "committeeInstitution", "committeeYears",
    "committeeBackground", "committeeReference", "committeeBio",
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


def _send_welcome_email(request, user):
    """Sent to every new account right after signup, regardless of which
    role(s) were requested -- the one guaranteed "you're in" email. Kept
    separate from _send_role_pending_email below, which only fires for a
    Reviewer/Committee request and is about that request's status, not
    the account itself -- both go out on the same signup when relevant,
    this one first."""
    login_url = settings.SITE_URL.rstrip("/") + reverse("pages:login")
    return send_branded_email(
        subject="Welcome to MSREC",
        to=user.email,
        heading=f"Welcome to MSREC, {user.first_name}",
        paragraphs=[
            f"Hi {user.full_name},",
            "Your MSREC account has been created. MSREC (Metascholar Research Ethics Committee) "
            "provides structured ethical review, post-approval oversight and verifiable decisions "
            "for researchers and institutions.",
            "You can log in any time using the email address and password you just set.",
        ],
        cta_text="Log in to MSREC",
        cta_url=login_url,
        preheader="Your MSREC account is ready.",
    )


def _notify_staff_of_role_request(user, roles_text):
    """Puts a new Reviewer/Committee application in the Admin and
    Secretariat notification bells (both can approve it), linking straight
    to the page where it's decided. Never blocks sign-up."""
    message = f"New {roles_text} application from {user.full_name} — awaiting approval."[:255]
    for audience, url_name in (
        (Notification.Audience.ADMIN, "admin_dashboard:accounts"),
        (Notification.Audience.SECRETARIAT, "secretariat_dashboard:users_access"),
    ):
        try:
            notify(audience, message, icon=Notification.Icon.WARN, link_url_name=url_name)
        except Exception:
            pass


def _secretariat_notification_emails():
    """Who to email about a new Reviewer/Committee application: every active
    Secretariat account, plus the configured Secretariat routing address
    from Site Settings (so an install with no Secretariat account yet still
    reaches a monitored inbox). De-duplicated, lower-cased."""
    emails = set()
    for addr in User.objects.filter(
        role=User.Role.SECRETARIAT, is_active=True
    ).values_list("email", flat=True):
        if addr:
            emails.add(addr.strip().lower())
    try:
        from pages.models import SiteSettings
        site = SiteSettings.get_solo()
        if site.contact_secretariat_email:
            emails.add(site.contact_secretariat_email.strip().lower())
    except Exception:
        logger.exception("Could not read Secretariat routing email from Site Settings")
    return sorted(emails)


def _email_secretariat_of_role_request(request, user, roles_text):
    """Emails the Secretariat the moment someone signs up requesting a
    Reviewer and/or Committee role, so a pending application isn't waiting
    only behind the in-app notification bell. Best-effort: a mail problem
    never blocks sign-up."""
    recipients = _secretariat_notification_emails()
    if not recipients:
        logger.warning("No Secretariat recipients for role-request email (%s)", user.email)
        return False

    review_url = settings.SITE_URL.rstrip("/") + reverse("secretariat_dashboard:users_access")
    detail_bits = [f"Email: {user.email}"]
    if user.phone:
        detail_bits.append(f"Phone: {user.phone}")
    if user.institution:
        detail_bits.append(f"Institution: {user.institution}")

    try:
        return send_branded_email(
            subject=f"New {roles_text} application — {user.full_name}",
            to=recipients,
            heading="New membership application",
            paragraphs=[
                "A new account has signed up and requested a role that needs Secretariat approval.",
                f"{user.full_name} has applied to join MSREC as {roles_text}.",
                " · ".join(detail_bits),
                "Review their details (including the CV they uploaded) and approve or decline the "
                "request from Users & Access.",
            ],
            cta_text="Review the application",
            cta_url=review_url,
            preheader=f"{user.full_name} applied to join MSREC as {roles_text}.",
        )
    except Exception:
        logger.exception("Failed to send Secretariat role-request email for %s", user.email)
        return False


def _send_role_pending_email(request, user):
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
            f"right away while your {roles_text} request is being reviewed."
        )
    else:
        access_note = (
            f"You don't have applicant access, since you didn't request it -- this account exists "
            f"solely for your {roles_text} request."
        )
    login_url = settings.SITE_URL.rstrip("/") + reverse("pages:login")
    logger.info("Sending role-pending email to %s for %s", user.email, roles_text)
    try:
        sent = send_branded_email(
            subject=f"MSREC -- your {roles_text} request is under review",
            to=user.email,
            heading="Your request is under review",
            paragraphs=[
                f"Hi {user.full_name},",
                f"Thank you for signing up to MSREC. Your request to join as {roles_text} has been "
                f"received and is now being vetted by the MSREC Secretariat.",
                "Your application will be carefully reviewed. Once approved, we will send you another "
                "email with your MSREC Ethics ID, Membership Certificate and login details.",
                access_note,
            ],
            cta_text="Log in to MSREC",
            cta_url=login_url,
            preheader=f"Your {roles_text} request is being vetted by the MSREC Secretariat.",
        )
        logger.info("Role-pending email to %s: sent=%s", user.email, sent)
        return sent
    except Exception:
        logger.exception("Failed to send role-pending email to %s", user.email)
        return False


def _send_reset_code(user):
    """Issues a fresh PasswordResetCode and emails it. Returns (code_row,
    emailed) -- callers (forgot_password / the resend action in
    reset_password) use the code row to reset the session's attempt
    counter, and `emailed` to tell the user the truth about whether the
    code actually went out instead of assuming delivery succeeded."""
    code_obj = PasswordResetCode.issue_for(user)
    minutes = int(PasswordResetCode.TTL.total_seconds() // 60)
    emailed = send_branded_email(
        subject="MSREC — your password reset code",
        to=user.email,
        heading="Reset your password",
        paragraphs=[
            f"Hi {user.first_name},",
            f"Use the code below to reset your MSREC account password. "
            f"It expires in {minutes} minutes and can only be used once.",
            "If you didn't request this, you can safely ignore this email — your password won't change.",
        ],
        quote_label="Your reset code",
        quote_text=code_obj.code,
        preheader="Your MSREC password reset code",
    )
    return code_obj, emailed


def forgot_password(request):
    if request.user.is_authenticated:
        return redirect(request.user.dashboard_url_name())

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        if not email:
            messages.error(request, "Enter your email address.")
            return render(request, "pages/forgot-password.html", {"email": email}, status=400)

        user = User.objects.filter(email=email).first()
        request.session[PASSWORD_RESET_SESSION_KEY] = email

        if user is not None:
            last_code = user.password_reset_codes.first()
            if last_code and last_code.is_valid and timezone.now() - last_code.created_at < PasswordResetCode.RESEND_COOLDOWN:
                # They still have a live, unexpired code from moments ago --
                # send them straight to enter it rather than bouncing them
                # with an error just because we won't issue a second one yet.
                messages.success(request, f"You already have a code on its way to {email} — enter it below.")
                return redirect("pages:reset_password")
            request.session[PASSWORD_RESET_ATTEMPTS_KEY] = 0
            _, emailed = _send_reset_code(user)
            if not emailed:
                messages.error(
                    request,
                    "We found your account, but couldn't send the reset code email right now. "
                    "Please try again in a moment or contact the Secretariat for help.",
                )
                return redirect("pages:reset_password")
        else:
            request.session[PASSWORD_RESET_ATTEMPTS_KEY] = 0

        # Same message whether or not the account exists -- doesn't
        # confirm/deny a given email is registered with MSREC.
        messages.success(request, f"If an account exists for {email}, a 6-digit reset code has been sent.")
        return redirect("pages:reset_password")

    return render(request, "pages/forgot-password.html")


def reset_password(request):
    email = request.session.get(PASSWORD_RESET_SESSION_KEY, "")
    if not email:
        messages.error(request, "Start by entering the email address on your account.")
        return redirect("pages:forgot_password")

    if request.method == "POST":
        action = request.POST.get("action", "reset")
        user = User.objects.filter(email=email).first()

        if action == "resend":
            emailed = True
            if user is not None:
                last_code = user.password_reset_codes.first()
                if last_code and last_code.is_valid and timezone.now() - last_code.created_at < PasswordResetCode.RESEND_COOLDOWN:
                    messages.error(request, "Please wait a minute before requesting another code.")
                    return redirect("pages:reset_password")
                _, emailed = _send_reset_code(user)
            request.session[PASSWORD_RESET_ATTEMPTS_KEY] = 0
            if emailed:
                messages.success(request, f"A new code has been sent to {email}.")
            else:
                messages.error(
                    request,
                    "We couldn't send a new code right now. Please try again in a moment or "
                    "contact the Secretariat for help.",
                )
            return redirect("pages:reset_password")

        attempts = request.session.get(PASSWORD_RESET_ATTEMPTS_KEY, 0)
        if attempts >= PasswordResetCode.MAX_ATTEMPTS:
            messages.error(request, "Too many incorrect attempts. Request a new code to keep trying.")
            return render(request, "pages/reset-password.html", {"email": email, "locked": True}, status=429)

        code = request.POST.get("code", "").strip()
        new_password = request.POST.get("new_password", "")
        confirm_password = request.POST.get("confirm_password", "")

        code_obj = None
        if user is not None and code:
            code_obj = user.password_reset_codes.filter(code=code, used_at__isnull=True).first()

        if user is None or code_obj is None or not code_obj.is_valid:
            request.session[PASSWORD_RESET_ATTEMPTS_KEY] = attempts + 1
            messages.error(request, "That code is incorrect or has expired.")
            return render(request, "pages/reset-password.html", {"email": email}, status=400)

        if not new_password or new_password != confirm_password:
            messages.error(request, "New password and confirmation don't match.")
            return render(request, "pages/reset-password.html", {"email": email}, status=400)

        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return render(request, "pages/reset-password.html", {"email": email}, status=400)

        user.set_password(new_password)
        user.save(update_fields=["password"])
        # This code, and any other still-open code for this user, are
        # spent the moment one of them succeeds -- an old code from an
        # earlier request must never remain usable after a reset.
        user.password_reset_codes.filter(used_at__isnull=True).update(used_at=timezone.now())

        send_password_changed_email(user, request)

        del request.session[PASSWORD_RESET_SESSION_KEY]
        request.session.pop(PASSWORD_RESET_ATTEMPTS_KEY, None)

        messages.success(request, "Your password has been reset. Please log in with your new password.")
        return redirect("pages:login")

    return render(request, "pages/reset-password.html", {"email": email})


# The three Institution dropdowns on the sign-up form (Applicant, Reviewer,
# Committee) each post a select value plus a companion free-text field used
# only when "Other" is picked. _resolve_institution_choices folds each pair
# into the single canonical field name the form/profile collection already
# reads, so an institution not in the admin-managed list still comes through.
INSTITUTION_OTHER_VALUE = "__other__"
INSTITUTION_FIELD_PAIRS = [
    ("institution", "institutionOther"),
    ("reviewerInstitution", "reviewerInstitutionOther"),
    ("committeeInstitution", "committeeInstitutionOther"),
]


def _resolve_institution_choices(post):
    """Returns a mutable copy of `post` where any Institution dropdown set to
    "Other" is replaced by the typed-in companion value."""
    data = post.copy()
    for select_name, other_name in INSTITUTION_FIELD_PAIRS:
        if data.get(select_name, "").strip() == INSTITUTION_OTHER_VALUE:
            data[select_name] = data.get(other_name, "").strip()
    return data


def _active_institutions():
    from pages.models import Institution

    return list(Institution.objects.filter(is_active=True))


def _register_institutions(names):
    """Any institution a new member typed into an "Other" box is added to the
    admin-managed list here, so it's offered in the dropdown to the next
    person signing up. Matching is case-insensitive, so a differently-cased
    duplicate is never created, and an institution picked straight from the
    existing list is simply left as-is. Each insert is isolated and best
    effort -- it must never block (or roll back) account creation."""
    from django.db import transaction

    from pages.models import Institution

    for raw in names:
        name = (raw or "").strip()
        if not name:
            continue
        try:
            with transaction.atomic():
                if not Institution.objects.filter(name__iexact=name).exists():
                    Institution.objects.create(name=name[:200], is_active=True)
        except Exception:
            # A race on the unique name, or any storage hiccup -- the member's
            # own record already holds the institution, so this is non-fatal.
            logger.exception("Could not auto-add institution %r to the list", name)


def signup(request):
    if request.user.is_authenticated:
        return redirect(request.user.dashboard_url_name())

    if request.method == "POST":
        post = _resolve_institution_choices(request.POST)
        form = SignupForm(post)
        if form.is_valid():
            cd = form.cleaned_data
            roles = cd["role"]

            # Reviewers and Committee members are published on the public
            # Board & Committee page the moment they're approved (with this
            # very photo -- see pages.committee_services), so a profile photo
            # is mandatory for them. Applicant-only signups stay optional.
            profile_photo = request.FILES.get("profilePhoto")
            if ("reviewer" in roles or "committee" in roles) and not profile_photo:
                messages.error(
                    request,
                    "A profile photo is required for Reviewer and Committee Member registration.",
                )
                return render(
                    request, "pages/signup.html",
                    {"form": form, "institutions": _active_institutions()}, status=400,
                )

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
                user.reviewer_profile = _collect_profile(post, REVIEWER_PROFILE_FIELDS)
            if "committee" in roles:
                user.wants_committee = True
                user.committee_status = User.RequestStatus.PENDING
                user.committee_profile = _collect_profile(
                    post, COMMITTEE_PROFILE_FIELDS,
                    multi_fields=("committeeExpertiseCategory",),
                )
            if "applicant" in roles:
                user.applicant_profile = _collect_profile(post, APPLICANT_PROFILE_FIELDS)

            # Signup documents (profile photo + role CVs) -> Supabase Storage
            # "signup" bucket, grouped under one folder per submission. A
            # Storage outage must never block account creation, so a failed
            # upload just means that particular field stays unset (see
            # accounts/storage.py) -- it doesn't fail the signup.
            upload_folder = uuid.uuid4().hex
            photo_path = storage.upload_signup_file(
                profile_photo, folder=upload_folder, field_name="profilePhoto"
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

            # Fold any institution(s) typed into an "Other" box into the
            # admin-managed list so the next applicant can pick them. Only
            # the sections for the roles actually requested are considered;
            # a value picked straight from the list is a no-op.
            institution_names = []
            if "applicant" in roles:
                institution_names.append(cd.get("institution", ""))
            if "reviewer" in roles:
                institution_names.append(post.get("reviewerInstitution", ""))
            if "committee" in roles:
                institution_names.append(post.get("committeeInstitution", ""))
            _register_institutions(institution_names)

            try:
                _send_welcome_email(request, user)
            except Exception:
                logger.exception("Welcome email failed for %s", user.email)

            auth_login(request, user)
            request.session["ua"] = request.META.get("HTTP_USER_AGENT", "")[:300]
            request.session["login_ip"] = request.META.get("REMOTE_ADDR", "")
            request.session["login_at"] = timezone.now().isoformat()

            if user.has_pending_requests:
                emailed = _send_role_pending_email(request, user)
                role_labels = [User.Role(role).label for role in user.requested_roles]
                roles_text = " and ".join(role_labels)
                _notify_staff_of_role_request(user, roles_text)
                _email_secretariat_of_role_request(request, user, roles_text)
                confirmation_note = (
                    "we've emailed you a confirmation, and we'll notify you again as soon as it's reviewed."
                    if emailed else
                    "we couldn't send the confirmation email right now, but your request has been recorded "
                    "and we'll notify you as soon as it's reviewed."
                )
                if user.wants_applicant:
                    messages.success(
                        request,
                        f"Welcome to MSREC! Your account is ready. Your {roles_text} request is "
                        f"under review by the Secretariat — {confirmation_note}",
                    )
                else:
                    messages.success(
                        request,
                        f"Welcome to MSREC! Your {roles_text} request has been submitted and is under "
                        f"review by the Secretariat — {confirmation_note}",
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
        return render(request, "pages/signup.html", {"form": form, "institutions": _active_institutions()}, status=400)

    form = SignupForm()
    return render(request, "pages/signup.html", {"form": form, "institutions": _active_institutions()})


def _after_login(user, next_url=""):
    """Where to send someone who is signed in. While maintenance mode locks
    the site, an administrator always lands in the admin area (the only
    place that's open), whatever dashboard their role would normally use
    and even if a saved ?next= points at a locked page."""
    from pages import maintenance

    try:
        locked = maintenance.state()["active"]
    except Exception:
        locked = False
    if locked and maintenance.is_bypass_user(user):
        return next_url if next_url.startswith("/admins/") else "admin_dashboard:home"
    return next_url or user.dashboard_url_name()


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_after_login(request.user))

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
            next_url = request.POST.get("next") or request.GET.get("next") or ""
            return redirect(_after_login(user, next_url))
        # A time-boxed suspension raises a ValidationError with an
        # internal sentinel so the view can render a nicer "you'll be
        # able to sign in again on ..." modal instead of a flat flash.
        suspended_modal = None
        real_errors = []
        for error in form.non_field_errors():
            if isinstance(error, str) and error.startswith("__SUSPENDED_UNTIL__"):
                from django.utils.dateparse import parse_datetime
                iso = error[len("__SUSPENDED_UNTIL__"):]
                until = parse_datetime(iso)
                suspended_modal = {
                    "until": until,
                    "reason": getattr(form, "suspended_reason", "") or "",
                    "email": (request.POST.get("email") or "").strip().lower(),
                }
                continue
            real_errors.append(error)
        for error in real_errors:
            messages.error(request, error)
        return render(request, "pages/login.html",
                      {"form": form, "suspended_modal": suspended_modal}, status=400)

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


@login_required
def membership_certificate(request):
    """The signed-in Reviewer's / Committee member's own Membership
    Certificate: the print-ready web version, or ?format=pdf for the same
    PDF that was attached to their welcome email."""
    from . import membership

    user = request.user
    if not membership.is_member(user):
        raise Http404("No membership certificate has been issued for this account yet.")
    if request.GET.get("format") == "pdf":
        response = HttpResponse(membership.render_certificate_pdf(user), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{membership.certificate_filename(user)}"'
        return response
    context = membership.certificate_context(user)
    context["back_url"] = reverse(user.dashboard_url_name())
    return render(request, "certificates/award_certificate.html", context)


@login_required
def appointment_letter(request):
    """PDF download of the signed-in Reviewer's / Committee member's own
    Appointment Letter -- the same PDF that was attached to their welcome
    email, in case that email couldn't be sent or was misplaced. Rendered
    on demand like the certificate above, so it always reflects the
    current Chair signature and Ethics ID."""
    from . import membership

    user = request.user
    if not membership.is_member(user):
        raise Http404("No appointment letter has been issued for this account yet.")
    response = HttpResponse(membership.render_appointment_letter_pdf(user), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{membership.appointment_letter_filename(user)}"'
    return response
