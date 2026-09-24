from django.apps import AppConfig


class PagesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'pages'

    def ready(self):
        from . import storage_cleanup

        storage_cleanup.connect()

        from django.db.models.signals import post_save

        from . import maintenance
        from .models import SiteSettings

        post_save.connect(maintenance.clear_cache, sender=SiteSettings, weak=False,
                          dispatch_uid="maintenance_clear_cache")
