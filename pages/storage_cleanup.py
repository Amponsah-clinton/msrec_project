"""Deletes a record's file(s) from Supabase Storage whenever the record is
deleted -- by any route (a dashboard view, Django admin, a bulk
queryset.delete(), or a CASCADE from a parent row such as a deleted
account, application, committee member or meeting).

Views that own a file already delete it explicitly; those calls stay, and
this is the safety net behind them for every path that doesn't (deleting a
draft application, cascading from a deleted user/member/meeting, the
Django admin, ...). delete_object() treats "already gone" as success, so
the two never conflict.

Runs on transaction.on_commit so a rolled-back delete never strips files
from a row that still exists. Best-effort like every Storage call here: a
failure is logged, never raised, and never blocks the deletion.
"""
import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _run_after_commit(func, *args):
    def _safe():
        try:
            func(*args)
        except Exception:
            logger.exception("Storage cleanup failed: %s%r", getattr(func, "__name__", func), args)

    transaction.on_commit(_safe)


def _paths_of(instance, *fields):
    return [getattr(instance, f) for f in fields if getattr(instance, f, "")]


def _delete_all(module_name, attr_paths):
    import importlib

    module = importlib.import_module(module_name)
    for path in attr_paths:
        module.delete_object(path)


def _register(model_path, module_name, *fields):
    """Wire post_delete for `model_path` ("app.Model"): each of `fields` is a
    CharField holding an object path in `module_name`'s bucket."""
    from django.apps import apps

    model = apps.get_model(model_path)

    def handler(sender, instance, **kwargs):
        paths = _paths_of(instance, *fields)
        if paths:
            _run_after_commit(_delete_all, module_name, paths)

    handler.__name__ = f"cleanup_{model.__name__}_files"
    post_delete.connect(handler, sender=model, weak=False, dispatch_uid=f"storage_cleanup_{model_path}")


def connect():
    _register("pages.GovernanceMember", "pages.storage", "photo_path")
    _register("pages.ClientLogo", "pages.storage", "image_path")
    _register("pages.Testimonial", "pages.storage", "image_path")
    _register("pages.MeetingDocument", "pages.documents_storage", "file_path")
    _register("pages.PolicyDocument", "pages.documents_storage", "file_path")
    _register("pages.CommitteeAppointment", "pages.documents_storage", "letter_path")
    _register("pages.TrainingRecord", "pages.documents_storage", "certificate_path")
    _register("pages.ResourceDocument", "pages.resources_storage", "file_path")
    _register("applicant_dashboard.TeamMember", "applicant_dashboard.team_storage", "photo_path")
    _register("pages.ApprovalDocumentTemplate", "pages.storage", "letter_header_path", "letter_footer_path", "letter_sign_path")

    from django.apps import apps

    site_settings = apps.get_model("pages.SiteSettings")

    @receiver(post_delete, sender=site_settings, weak=False, dispatch_uid="storage_cleanup_site_settings")
    def _site_settings_files(sender, instance, **kwargs):
        # Logo + sign-in image live in the "profile" bucket, hero in "hero".
        profile = _paths_of(instance, "logo_path", "auth_image_path", "chair_signature_path")
        hero = _paths_of(instance, "hero_image_path")
        if profile:
            _run_after_commit(_delete_all, "pages.storage", profile)
        if hero:
            _run_after_commit(_delete_all, "pages.hero_storage", hero)

    application = apps.get_model("applicant_dashboard.Application")

    @receiver(post_delete, sender=application, weak=False, dispatch_uid="storage_cleanup_application")
    def _application_files(sender, instance, **kwargs):
        paths = [d.get("path") for d in (instance.documents or []) if isinstance(d, dict) and d.get("path")]
        if paths:
            _run_after_commit(_delete_all, "applicant_dashboard.storage", paths)

    user = apps.get_model("accounts.User")

    @receiver(post_delete, sender=user, weak=False, dispatch_uid="storage_cleanup_user")
    def _user_files(sender, instance, **kwargs):
        photo = instance.profile_photo_path
        cvs = [
            (getattr(instance, field) or {}).get("cv_path")
            for field in ("reviewer_profile", "committee_profile", "applicant_profile")
        ]
        cvs = [p for p in cvs if p]
        if photo:
            from accounts.photos import delete_profile_photo

            _run_after_commit(delete_profile_photo, photo)
        if cvs:
            _run_after_commit(_delete_all, "accounts.storage", cvs)
