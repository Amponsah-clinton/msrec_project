import uuid

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from accounts.sessions import active_sessions_for
from notifications.models import Notification
from notifications.services import notify
from payments import fees
from payments.models import Payment

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


def _get_editable_or_404(request, pk):
    """Like _get_draft_or_404, but also accepts a REVISIONS_REQUIRED
    application -- the one other status an applicant is allowed to load
    back into the form and edit (to fix what the Secretariat flagged and
    resubmit). Used only by application_form()/autosave_application();
    every other draft-only view (delete_draft, ...) keeps using
    _get_draft_or_404 on purpose."""
    return get_object_or_404(
        Application, pk=pk, applicant=request.user,
        status__in=[Application.Status.DRAFT, Application.Status.REVISIONS_REQUIRED],
    )


def finalize_submission(application, request):
    """The one place an application actually becomes SUBMITTED -- called
    either directly (fee-exempt review types, or a resubmission that was
    already paid for) or by payments.views.verify once Paystack has
    genuinely confirmed a successful payment (paid review types, first
    time). Assigns the reference number, notifies the Secretariat, exactly
    once either way.

    A resubmission is detected from revision_requested_at/resubmitted_at
    rather than the application's current `status` -- status is DRAFT for
    the whole time a paid resubmission is sitting at checkout waiting on
    Paystack, so checking `status == REVISIONS_REQUIRED` here would miss
    that case; these two timestamps are untouched by the payment detour."""
    is_resubmission = application.revision_requested_at is not None and (
        application.resubmitted_at is None
        or application.revision_requested_at > application.resubmitted_at
    )

    application.status = Application.Status.SUBMITTED
    application.completion_pct = 100
    if not application.submitted_at:
        application.submitted_at = timezone.now()
    if is_resubmission:
        application.resubmitted_at = timezone.now()
    application.save()
    if not application.reference_no:
        application.assign_reference_no()

    if is_resubmission:
        notify_message = (
            f"{application.applicant.full_name} resubmitted {application.reference_no} "
            "after requested revisions."
        )
    else:
        notify_message = f"New application {application.reference_no} submitted by {application.applicant.full_name}."
    notify(
        Notification.Audience.SECRETARIAT,
        notify_message,
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
        draft = _get_editable_or_404(request, draft_id)

    if request.method == "POST":
        application = draft or Application(applicant=request.user)
        form_action = request.POST.get("formAction", "submit")
        is_revision_edit = application.status == Application.Status.REVISIONS_REQUIRED

        if form_action == "draft":
            _apply_posted_fields(application, request)
            # A revision-in-progress edit stays REVISIONS_REQUIRED while
            # they're still working on it -- downgrading it to a plain
            # Draft here would drop it off the Secretariat's radar (and
            # the applicant's own Revisions Required list) before they've
            # actually resubmitted anything.
            if not is_revision_edit:
                application.status = Application.Status.DRAFT
            application.save()
            if is_revision_edit:
                messages.success(request, "Your changes have been saved. Resubmit whenever you're ready.")
                return redirect(f"{reverse('applicant_dashboard:application_form')}?draft={application.pk}")
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

        # A resubmission after revisions never pays twice -- if this
        # application already has one genuinely verified payment (any
        # amount, any review type), that satisfied the review-fee
        # requirement once and for all for this application.
        already_paid = bool(application.pk) and application.payments.filter(status=Payment.Status.SUCCESS).exists()

        if fees.requires_payment(application.review_type) and not already_paid:
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
        # REVISIONS_REQUIRED included on purpose: autosave also fires
        # while an applicant is fixing-and-resubmitting an application
        # the Secretariat sent back, and must keep saving into that same
        # row (see application_form) rather than treating it as gone.
        application = Application.objects.filter(
            pk=draft_id, applicant=request.user,
            status__in=[Application.Status.DRAFT, Application.Status.REVISIONS_REQUIRED],
        ).first()
        if application is None:
            # Gone, or no longer editable (submitted from another tab,
            # deleted, ...) -- start a fresh draft row instead of erroring
            # the autosave loop out forever on a stale id.
            return JsonResponse({"error": "stale_draft"}, status=409)
    if application is None:
        application = Application(applicant=request.user)

    _apply_posted_fields(application, request)
    # Don't downgrade a revision-in-progress edit to a plain Draft mid-
    # autosave -- same reasoning as the "Save as Draft" branch above.
    if application.status != Application.Status.REVISIONS_REQUIRED:
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
    confirm_email = request.POST.get("confirm_email", "").strip().lower()

    if not first_name or not last_name:
        messages.error(request, "First and last name are required.")
        return
    if not email:
        messages.error(request, "Email is required.")
        return
    if email != confirm_email:
        messages.error(request, "Email and Confirm Email don't match.")
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


def nav_counts(request):
    """Polled by nav-badges.js to keep the sidebar's Applications badges
    current without a full page reload -- e.g. the Secretariat moves an
    application to Under Review while the applicant already has a
    dashboard page open in another tab."""
    all_applications = Application.objects.filter(applicant=request.user)
    counts = {
        "draft": all_applications.filter(status=Application.Status.DRAFT).count(),
        "submitted": all_applications.filter(status=Application.Status.SUBMITTED).count(),
        "under_review": all_applications.filter(status=Application.Status.UNDER_REVIEW).count(),
        "revisions": all_applications.filter(status=Application.Status.REVISIONS_REQUIRED).count(),
        "approved": all_applications.filter(status=Application.Status.APPROVED).count(),
        "not_approved": all_applications.filter(status=Application.Status.NOT_APPROVED).count(),
    }
    return JsonResponse(counts)


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


def _progress_steps(application):
    """Drives the status tracker on the applicant's own application-detail
    page -- a plain, honest read of what's actually happened to this
    application so far, from the fields already on it (no separate
    status-history table to keep in sync). A "Revisions Requested" step
    only appears at all once one's actually been requested."""
    decided = application.status in (Application.Status.APPROVED, Application.Status.NOT_APPROVED)
    reached_review = (
        application.status != Application.Status.SUBMITTED
        or application.decided_at is not None
        or application.revision_count > 0
    )

    steps = [
        {"key": "submitted", "label": "Submitted", "done": True, "current": False, "date": application.submitted_at},
        {
            "key": "under_review", "label": "Under Review", "done": reached_review,
            "current": application.status == Application.Status.UNDER_REVIEW, "date": None,
        },
    ]
    if application.revision_count > 0:
        steps.append({
            "key": "revisions", "label": "Revisions Requested",
            "done": application.resubmitted_at is not None,
            "current": application.status == Application.Status.REVISIONS_REQUIRED,
            "date": application.revision_requested_at,
        })
    steps.append({
        "key": "decision",
        "label": "Approved" if application.status == Application.Status.APPROVED
            else "Not Approved" if application.status == Application.Status.NOT_APPROVED else "Decision",
        "done": decided, "current": False, "date": application.decided_at,
        "outcome": application.status if decided else "",
    })
    return steps


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
        "progress_steps": _progress_steps(application),
    })
