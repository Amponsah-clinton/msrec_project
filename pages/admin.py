from django import forms
from django.contrib import admin

from . import documents_storage
from .models import CommitteeMeeting, Inquiry, MeetingDocument, PolicyDocument


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "reason", "status", "created_at", "replied_at")
    list_filter = ("status", "reason")
    search_fields = ("name", "email", "message")
    readonly_fields = ("created_at",)


class _DocumentUploadForm(forms.ModelForm):
    """Shared by MeetingDocumentAdmin/PolicyDocumentAdmin: an `upload`
    field that isn't a real model field -- save_model() below reads it,
    pushes the file to Supabase Storage (pages/documents_storage.py), and
    writes the resulting object path into file_path itself. Keeps the
    model's own file_path/file_size read-only in the admin (they're
    Storage-derived, not something to hand-edit) while still giving the
    Secretariat a normal file picker to work with.
    """
    upload = forms.FileField(required=False, help_text="Upload a PDF/DOCX to replace or attach the file.")


class MeetingDocumentInline(admin.TabularInline):
    model = MeetingDocument
    form = _DocumentUploadForm
    extra = 1
    fields = ("doc_type", "title", "upload", "file_path")
    readonly_fields = ("file_path",)

    def save_formset(self, request, form, formset, change):
        # Iterate formset.forms directly (each paired with its own
        # cleaned_data) rather than the list save(commit=False) returns --
        # unsaved model instances all compare equal (same class, pk=None),
        # so matching them back to a form by list.index() picks the first
        # form for every row once there's more than one new, unsaved one.
        formset.save(commit=False)
        for inline_form in formset.forms:
            if not inline_form.cleaned_data or inline_form.cleaned_data.get("DELETE"):
                continue
            instance = inline_form.instance
            instance.meeting = form.instance
            upload = inline_form.cleaned_data.get("upload")
            if upload:
                old_path = instance.file_path
                object_path = documents_storage.upload_document(upload, folder=f"meetings/{form.instance.pk}")
                if object_path:
                    instance.file_path = object_path
                    instance.file_size = upload.size
                    if old_path and old_path != object_path:
                        documents_storage.delete_object(old_path)
            instance.save()
        for obj in formset.deleted_objects:
            if obj.file_path:
                documents_storage.delete_object(obj.file_path)
            obj.delete()
        formset.save_m2m()


@admin.register(CommitteeMeeting)
class CommitteeMeetingAdmin(admin.ModelAdmin):
    list_display = ("title", "scheduled_at", "location", "is_past")
    list_filter = ("scheduled_at",)
    search_fields = ("title", "location")
    inlines = [MeetingDocumentInline]


@admin.register(PolicyDocument)
class PolicyDocumentAdmin(admin.ModelAdmin):
    form = _DocumentUploadForm
    list_display = ("title", "category", "version", "display_order", "updated_at")
    list_filter = ("category",)
    search_fields = ("title", "description")
    readonly_fields = ("file_path", "file_size")

    def save_model(self, request, obj, form, change):
        upload = form.cleaned_data.get("upload")
        if upload:
            old_path = obj.file_path
            super().save_model(request, obj, form, change)  # ensures obj.pk exists
            object_path = documents_storage.upload_document(upload, folder=f"policies/{obj.pk}")
            if object_path:
                obj.file_path = object_path
                obj.file_size = upload.size
                if old_path and old_path != object_path:
                    documents_storage.delete_object(old_path)
                obj.save(update_fields=["file_path", "file_size"])
        else:
            super().save_model(request, obj, form, change)
