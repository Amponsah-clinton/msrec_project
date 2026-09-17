"""Shared write-side logic for the Committee pages (Committee Members,
Membership/Appointments, Terms & Expiry, Training, Conflict Records).

Both admin_dashboard and secretariat_dashboard manage the same governance
tables (GovernanceMember, CommitteeAppointment, TrainingRecord,
ConflictDeclaration) through near-identical forms -- this module is the one
place that logic lives, so the two dashboards can't drift the way the
Committee pages already had (training.html/conflict-records.html existed
as views with nowhere to render). Each dashboard's view stays responsible
for its own decorators, tab bookkeeping and template choice; it just calls
into here for the actual create/update work.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404

from pages import documents_storage
from pages import storage as pages_storage
from pages.models import CommitteeAppointment, ConflictDeclaration, GovernanceMember, TrainingRecord


def active_governance_members():
    return list(GovernanceMember.objects.filter(is_active=True).order_by("group", "display_order", "full_name"))


# ---------------------------------------------------------------------
# Committee Members (GovernanceMember)
# ---------------------------------------------------------------------

def _resolve_tag(request):
    """The Tag / discipline dropdown submits "__other__" plus a free-text
    "tag_other" field when someone's discipline isn't in the list --
    resolve that pair down to the single string GovernanceMember.tag
    stores."""
    tag = request.POST.get("tag", "").strip()
    if tag == "__other__":
        tag = request.POST.get("tag_other", "").strip()
    return tag


def handle_governance_add(request):
    full_name = request.POST.get("full_name", "").strip()
    title = request.POST.get("title", "").strip()
    role_title = request.POST.get("role_title", "").strip()
    tag = _resolve_tag(request)
    group = request.POST.get("group", "")
    display_order = request.POST.get("display_order", "").strip()

    if not full_name or not role_title:
        messages.error(request, "Name and role/title are required.")
        return
    if group not in {c for c, _ in GovernanceMember.Group.choices}:
        messages.error(request, "Choose a valid group (Board, Committee or Secretariat).")
        return

    member = GovernanceMember.objects.create(
        full_name=full_name, title=title, role_title=role_title, tag=tag, group=group,
        display_order=int(display_order) if display_order.isdigit() else 0,
    )

    photo = request.FILES.get("photo")
    if photo:
        object_path = pages_storage.upload_member_photo(photo, member_id=member.pk)
        if object_path:
            member.photo_path = object_path
            member.save(update_fields=["photo_path"])
        else:
            messages.warning(request, f"{full_name} was added, but the photo couldn't be uploaded right now.")

    messages.success(request, f"{full_name} added to {member.get_group_display()}.")


def handle_governance_edit(request, member):
    full_name = request.POST.get("full_name", "").strip()
    title = request.POST.get("title", "").strip()
    role_title = request.POST.get("role_title", "").strip()
    tag = _resolve_tag(request)
    group = request.POST.get("group", "")
    display_order = request.POST.get("display_order", "").strip()

    if not full_name or not role_title:
        messages.error(request, "Name and role/title are required.")
        return
    if group not in {c for c, _ in GovernanceMember.Group.choices}:
        messages.error(request, "Choose a valid group (Board, Committee or Secretariat).")
        return

    member.full_name = full_name
    member.title = title
    member.role_title = role_title
    member.tag = tag
    member.group = group
    member.display_order = int(display_order) if display_order.isdigit() else 0
    member.is_active = bool(request.POST.get("is_active"))

    photo = request.FILES.get("photo")
    if photo:
        old_path = member.photo_path
        object_path = pages_storage.upload_member_photo(photo, member_id=member.pk)
        if object_path:
            member.photo_path = object_path
            if old_path and old_path != object_path:
                pages_storage.delete_object(old_path)
        else:
            messages.warning(request, "The new photo couldn't be uploaded right now -- everything else was saved.")

    member.save()
    messages.success(request, f"{full_name} updated.")


def handle_governance_delete(request, member):
    if member.photo_path:
        pages_storage.delete_object(member.photo_path)
    name = member.full_name
    member.delete()
    messages.success(request, f"{name} removed from the Board & Committee page.")


# ---------------------------------------------------------------------
# Membership / Appointments + Terms & Expiry (CommitteeAppointment)
# ---------------------------------------------------------------------

def handle_appointment_add(request):
    member = get_object_or_404(GovernanceMember, pk=request.POST.get("member_id"))
    seat_title = request.POST.get("seat_title", "").strip()
    start_date = request.POST.get("start_date", "").strip()

    if not seat_title or not start_date:
        messages.error(request, "Seat / title and start date are required.")
        return

    appointment = CommitteeAppointment.objects.create(
        member=member,
        seat_title=seat_title,
        appointed_by=request.POST.get("appointed_by", "").strip(),
        start_date=start_date,
        end_date=request.POST.get("end_date") or None,
        status=request.POST.get("status") or CommitteeAppointment.Status.ACTIVE,
        notes=request.POST.get("notes", "").strip(),
    )

    letter = request.FILES.get("letter")
    if letter:
        object_path = documents_storage.upload_document(letter, folder=f"appointments/{appointment.pk}")
        if object_path:
            appointment.letter_path = object_path
            appointment.save(update_fields=["letter_path"])
        else:
            messages.warning(request, "The appointment was saved, but the letter couldn't be uploaded right now.")

    messages.success(request, f"Appointment recorded for {member.full_name}.")


def handle_appointment_edit(request, appointment):
    seat_title = request.POST.get("seat_title", "").strip()
    start_date = request.POST.get("start_date", "").strip()

    if not seat_title or not start_date:
        messages.error(request, "Seat / title and start date are required.")
        return

    appointment.seat_title = seat_title
    appointment.appointed_by = request.POST.get("appointed_by", "").strip()
    appointment.start_date = start_date
    appointment.end_date = request.POST.get("end_date") or None
    appointment.status = request.POST.get("status") or CommitteeAppointment.Status.ACTIVE
    appointment.notes = request.POST.get("notes", "").strip()

    letter = request.FILES.get("letter")
    if letter:
        old_path = appointment.letter_path
        object_path = documents_storage.upload_document(letter, folder=f"appointments/{appointment.pk}")
        if object_path:
            appointment.letter_path = object_path
            if old_path and old_path != object_path:
                documents_storage.delete_object(old_path)
        else:
            messages.warning(request, "The new letter couldn't be uploaded right now -- everything else was saved.")

    appointment.save()
    messages.success(request, "Appointment updated.")


def handle_appointment_delete(request, appointment):
    if appointment.letter_path:
        documents_storage.delete_object(appointment.letter_path)
    name = appointment.member.full_name
    appointment.delete()
    messages.success(request, f"Appointment record for {name} removed.")


# ---------------------------------------------------------------------
# Training (TrainingRecord)
# ---------------------------------------------------------------------

def handle_training_add(request):
    member = get_object_or_404(GovernanceMember, pk=request.POST.get("member_id"))
    course_title = request.POST.get("course_title", "").strip()

    if not course_title:
        messages.error(request, "Course / training title is required.")
        return

    record = TrainingRecord.objects.create(
        member=member,
        course_title=course_title,
        provider=request.POST.get("provider", "").strip(),
        completed_date=request.POST.get("completed_date") or None,
        expiry_date=request.POST.get("expiry_date") or None,
        notes=request.POST.get("notes", "").strip(),
    )

    certificate = request.FILES.get("certificate")
    if certificate:
        object_path = documents_storage.upload_document(certificate, folder=f"training/{record.pk}")
        if object_path:
            record.certificate_path = object_path
            record.save(update_fields=["certificate_path"])
        else:
            messages.warning(request, "The record was saved, but the certificate couldn't be uploaded right now.")

    messages.success(request, f"Training record added for {member.full_name}.")


def handle_training_edit(request, record):
    course_title = request.POST.get("course_title", "").strip()
    if not course_title:
        messages.error(request, "Course / training title is required.")
        return

    record.course_title = course_title
    record.provider = request.POST.get("provider", "").strip()
    record.completed_date = request.POST.get("completed_date") or None
    record.expiry_date = request.POST.get("expiry_date") or None
    record.notes = request.POST.get("notes", "").strip()

    certificate = request.FILES.get("certificate")
    if certificate:
        old_path = record.certificate_path
        object_path = documents_storage.upload_document(certificate, folder=f"training/{record.pk}")
        if object_path:
            record.certificate_path = object_path
            if old_path and old_path != object_path:
                documents_storage.delete_object(old_path)
        else:
            messages.warning(request, "The new certificate couldn't be uploaded right now -- everything else was saved.")

    record.save()
    messages.success(request, "Training record updated.")


def handle_training_delete(request, record):
    if record.certificate_path:
        documents_storage.delete_object(record.certificate_path)
    name = record.member.full_name
    record.delete()
    messages.success(request, f"Training record for {name} removed.")


# ---------------------------------------------------------------------
# Conflict Records (ConflictDeclaration)
# ---------------------------------------------------------------------

def handle_conflict_add(request):
    member = get_object_or_404(GovernanceMember, pk=request.POST.get("member_id"))
    description = request.POST.get("description", "").strip()

    if not description:
        messages.error(request, "A description of the conflict is required.")
        return

    ConflictDeclaration.objects.create(
        member=member,
        related_to=request.POST.get("related_to", "").strip(),
        date_declared=request.POST.get("date_declared") or None,
        description=description,
        status=request.POST.get("status") or ConflictDeclaration.Status.PENDING,
        recorded_by=request.user,
    )
    messages.success(request, f"Conflict of interest record added for {member.full_name}.")


def handle_conflict_edit(request, record):
    from django.utils import timezone

    description = request.POST.get("description", "").strip()
    if not description:
        messages.error(request, "A description of the conflict is required.")
        return

    new_status = request.POST.get("status") or ConflictDeclaration.Status.PENDING
    record.related_to = request.POST.get("related_to", "").strip()
    record.date_declared = request.POST.get("date_declared") or record.date_declared
    record.description = description
    record.resolution_notes = request.POST.get("resolution_notes", "").strip()

    if new_status in (ConflictDeclaration.Status.RESOLVED, ConflictDeclaration.Status.RECUSED) and record.status != new_status:
        record.resolved_at = timezone.now()
    record.status = new_status

    record.save()
    messages.success(request, "Conflict of interest record updated.")


def handle_conflict_delete(request, record):
    name = record.member.full_name
    record.delete()
    messages.success(request, f"Conflict of interest record for {name} removed.")
