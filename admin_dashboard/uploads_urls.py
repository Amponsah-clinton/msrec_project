"""The public side of a shared upload: /u/<token>/.

Short on purpose -- these links get pasted into emails and WhatsApp, and
a long path is one more thing that wraps badly.
"""
from django.urls import path

from . import uploads_views

app_name = "uploads"

urlpatterns = [
    path("<str:token>/", uploads_views.share, name="share"),
    path("<str:token>/file/", uploads_views.file, name="file"),
]
