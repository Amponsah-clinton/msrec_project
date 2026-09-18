from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("<str:audience>/mark-all-read/", views.mark_all_read, name="mark_all_read"),
    path("<str:audience>/<int:pk>/open/", views.open_notification, name="open"),
    path("<str:audience>/feed/", views.feed, name="feed"),
    path("<str:audience>/", views.list_page, name="list"),
]
