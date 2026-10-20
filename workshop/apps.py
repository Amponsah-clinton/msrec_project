from django.apps import AppConfig


class WorkshopConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "workshop"

    def ready(self):
        # Registers the post_save that keeps the contact list in step.
        from . import contacts  # noqa: F401
