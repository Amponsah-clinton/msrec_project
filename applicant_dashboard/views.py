import uuid

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.sessions import active_sessions_for
from notifications.models import Notification
from notifications.services import notify
from payments import fees

from . import storage
from .models import Application

# Checkbox groups on the application form where more than one value can be
# ticked (name="..." repeated across several <input type="checkbox">) --
# these always come back as a list in form_data, even if only one box was
# checked. Every other posted field is a single value (text/textarea/select/
# radio/hidden yes-no toggle).
MULTI_CHECKBOX_FIELDS = {
    "researchArea", "studyType", "dataCollection", "possibleRisks",
    "consentMethod", "sensitiveInfo", "aiType", "aiDataSource",
    "systemType", "documentsAttached",
}

# Research-team rows post as three parallel arrays (one entry per row) --
# collapsed into form_data["researchTeam"] instead of kept as raw arrays.
TEAM_FIELDS = ("teamName[]", "teamRole[]", "teamInstitution[]")

# Never belongs in form_data: Django's own CSRF field, the requested review
# type (its own Application.review_type column), and the bookkeeping fields
# the draft/autosave machinery adds to the same <form> (which application
# this is, draft-vs-submit, and the client's completion-percentage guess).
SKIP_FIELDS = {
    "csrfmiddlewaretoken", "requestedReview", "formAction",
    "application_id", "completionPct",
}


def _collect_form_data(post):
    data = {}
    for key in post:
        if key in SKIP_FIELDS or key in TEAM_FIELDS:
            continue
        if key == "confirmDeclaration":
            data[key] = True
            continue
        if key in MULTI_CHECKBOX_FIELDS:
            data[key] = post.getlist(key)
        else:
            data[key] = post.get(key, "")

    names = post.getlist("teamName[]")
    roles = post.getlist("teamRole[]")
    institutions = post.getlist("teamInstitution[]")
    data["researchTeam"] = [
        {"name": name.strip(), "role": role.strip(), "institution": institution.strip()}
        for name, role, institution in zip(names, roles, institutions)
        if name.strip() or role.strip() or institution.strip()
    ]

    return data


def _apply_posted_fields(application, request):
    """Common to every write path (autosave, manual "Save as Draft", and
    final submit): copy the posted form over onto `application` and append
    any newly-uploaded documents. Doesn't touch status/timestamps -- callers
    decide those since draft-saves and submits treat them differently."""
    application.review_type = request.POST.get("requestedReview", "")
    application.form_data = _collect_form_data(request.POST)

    pct = request.POST.get("completionPct")
    try:
        application.completion_pct = max(0, min(100, int(pct)))
    except (TypeError, ValueError):
        pass

    uploaded_files = request.FILES.getlist("documents")
    if uploaded_files:
        # Documents -> Supabase Storage "application" bucket, grouped under
        # one folder per save. A Storage outage never blocks the save -- a
        # failed upload just means that file is skipped (see
        # applicant_dashboard/storage.py). Autosave never posts files (see
        # apply.js), so this only runs on the real Submit / Save-as-Draft
        # button, each of which is a normal multipart form submission.
        upload_folder = uuid.uuid4().hex
        documents = list(application.documents or [])
        for uploaded in uploaded_files:
            object_path = storage.upload_application_file(uploaded, folder=upload_folder)
            if object_path:
                documents.append({
                    "name": uploaded.name,
                    "path": object_path,
                    "size": uploaded.size,
                    "content_type": getattr(uploaded, "content_type", "") or "",
                })
        application.documents = documents


def _initial_data_for_template(form_data, review_type):
    """`requestedReview` never lands in form_data (it's its own column --
    see SKIP_FIELDS), but apply.js's populateForm() restores everything
    from one JSON blob, so fold it back in just for that trip to the
    template."""
    data = dict(form_data or {})
    if review_type:
        data["requestedReview"] = review_type
    return data


def _get_draft_or_404(request, pk):
    return get_object_or_404(
        Application, pk=pk, applicant=request.user, status=Application.Status.DRAFT
    )


def finalize_submission(application, request):
    """The one place an application actually becomes SUBMITTED -- called
    either directly (fee-exempt review types) or by payments.views.verify
    once Paystack has genuinely confirmed a successful payment (paid review
    types). Assigns the reference number, notifies the Secretariat, exactly
    once either way."""
    application.status = Application.Status.SUBMITTED
    application.completion_pct = 100
    application.submitted_at = timezone.now()
    application.save()
    if not application.reference_no:
        application.assign_reference_no()

    notify(
        Notification.Audience.SECRETARIAT,
        f"New application {application.reference_no} submitted by {application.applicant.full_name}.",
        icon=Notification.Icon.INFO,
        link_url_name="secretariat_dashboard:application_detail",
        link_kwargs={"pk": application.pk},
    )
    messages.success(request, f"Application {application.reference_no} submitted successfully.")
    return application


def payments_fees(request):
    return render(request, "dashboards/applicant/payments-fees.html", _fee_schedule_context())


def _fee_schedule_context():
    """Live fee amounts for the application form -- keyed with underscores
    (not the raw `requestedReview` values like "not-sure") since Django
    template variable lookups can't contain hyphens."""
    schedule = fees.schedule()
    return {
        "fee_exemption": schedule.get("exemption"),
        "fee_expedited": schedule.get("expedited"),
        "fee_full": schedule.get("full"),
        "fee_not_sure": schedule.get("not-sure"),
        "fee_schedule_list": [fee for fee in schedule.values() if fee],
    }


def application_form(request):
    draft = None
    draft_id = request.GET.get("draft") or request.POST.get("application_id")
    if draft_id:
        draft = _get_draft_or_404(request, draft_id)

    if request.method == "POST":
        application = draft or Application(applicant=request.user)
        form_action = request.POST.get("formAction", "submit")

        if form_action == "draft":
            _apply_posted_fields(application, request)
            application.status = Application.Status.DRAFT
            application.save()
            messages.success(
                request,
                "Draft saved. Pick up where you left off anytime from Draft Applications.",
            )
            return redirect("applicant_dashboard:application_drafts")

        if not request.POST.get("confirmDeclaration"):
            messages.error(
                request,
                "Please confirm the Principal Investigator declaration before submitting.",
            )
            # Re-show exactly what they'd typed (not the draft's last saved
            # state) so a missed declaration checkbox doesn't cost them
            # everything they'd just filled in -- just don't persist it yet.
            return render(
                request,
                "dashboards/applicant/application-form.html",
                {
                    "draft_application": draft,
                    "initial_data": _initial_data_for_template(
                        _collect_form_data(request.POST), request.POST.get("requestedReview", "")
                    ),
                    **_fee_schedule_context(),
                },
                status=400,
            )

        _apply_posted_fields(application, request)

        if fees.requires_payment(application.review_type):
            # Saved as a draft for now -- finalize_submission() only runs
            # once payments.views.verify has a genuine Paystack success for
            # this application, never from this request directly. That's
            # the whole payment gate: no verified payment, no submission.
            application.status = Application.Status.DRAFT
            application.completion_pct = 100
            application.save()
            return redirect("applicant_dashboard:application_pay", pk=application.pk)

        finalize_submission(application, request)
        return render(
            request,
            "dashboards/applicant/application-form.html",
            {"submitted": True, "application": application},
        )

    return render(request, "dashboards/applicant/application-form.html", {
        "draft_application": draft,
        "initial_data": _initial_data_for_template(
            draft.form_data if draft else {}, draft.review_type if draft else ""
        ),
        **_fee_schedule_context(),
    })


@require_POST
def autosave_application(request):
    """Fired by apply.js a couple of seconds after the applicant stops
    typing/ticking boxes -- keeps a running draft up to date without the
    applicant ever having to click Save. Never touches file uploads (those
    only travel on a real Submit / Save-as-Draft form post); returns JSON
    since it's called from fetch(), not a page navigation."""
    draft_id = request.POST.get("application_id")
    application = None
    if draft_id:
        application = Application.objects.filter(
            pk=draft_id, applicant=request.user, status=Application.Status.DRAFT
        ).first()
        if application is None:
            # Gone, or no longer a draft (submitted from another tab,
            # deleted, ...) -- start a fresh draft row instead of erroring
            # the autosave loop out forever on a stale id.
            return JsonResponse({"error": "stale_draft"}, status=409)
    if application is None:
        application = Application(applicant=request.user)

    _apply_posted_fields(application, request)
    application.status = Application.Status.DRAFT
    application.save()

    return JsonResponse({
        "application_id": application.pk,
        "completion_pct": application.completion_pct,
        "title": application.title,
        "saved_at": application.updated_at.isoformat(),
    })


def application_drafts(request):
    drafts = Application.objects.filter(
        applicant=request.user, status=Application.Status.DRAFT
    ).order_by("-updated_at")
    return render(request, "dashboards/applicant/application-drafts.html", {"drafts": drafts})


@require_POST
def delete_draft(request, pk):
    draft = _get_draft_or_404(request, pk)
    draft.delete()
    messages.success(request, "Draft deleted.")
    return redirect("applicant_dashboard:application_drafts")


INSTITUTION_FIELDS = [
    "institution", "department", "faculty", "institution_address",
    "position", "staff_student_id", "hod_name", "hod_email",
    "irb_name", "irb_reference_no",
]


def institution(request):
    if request.method == "POST":
        hod_email = request.POST.get("hod_email", "").strip()
        if hod_email:
            try:
                validate_email(hod_email)
            except ValidationError:
                messages.error(request, "Enter a valid email address for the Head of Department.")
                return redirect("applicant_dashboard:institution")

        user = request.user
        for field in INSTITUTION_FIELDS:
            setattr(user, field, request.POST.get(field, "").strip())
        user.save(update_fields=INSTITUTION_FIELDS)
        messages.success(request, "Institutional information updated.")
        return redirect("applicant_dashboard:institution")

    return render(request, "dashboards/applicant/institution-affiliation.html")


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

    user.title = title
    user.first_name = first_name
    user.last_name = last_name
    user.phone = phone
    user.orcid = orcid
    user.email = email
    user.two_factor_app = bool(request.POST.get("two_factor_app"))
    user.two_factor_sms = bool(request.POST.get("two_factor_sms"))
    user.notify_new_signin = bool(request.POST.get("notify_new_signin"))

    update_fields = [
        "title", "first_name", "last_name", "phone", "orcid", "email",
        "two_factor_app", "two_factor_sms", "notify_new_signin",
    ]

    # Password change is optional and bundled into the same "Save Changes"
    # submit -- any of the three fields being filled in triggers full
    # validation of all three, rather than silently ignoring a half-filled
    # attempt.
    current_password = request.POST.get("current_password", "")
    new_password = request.POST.get("new_password", "")
    confirm_password = request.POST.get("confirm_password", "")
    if current_password or new_password or confirm_password:
        if not current_password or not user.check_password(current_password):
            messages.error(request, "Your current password is incorrect.")
            return
        if new_password != confirm_password:
            messages.error(request, "New password and confirmation don't match.")
            return
        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return
        user.set_password(new_password)
        update_fields.append("password")

    user.save(update_fields=update_fields)
    if "password" in update_fields:
        # Changing the password rotates Django's session auth hash --
        # without this the applicant would be logged out by their own
        # password change on the very page they just used to make it.
        update_session_auth_hash(request, user)
        messages.success(request, "Profile updated and password changed.")
    else:
        messages.success(request, "Profile updated.")


def _handle_update_avatar(request):
    uploaded = request.FILES.get("avatar")
    if not uploaded:
        messages.error(request, "Choose an image to upload first.")
        return
    if not (uploaded.content_type or "").startswith("image/"):
        messages.error(request, "Please upload an image file (JPG or PNG).")
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


def _handle_revoke_session(request):
    session_key = request.POST.get("session_key", "")
    if session_key and session_key != request.session.session_key:
        session = Session.objects.filter(pk=session_key).first()
        if session and session.get_decoded().get("_auth_user_id") == str(request.user.pk):
            session.delete()
            messages.success(request, "That session has been signed out.")
            return
    messages.error(request, "That session could not be found.")


def profile_security(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "update_profile":
            _handle_update_profile(request)
        elif action == "update_avatar":
            _handle_update_avatar(request)
        elif action == "remove_avatar":
            _handle_remove_avatar(request)
        elif action == "revoke_session":
            _handle_revoke_session(request)
        else:
            messages.error(request, "That request could not be processed.")
        return redirect("applicant_dashboard:profile_security")

    sessions = active_sessions_for(request.user, current_session_key=request.session.session_key)
    return render(request, "dashboards/applicant/profile-security.html", {"sessions": sessions})


def _my_applications(request, *, status=None):
    """Every one of this applicant's own applications -- optionally
    narrowed to one status -- newest submission first. Drafts are never
    included here; that's what Draft Applications / application_drafts is
    for (see _get_draft_or_404 and application_drafts above)."""
    qs = Application.objects.filter(applicant=request.user).exclude(status=Application.Status.DRAFT)
    if status:
        qs = qs.filter(status=status)
    return qs.order_by("-submitted_at")


def home(request):
    all_applications = Application.objects.filter(applicant=request.user)
    counts = {
        "draft": all_applications.filter(status=Application.Status.DRAFT).count(),
        "under_review": all_applications.filter(status=Application.Status.UNDER_REVIEW).count(),
        "revisions": all_applications.filter(status=Application.Status.REVISIONS_REQUIRED).count(),
        "approved": all_applications.filter(status=Application.Status.APPROVED).count(),
    }
    needs_revision = all_applications.filter(
        status=Application.Status.REVISIONS_REQUIRED
    ).order_by("-submitted_at").first()

    return render(request, "dashboards/applicant.html", {
        "my_applications": _my_applications(request)[:5],
        "counts": counts,
        "needs_revision": needs_revision,
        # "Notices" panel: real recent activity across every one of this
        # applicant's applications (drafts included, unlike my_applications)
        # ordered by whatever last touched them -- an edit, an autosave, or
        # a status change from the Secretariat/reviewer side.
        "recent_activity": all_applications.order_by("-updated_at")[:5],
    })


def application_submitted(request):
    return render(request, "dashboards/applicant/application-submitted.html", {
        "applications": _my_applications(request, status=Application.Status.SUBMITTED),
    })


def application_under_review(request):
    return render(request, "dashboards/applicant/application-under-review.html", {
        "applications": _my_applications(request, status=Application.Status.UNDER_REVIEW),
    })


def application_revisions(request):
    return render(request, "dashboards/applicant/application-revisions.html", {
        "applications": _my_applications(request, status=Application.Status.REVISIONS_REQUIRED),
    })


def application_approved(request):
    return render(request, "dashboards/applicant/application-approved.html", {
        "applications": _my_applications(request, status=Application.Status.APPROVED),
    })


def application_not_approved(request):
    return render(request, "dashboards/applicant/application-not-approved.html", {
        "applications": _my_applications(request, status=Application.Status.NOT_APPROVED),
    })


def application_detail(request, pk):
    application = get_object_or_404(
        Application.objects.exclude(status=Application.Status.DRAFT), pk=pk, applicant=request.user
    )
    documents = [
        {**doc, "url": storage.public_url(doc.get("path"))}
        for doc in (application.documents or [])
    ]
    return render(request, "dashboards/applicant/application-detail.html", {
        "application": application,
        "documents": documents,
        "review_type_label": fees.label_for(application.review_type),
    })
