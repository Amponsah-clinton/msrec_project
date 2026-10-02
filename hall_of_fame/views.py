import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import AuditLog, User
from notifications.emails import send_branded_email

from . import storage
from .certificate import render_hof_certificate_pdf
from .letter import render_recognition_letter_pdf
from .models import HallOfFameNomination, HofAuditLog

logger = logging.getLogger(__name__)

Status = HallOfFameNomination.Status


def _is_eligible(user):
    if not user.is_authenticated:
        return False
    return user.role in (
        User.Role.REVIEWER, User.Role.COMMITTEE, User.Role.CHAIR,
        User.Role.SECRETARIAT, User.Role.ADMIN, User.Role.APPLICANT,
        User.Role.INSTITUTION_SECRETARY,
    )


eligible_required = user_passes_test(_is_eligible, login_url="pages:login")


def _is_staff(user):
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.role in (
        User.Role.ADMIN, User.Role.SECRETARIAT, User.Role.CHAIR,
    )


staff_required = user_passes_test(_is_staff, login_url="pages:login")


def _log(nomination, actor, action, detail=""):
    HofAuditLog.objects.create(nomination=nomination, actor=actor, action=action, detail=detail)


def _save_files(request, nomination):
    changed = False
    photo = request.FILES.get("photo")
    if photo:
        path = storage.upload_photo(photo, nomination_id=nomination.pk)
        if path:
            nomination.photo_path = path
            changed = True

    cv = request.FILES.get("cv")
    if cv:
        path = storage.upload_cv(cv, nomination_id=nomination.pk)
        if path:
            nomination.cv_path = path
            changed = True

    report = request.FILES.get("activity_report")
    if report:
        path = storage.upload_activity_report(report, nomination_id=nomination.pk)
        if path:
            nomination.activity_report_path = path
            changed = True

    evidence = request.FILES.get("supporting_evidence")
    if evidence:
        path = storage.upload_supporting_evidence(evidence, nomination_id=nomination.pk)
        if path:
            nomination.supporting_evidence_path = path
            changed = True

    return changed


# ── Member-facing views ──────────────────────────────────────────────

@login_required
@eligible_required
def dashboard(request):
    nomination = HallOfFameNomination.objects.filter(user=request.user).first()
    return render(request, "hall_of_fame/dashboard.html", {
        "nomination": nomination,
        "can_nominate": nomination is None or nomination.status in (Status.REJECTED,),
    })


@login_required
@eligible_required
def nominate(request):
    existing = HallOfFameNomination.objects.filter(user=request.user).exclude(
        status__in=(Status.REJECTED, Status.ARCHIVED)
    ).first()
    if existing and existing.status != Status.DRAFT:
        return redirect("hall_of_fame:dashboard")

    nomination = existing

    if request.method == "POST":
        if not nomination:
            nomination = HallOfFameNomination(user=request.user)
            nomination.save()

        nomination.full_name = request.POST.get("full_name", "").strip()
        nomination.professional_title = request.POST.get("professional_title", "").strip()
        nomination.email = request.POST.get("email", "").strip()
        nomination.phone = request.POST.get("phone", "").strip()
        nomination.nationality = request.POST.get("nationality", "").strip()
        nomination.current_location = request.POST.get("current_location", "").strip()

        nomination.institution = request.POST.get("institution", "").strip()
        nomination.position = request.POST.get("position", "").strip()
        nomination.department = request.POST.get("department", "").strip()
        years = request.POST.get("years_experience", "").strip()
        nomination.years_experience = int(years) if years.isdigit() else None
        nomination.areas_of_expertise = request.POST.get("areas_of_expertise", "").strip()

        nomination.biography = request.POST.get("biography", "").strip()
        nomination.achievements = request.POST.get("achievements", "").strip()
        nomination.contribution = request.POST.get("contribution", "").strip()
        nomination.reason_for_nomination = request.POST.get("reason_for_nomination", "").strip()

        _save_files(request, nomination)

        action = request.POST.get("action", "save")

        if action == "submit":
            nomination.consent_accurate = bool(request.POST.get("consent_accurate"))
            nomination.consent_publish = bool(request.POST.get("consent_publish"))
            nomination.consent_verify = bool(request.POST.get("consent_verify"))
            nomination.status = Status.SUBMITTED
            nomination.submitted_at = timezone.now()
            nomination.save()
            _log(nomination, request.user, "submitted")
            return redirect("hall_of_fame:dashboard")
        else:
            nomination.save()
            _log(nomination, request.user, "draft_saved")
            return redirect("hall_of_fame:nominate")

    user = request.user
    if not nomination:
        initial = {
            "full_name": user.full_name,
            "professional_title": user.title,
            "email": user.email,
            "phone": user.phone,
            "institution": user.institution,
            "position": user.position,
            "department": user.department,
        }
    else:
        initial = None

    return render(request, "hall_of_fame/nominate.html", {
        "nomination": nomination,
        "initial": initial,
    })


@login_required
@eligible_required
def resubmit(request, pk):
    nomination = get_object_or_404(
        HallOfFameNomination, pk=pk, user=request.user, status=Status.REVISION_REQUESTED,
    )
    if request.method == "POST":
        nomination.full_name = request.POST.get("full_name", "").strip() or nomination.full_name
        nomination.professional_title = request.POST.get("professional_title", "").strip()
        nomination.biography = request.POST.get("biography", "").strip() or nomination.biography
        nomination.achievements = request.POST.get("achievements", "").strip() or nomination.achievements
        nomination.contribution = request.POST.get("contribution", "").strip() or nomination.contribution
        nomination.reason_for_nomination = request.POST.get("reason_for_nomination", "").strip() or nomination.reason_for_nomination
        nomination.institution = request.POST.get("institution", "").strip() or nomination.institution
        nomination.position = request.POST.get("position", "").strip() or nomination.position
        nomination.department = request.POST.get("department", "").strip() or nomination.department
        years = request.POST.get("years_experience", "").strip()
        if years.isdigit():
            nomination.years_experience = int(years)
        nomination.areas_of_expertise = request.POST.get("areas_of_expertise", "").strip() or nomination.areas_of_expertise

        _save_files(request, nomination)
        nomination.status = Status.RESUBMITTED
        nomination.submitted_at = timezone.now()
        nomination.save()
        _log(nomination, request.user, "resubmitted")
        return redirect("hall_of_fame:dashboard")

    return render(request, "hall_of_fame/resubmit.html", {"nomination": nomination})


@login_required
@eligible_required
def certificate_download(request):
    nomination = get_object_or_404(
        HallOfFameNomination, user=request.user, status__in=(Status.APPROVED, Status.PUBLISHED),
    )
    pdf = render_hof_certificate_pdf(nomination)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="MSREC-HoF-Certificate-{nomination.hof_member_id or nomination.pk}.pdf"'
    return response


@login_required
@eligible_required
def letter_download(request):
    nomination = get_object_or_404(
        HallOfFameNomination, user=request.user, status__in=(Status.APPROVED, Status.PUBLISHED),
    )
    pdf = render_recognition_letter_pdf(nomination)
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="MSREC-HoF-Letter-{nomination.letter_ref or nomination.pk}.pdf"'
    return response


# ── Secretary / Admin review views ───────────────────────────────────

@login_required
@staff_required
def admin_nominations(request):
    qs = HallOfFameNomination.objects.select_related("user", "reviewed_by").all()

    status_filter = request.GET.get("status", "")
    if status_filter:
        qs = qs.filter(status=status_filter)

    counts = {}
    all_noms = HallOfFameNomination.objects.all()
    for s in Status:
        counts[s.value] = all_noms.filter(status=s.value).count()
    counts["all"] = all_noms.count()

    return render(request, "hall_of_fame/admin_nominations.html", {
        "nominations": qs,
        "counts": counts,
        "current_status": status_filter,
        "statuses": Status,
        "current_year": timezone.now().year,
    })


@login_required
@staff_required
@require_POST
def admin_add_member(request):
    """Let an admin/secretary add a Hall of Fame member directly, skipping the
    nominate → review → approve chain. The record (and any photo) is saved to
    Supabase just like a normal nomination, and can be published immediately so
    it shows on the public directory.

    The nomination's ``user`` FK is set to the staff member who created it (it's
    a required ownership link, not the honoree's login); the honoree is
    identified by the ``full_name``/``email`` fields, exactly as in the normal
    flow where those are independent of the submitting account.
    """
    full_name = request.POST.get("full_name", "").strip()
    email = request.POST.get("email", "").strip()
    if not full_name or not email:
        messages.error(request, "A full name and an email address are required to add a member.")
        return redirect("hall_of_fame:admin_nominations")

    nomination = HallOfFameNomination(user=request.user)
    nomination.full_name = full_name
    nomination.email = email
    nomination.professional_title = request.POST.get("professional_title", "").strip()
    nomination.phone = request.POST.get("phone", "").strip()
    nomination.nationality = request.POST.get("nationality", "").strip()
    nomination.current_location = request.POST.get("current_location", "").strip()
    nomination.institution = request.POST.get("institution", "").strip()
    nomination.position = request.POST.get("position", "").strip()
    nomination.department = request.POST.get("department", "").strip()
    years = request.POST.get("years_experience", "").strip()
    nomination.years_experience = int(years) if years.isdigit() else None
    nomination.areas_of_expertise = request.POST.get("areas_of_expertise", "").strip()
    nomination.biography = request.POST.get("biography", "").strip()
    nomination.achievements = request.POST.get("achievements", "").strip()
    nomination.contribution = request.POST.get("contribution", "").strip()
    nomination.reason_for_nomination = request.POST.get("reason_for_nomination", "").strip()

    year = request.POST.get("recognition_year", "").strip()
    nomination.recognition_year = int(year) if year.isdigit() else timezone.now().year

    # Staff adding a member directly is vouching for them, so the consent and
    # review fields that the normal pipeline fills get set here.
    nomination.consent_accurate = True
    nomination.consent_publish = True
    nomination.consent_verify = True
    nomination.approved_biography = nomination.biography
    nomination.submitted_at = timezone.now()
    nomination.reviewed_by = request.user
    nomination.reviewed_at = timezone.now()
    nomination.approved_at = timezone.now()

    publish_now = bool(request.POST.get("publish_now"))

    # First save mints the PK that the Supabase storage paths and the HoF IDs
    # both need; then upload the photo and persist the IDs/photo path/status.
    nomination.status = Status.APPROVED
    nomination.save()
    nomination.generate_hof_ids()
    _save_files(request, nomination)
    if publish_now:
        nomination.status = Status.PUBLISHED
        nomination.published_at = timezone.now()
    nomination.save()

    _log(nomination, request.user, "member_added",
         f"Added directly by {request.user.full_name or request.user.email}")

    if request.POST.get("send_email"):
        try:
            _send_approval_email(request, nomination)
        except Exception:
            logger.exception("Hall of Fame induction email failed for nomination %s", nomination.pk)
            messages.warning(request, f"{full_name} was added, but the induction email couldn't be sent.")

    where = "published to the public directory" if publish_now else "saved as an approved member"
    messages.success(request, f"{full_name} has been added to the Hall of Fame and {where}.")
    return redirect("hall_of_fame:admin_nominations")


@login_required
@staff_required
def admin_nomination_detail(request, pk):
    nomination = get_object_or_404(HallOfFameNomination.objects.select_related("user", "reviewed_by"), pk=pk)

    cv_url = storage.create_signed_url(nomination.cv_path) if nomination.cv_path else None
    report_url = storage.create_signed_url(nomination.activity_report_path) if nomination.activity_report_path else None
    evidence_url = storage.create_signed_url(nomination.supporting_evidence_path) if nomination.supporting_evidence_path else None
    photo_url = storage.public_url(nomination.photo_path) if nomination.photo_path else None
    audit_logs = nomination.audit_logs.select_related("actor").all()[:30]

    return render(request, "hall_of_fame/admin_detail.html", {
        "nom": nomination,
        "cv_url": cv_url,
        "report_url": report_url,
        "evidence_url": evidence_url,
        "photo_url": photo_url,
        "audit_logs": audit_logs,
    })


@login_required
@staff_required
@require_POST
def admin_action(request, pk):
    nomination = get_object_or_404(HallOfFameNomination, pk=pk)
    action = request.POST.get("action", "")

    if action == "under_review":
        nomination.status = Status.UNDER_REVIEW
        nomination.reviewed_by = request.user
        nomination.save()
        _log(nomination, request.user, "marked_under_review")

    elif action == "request_revision":
        message = request.POST.get("revision_message", "").strip()
        nomination.status = Status.REVISION_REQUESTED
        nomination.revision_message = message
        nomination.reviewed_by = request.user
        nomination.reviewed_at = timezone.now()
        nomination.save()
        _log(nomination, request.user, "revision_requested", message)
        send_branded_email(
            subject="MSREC Hall of Fame – Revision Requested",
            to=nomination.email,
            heading="Revision Requested",
            paragraphs=[
                f"Dear {nomination.full_name},",
                "Your Hall of Fame nomination requires some changes before it can be approved.",
                f"Message from the reviewer: {message}" if message else "Please check your dashboard for details.",
                "Please log in to your dashboard to make the requested changes and resubmit.",
            ],
            cta_text="Go to Dashboard",
            cta_url=request.build_absolute_uri("/dashboard/hall-of-fame/"),
        )

    elif action == "approve":
        approved_bio = request.POST.get("approved_biography", "").strip()
        nomination.status = Status.APPROVED
        nomination.approved_biography = approved_bio or nomination.biography
        nomination.approved_at = timezone.now()
        nomination.reviewed_by = request.user
        nomination.reviewed_at = timezone.now()
        nomination.recognition_year = timezone.now().year
        nomination.generate_hof_ids()
        nomination.save()
        _log(nomination, request.user, "approved")
        _send_approval_email(request, nomination)

    elif action == "publish":
        if nomination.status != Status.APPROVED:
            nomination.status = Status.APPROVED
            nomination.approved_biography = nomination.approved_biography or nomination.biography
            nomination.approved_at = nomination.approved_at or timezone.now()
            nomination.reviewed_by = request.user
            nomination.reviewed_at = timezone.now()
            nomination.recognition_year = nomination.recognition_year or timezone.now().year
            nomination.generate_hof_ids()
        nomination.status = Status.PUBLISHED
        nomination.published_at = timezone.now()
        nomination.save()
        _log(nomination, request.user, "published")
        if not nomination.approved_at or nomination.approved_at == nomination.published_at:
            _send_approval_email(request, nomination)

    elif action == "reject":
        reason = request.POST.get("rejection_reason", "").strip()
        nomination.status = Status.REJECTED
        nomination.rejection_reason = reason
        nomination.reviewed_by = request.user
        nomination.reviewed_at = timezone.now()
        nomination.save()
        _log(nomination, request.user, "rejected", reason)
        send_branded_email(
            subject="MSREC Hall of Fame – Nomination Update",
            to=nomination.email,
            heading="Nomination Not Approved",
            paragraphs=[
                f"Dear {nomination.full_name},",
                "After careful review, your Hall of Fame nomination has not been approved at this time.",
                f"Reason: {reason}" if reason else "",
                "If you believe this decision should be reconsidered, please contact the MSREC Secretariat.",
            ],
        )

    elif action == "unpublish":
        nomination.status = Status.APPROVED
        nomination.published_at = None
        nomination.save()
        _log(nomination, request.user, "unpublished")

    elif action == "archive":
        nomination.status = Status.ARCHIVED
        nomination.save()
        _log(nomination, request.user, "archived")

    elif action == "edit_biography":
        nomination.approved_biography = request.POST.get("approved_biography", "").strip()
        nomination.save()
        _log(nomination, request.user, "biography_edited")

    return redirect("hall_of_fame:admin_detail", pk=pk)


def _send_approval_email(request, nomination):
    cert_pdf = render_hof_certificate_pdf(nomination)
    letter_pdf = render_recognition_letter_pdf(nomination)
    send_branded_email(
        subject="Congratulations! You Have Been Inducted into the MSREC Hall of Fame",
        to=nomination.email,
        heading="Hall of Fame Induction",
        paragraphs=[
            f"Dear {nomination.full_name},",
            "Congratulations! Your nomination has been approved and you have been formally "
            "inducted into the MSREC Hall of Fame.",
            f"Your Hall of Fame ID is: {nomination.hof_member_id}",
            f"Recognition Year: {nomination.recognition_year}",
            "Your recognition certificate and official letter are attached to this email "
            "and are also available for download from your member dashboard.",
        ],
        cta_text="View Your Profile",
        cta_url=request.build_absolute_uri(f"/hall-of-fame/{nomination.pk}/"),
        callout_label="Hall of Fame ID",
        callout_value=nomination.hof_member_id,
        attachments=[
            (f"MSREC-HoF-Certificate-{nomination.hof_member_id}.pdf", cert_pdf, "application/pdf"),
            (f"MSREC-HoF-Letter-{nomination.letter_ref}.pdf", letter_pdf, "application/pdf"),
        ],
    )


# ── Public views ─────────────────────────────────────────────────────

_AVATAR_COLORS = ["#2a4747", "#7a4fb5", "#2f5fa8", "#1f7a5c", "#d97b29", "#c0392b", "#196D8A"]


def hall_of_fame_page(request):
    published = HallOfFameNomination.objects.filter(status=Status.PUBLISHED).order_by("-recognition_year", "full_name")
    members = []
    for nom in published:
        members.append({
            "pk": nom.pk,
            "full_name": nom.full_name,
            "professional_title": nom.professional_title,
            "institution": nom.institution,
            "position": nom.position,
            "areas_of_expertise": nom.areas_of_expertise,
            "expertise_tags": [t.strip() for t in (nom.areas_of_expertise or "").replace(";", ",").split(",") if t.strip()][:4],
            "recognition_year": nom.recognition_year,
            "photo_url": storage.public_url(nom.photo_path) if nom.photo_path else None,
            "initials": "".join(w[0] for w in nom.full_name.split()[:2]).upper() if nom.full_name else "?",
            "avatar_color": _AVATAR_COLORS[nom.pk % len(_AVATAR_COLORS)],
            "hof_member_id": nom.hof_member_id,
        })

    years = sorted(set(m["recognition_year"] for m in members if m["recognition_year"]), reverse=True)

    return render(request, "hall_of_fame/public_directory.html", {
        "members": members,
        "years": years,
        "total": len(members),
    })


def public_profile(request, pk):
    nomination = get_object_or_404(HallOfFameNomination, pk=pk, status=Status.PUBLISHED)
    photo_url = storage.public_url(nomination.photo_path) if nomination.photo_path else None

    from pages.verification import qr_svg_data_uri
    verify_data = f"MSREC Hall of Fame | {nomination.hof_member_id} | {nomination.full_name} | {nomination.recognition_year}"
    qr_uri = qr_svg_data_uri(verify_data)

    initials = "".join(w[0] for w in nomination.full_name.split()[:2]).upper() if nomination.full_name else "?"

    return render(request, "hall_of_fame/public_profile.html", {
        "nom": nomination,
        "photo_url": photo_url,
        "qr_uri": qr_uri,
        "initials": initials,
        "biography": nomination.approved_biography or nomination.biography,
    })
