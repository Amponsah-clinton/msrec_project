"""Committee member account pages: Notifications, Profile & Committee
Appointment and Security. Imported into views.py so the URLconf keeps
resolving everything through one module."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import AuditLog, RoleApprovalLog, User
from accounts.sessions import active_sessions_for
from admin_dashboard.views import _handle_admin_remove_avatar, _handle_admin_update_avatar
from meetings.models import Meeting, MeetingParticipant
from notifications import services as notification_services
from notifications.models import Notification
from pages import documents_storage
from pages.models import GovernanceMember

from .views import committee_required


AUDIENCE = Notification.Audience.COMMITTEE


def _shell_context(request):
    """What the shared topbar's notification bell needs on every page."""
    return {
        "notifications": notification_services.for_user(request.user, AUDIENCE, limit=6),
        "unread_count": notification_services.unread_count(request.user, AUDIENCE),
    }


# ---------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------

def _day_bucket(moment, today):
    day = timezone.localtime(moment).date()
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    if (today - day).days < 7:
        return "This week"
    return "Earlier"


_BUCKET_ORDER = ["Today", "Yesterday", "This week", "Earlier"]


def _handle_update_notification_prefs(request):
    user = request.user
    user.notify_email_alerts = bool(request.POST.get("notify_email"))
    user.notify_sms_alerts = bool(request.POST.get("notify_sms"))
    user.notify_weekly_digest = bool(request.POST.get("notify_weekly_digest"))

    profile = dict(user.committee_profile or {})
    profile["notifyMeetingInvites"] = bool(request.POST.get("notify_meeting_invites"))
    profile["notifyDecisionRequests"] = bool(request.POST.get("notify_decision_requests"))
    for post_key, profile_key in (("quiet_hours_from", "quietHoursFrom"), ("quiet_hours_to", "quietHoursTo")):
        value = request.POST.get(post_key, "").strip()
        if value:
            profile[profile_key] = value
    user.committee_profile = profile

    user.save(update_fields=[
        "notify_email_alerts", "notify_sms_alerts", "notify_weekly_digest", "committee_profile",
    ])
    messages.success(request, "Notification preferences saved.")


@login_required
@committee_required
def notifications(request):
    if request.method == "POST":
        if request.POST.get("action") == "update_notification_prefs":
            _handle_update_notification_prefs(request)
        else:
            messages.error(request, "That request could not be processed.")
        return redirect("committee_dashboard:notifications")

    user = request.user
    now = timezone.now()
    today = timezone.localdate()

    feed = notification_services.for_user(user, AUDIENCE, limit=100)
    groups = {label: [] for label in _BUCKET_ORDER}
    for item in feed:
        item.category = "alert" if item.icon == Notification.Icon.WARN else "update"
        groups[_day_bucket(item.created_at, today)].append(item)
    grouped_feed = [(label, groups[label]) for label in _BUCKET_ORDER if groups[label]]

    invites = list(
        MeetingParticipant.objects.filter(
            user=user, meeting__scheduled_at__gte=now, meeting__status=Meeting.Status.SCHEDULED,
        ).select_related("meeting").order_by("meeting__scheduled_at")
    )
    profile = user.committee_profile or {}

    return render(request, "dashboards/committee/notifications.html", {
        **_shell_context(request),
        "grouped_feed": grouped_feed,
        "total_count": Notification.objects.filter(audience=AUDIENCE).count(),
        "feed_count": len(feed),
        "alert_count": sum(1 for i in feed if i.category == "alert"),
        "update_count": sum(1 for i in feed if i.category == "update"),
        "upcoming_invites": invites[:4],
        "upcoming_count": len(invites),
        "pending_rsvp_count": sum(1 for i in invites if i.rsvp_status == MeetingParticipant.RsvpStatus.PENDING),
        "notify_meeting_invites": profile.get("notifyMeetingInvites", True),
        "notify_decision_requests": profile.get("notifyDecisionRequests", True),
        "quiet_hours_from": profile.get("quietHoursFrom", "21:00"),
        "quiet_hours_to": profile.get("quietHoursTo", "07:00"),
    })


# ---------------------------------------------------------------------
# Profile & Committee Appointment
# ---------------------------------------------------------------------

EXPERTISE_CHOICES = [
    ("health-biomedical", "Health / Biomedical Science"),
    ("social-behavioral", "Social / Behavioral Science"),
    ("methodology-biostatistics", "Research Methodology / Biostatistics"),
    ("law-privacy", "Law / Data Protection / Privacy"),
    ("ethics-bioethics", "Ethics / Bioethics"),
    ("lay-community", "Lay / Community Representative"),
    ("independent-external", "Independent External Member"),
    ("other", "Other"),
]
_EXPERTISE_VALUES = {value for value, _label in EXPERTISE_CHOICES}
_EXPERTISE_LABELS = dict(EXPERTISE_CHOICES)


def _handle_update_profile(request):
    user = request.user
    post = request.POST

    first_name = post.get("first_name", "").strip()
    last_name = post.get("last_name", "").strip()
    email = post.get("email", "").strip().lower()
    if not first_name or not last_name:
        messages.error(request, "First and last name are required.")
        return
    if not email:
        messages.error(request, "Email is required.")
        return
    if User.objects.exclude(pk=user.pk).filter(email=email).exists():
        messages.error(request, "Another account already uses that email address.")
        return

    years = post.get("years", "").strip()
    if years and (not years.isdigit() or int(years) > 80):
        messages.error(request, "Years of professional experience must be a whole number.")
        return

    user.title = post.get("title", "").strip()
    user.first_name = first_name
    user.last_name = last_name
    user.email = email
    user.phone = post.get("phone", "").strip()
    user.country_residence = post.get("country_residence", "").strip()
    user.position = post.get("position", "").strip()
    user.institution = post.get("institution", "").strip()
    user.department = post.get("department", "").strip()

    # The signup form's committee answers live in this JSON column under
    # the same keys, so a profile edited here and one filled in at signup
    # are always the same record.
    profile = dict(user.committee_profile or {})
    profile.update({
        "committeePosition": user.position,
        "committeeInstitution": user.institution,
        "committeeYears": years,
        "committeeBackground": post.get("background", "").strip(),
        "committeeBio": post.get("bio", "").strip(),
        "committeeExpertiseCategory": [v for v in post.getlist("expertise") if v in _EXPERTISE_VALUES],
    })
    user.committee_profile = profile

    user.save(update_fields=[
        "title", "first_name", "last_name", "email", "phone", "country_residence",
        "position", "institution", "department", "committee_profile",
    ])
    AuditLog.record(user, "user.profile_updated", target=user, description="Committee profile updated")
    messages.success(request, "Profile saved.")


def _appointment_context(user):
    seat = GovernanceMember.objects.filter(user=user).first()
    approval = (
        RoleApprovalLog.objects.filter(user=user, role=User.Role.COMMITTEE, action=RoleApprovalLog.Action.APPROVED)
        .select_related("acted_by").order_by("-created_at").first()
    )
    context = {"seat": seat, "approval": approval, "appointments": [], "training": [], "conflicts": []}
    if not seat:
        return context

    appointments = list(seat.appointments.all())
    for appointment in appointments:
        appointment.letter_url = documents_storage.public_url(appointment.letter_path) if appointment.letter_path else None
        if appointment.end_date:
            total = (appointment.end_date - appointment.start_date).days or 1
            elapsed = (timezone.localdate() - appointment.start_date).days
            appointment.term_pct = max(0, min(100, round(100 * elapsed / total)))
        else:
            appointment.term_pct = None
    context["appointments"] = appointments
    context["current_appointment"] = next(
        (a for a in appointments if a.status in ("active", "renewed")), appointments[0] if appointments else None,
    )
    context["training"] = list(seat.training_records.all())
    context["conflicts"] = list(seat.conflict_declarations.all())
    return context


@login_required
@committee_required
def profile(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_profile":
            _handle_update_profile(request)
        elif action == "update_avatar":
            _handle_admin_update_avatar(request)
        elif action == "remove_avatar":
            _handle_admin_remove_avatar(request)
        else:
            messages.error(request, "That request could not be processed.")
        return redirect("committee_dashboard:profile")

    user = request.user
    data = user.committee_profile or {}
    chosen = data.get("committeeExpertiseCategory") or []
    if isinstance(chosen, str):
        chosen = [chosen]

    invites = MeetingParticipant.objects.filter(user=user, meeting__status=Meeting.Status.COMPLETED)
    stats = {
        "meetings_invited": invites.count(),
        "meetings_attended": invites.filter(attended=True).count(),
    }

    completeness_fields = [
        user.profile_photo_path, user.phone, user.position, user.institution,
        data.get("committeeYears"), data.get("committeeBackground"),
        data.get("committeeBio"), chosen,
    ]
    completeness = round(100 * sum(1 for f in completeness_fields if f) / len(completeness_fields))

    return render(request, "dashboards/committee/profile.html", {
        **_shell_context(request),
        **_appointment_context(user),
        "data": data,
        "stats": stats,
        "completeness": completeness,
        "expertise_choices": EXPERTISE_CHOICES,
        "chosen_expertise": chosen,
        "chosen_expertise_labels": [_EXPERTISE_LABELS.get(v, v) for v in chosen],
        "title_choices": ["Prof.", "Dr.", "Rev.", "Mr.", "Mrs.", "Ms.", "Madam", "Barr.", "Engr."],
    })


@login_required
@committee_required
def certificate_download(request):
    """Shows the requesting committee member's own Membership Certificate
    as a full-page, print-ready HTML certificate (its own "Print / Save as
    PDF" button covers getting a file, via the browser's native
    print-to-PDF -- see templates/certificates/award_certificate.html).
    membership_ethics_id is only ever set by User.approve_role once the
    Secretariat/an admin confirms the Committee request (see
    accounts.models.User.approve_role), so a 404 here means "not confirmed
    yet" rather than a broken link. The PDF attached to the approval email
    is a separate, simpler reportlab rendering (see
    committee_dashboard/certificate.py) -- generating this exact HTML
    design server-side would need a system HTML-to-PDF engine (WeasyPrint
    + GTK3) this Windows dev box doesn't have installed."""
    user = request.user
    if not user.membership_ethics_id:
        raise Http404("No membership certificate has been issued for this account yet.")

    role_title = (user.committee_profile or {}).get("committeePosition") or user.position or "Committee Member"
    return render(request, "certificates/award_certificate.html", {
        "cert_title": "Certificate",
        "cert_subtitle": "of Membership",
        "recipient_name": user.full_name,
        "message": (
            f"In recognition of your confirmed membership of the Metascholar Research<br>"
            f"Ethics Committee, serving as {role_title}, in good standing with MSREC's governing charter"
        ),
        "cert_id": user.membership_ethics_id,
        "issued_on": user.membership_confirmed_at,
        "left_name": "Secretariat",
        "left_role": "MSREC Secretariat",
        "right_name": "Chair",
        "right_role": "MSREC Committee Chair",
        "back_url": reverse("committee_dashboard:profile"),
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
    # Keeps this browser signed in -- changing your own password would
    # otherwise invalidate the very session you just used to change it.
    update_session_auth_hash(request, user)
    AuditLog.record(user, "user.password_changed", target=user, description="Password changed from Security page")
    messages.success(request, "Password updated.")


def _handle_update_security_prefs(request):
    user = request.user
    user.two_factor_app = bool(request.POST.get("two_factor_app"))
    user.two_factor_sms = bool(request.POST.get("two_factor_sms"))
    user.notify_new_signin = bool(request.POST.get("notify_new_signin"))

    profile = dict(user.committee_profile or {})
    profile["twoFactorEmail"] = bool(request.POST.get("two_factor_email"))
    profile["blockUnrecognisedCountries"] = bool(request.POST.get("block_unrecognised_countries"))
    user.committee_profile = profile

    user.save(update_fields=["two_factor_app", "two_factor_sms", "notify_new_signin", "committee_profile"])
    AuditLog.record(user, "user.security_updated", target=user, description="Security preferences updated")
    messages.success(request, "Security preferences saved.")


def _user_sessions(user):
    return [
        session for session in Session.objects.filter(expire_date__gte=timezone.now())
        if session.get_decoded().get("_auth_user_id") == str(user.pk)
    ]


def _handle_revoke_session(request):
    session_key = request.POST.get("session_key", "")
    if session_key and session_key != request.session.session_key:
        session = Session.objects.filter(pk=session_key).first()
        if session and session.get_decoded().get("_auth_user_id") == str(request.user.pk):
            session.delete()
            AuditLog.record(request.user, "user.session_revoked", target=request.user, description="Signed out one device")
            messages.success(request, "That device has been signed out.")
            return
    messages.error(request, "That session could not be found.")


def _handle_revoke_other_sessions(request):
    others = [s for s in _user_sessions(request.user) if s.session_key != request.session.session_key]
    for session in others:
        session.delete()
    if others:
        AuditLog.record(
            request.user, "user.session_revoked", target=request.user,
            description=f"Signed out {len(others)} other device{'s' if len(others) != 1 else ''}",
        )
        messages.success(request, f"Signed out {len(others)} other device{'s' if len(others) != 1 else ''}.")
    else:
        messages.info(request, "This is the only device signed in.")


_ACTIVITY_LABELS = {
    "user.password_changed": ("Password changed", "ok"),
    "user.security_updated": ("Security preferences updated", "ok"),
    "user.profile_updated": ("Profile updated", "ok"),
    "user.session_revoked": ("Device signed out", "warn"),
    "user.suspended": ("Account suspended", "fail"),
    "user.activated": ("Account re-activated", "ok"),
    "user.edited": ("Account edited by an administrator", "ok"),
}


@login_required
@committee_required
def security(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_password":
            _handle_update_password(request)
        elif action == "update_security_prefs":
            _handle_update_security_prefs(request)
        elif action == "revoke_session":
            _handle_revoke_session(request)
        elif action == "revoke_other_sessions":
            _handle_revoke_other_sessions(request)
        else:
            messages.error(request, "That request could not be processed.")
        return redirect("committee_dashboard:security")

    user = request.user
    profile = user.committee_profile or {}
    sessions = active_sessions_for(user, current_session_key=request.session.session_key)
    two_factor_email = profile.get("twoFactorEmail", True)
    has_2fa = user.two_factor_app or user.two_factor_sms or two_factor_email

    score = 40
    if has_2fa:
        score += 30
    if user.notify_new_signin:
        score += 15
    if len(sessions) <= 1:
        score += 15
    score_label = "Strong" if score >= 85 else "Good" if score >= 55 else "Needs attention"

    logs = AuditLog.objects.filter(
        Q(actor=user) | Q(target_type="User", target_id=str(user.pk)), action__startswith="user.",
    ).order_by("-created_at")[:8]
    activity = []
    for log in logs:
        label, tone = _ACTIVITY_LABELS.get(log.action, (log.action.replace("user.", "").replace("_", " ").capitalize(), "ok"))
        activity.append({"label": label, "tone": tone, "detail": log.description, "at": log.created_at})
    if user.last_login:
        activity.append({
            "label": "Last sign-in", "tone": "ok",
            "detail": "The most recent successful sign-in to this account", "at": user.last_login,
        })
    activity.sort(key=lambda row: row["at"], reverse=True)

    return render(request, "dashboards/committee/security.html", {
        **_shell_context(request),
        "sessions": sessions,
        "other_session_count": sum(1 for s in sessions if not s["is_current"]),
        "two_factor_email": two_factor_email,
        "has_2fa": has_2fa,
        "block_unrecognised_countries": profile.get("blockUnrecognisedCountries", False),
        "security_score": score,
        "security_score_label": score_label,
        "activity": activity[:8],
        "password_changed_at": AuditLog.objects.filter(
            actor=user, action="user.password_changed",
        ).values_list("created_at", flat=True).first(),
    })
