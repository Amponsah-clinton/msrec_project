from . import storage as signup_storage


def profile_avatar(request):
    """Makes `profile_photo_url` available in every template.

    The dashboards' topbar profile dropdown (avatar + name + email) used
    to be hardcoded demo data ("Ama Owusu") copy-pasted into every single
    dashboard template. That's now driven by request.user directly in
    each template (full_name, email, initials); the one piece that can't
    be a plain template variable is the photo, since it's a path into
    Supabase Storage that needs resolving to an actual URL -- computing
    that per-page here, once, keeps every dashboard template from having
    to know anything about Supabase Storage.

    Three possible buckets, told apart by the path's prefix:
      - "reviewers/<id>/..." -> the public "profile" bucket (photos
        changed from a reviewer's Profile & Expertise page --
        reviewer_dashboard/storage.py, a plain public URL, never expires).
      - "avatars/<id>/..."  -> the public "application" bucket (photos
        changed from Profile & Security -- applicant_dashboard/storage.py,
        a plain public URL, never expires).
      - anything else       -> the legacy path shape from the private
        "signup" bucket (the photo attached at signup -- this module's
        own storage.py, needs a freshly-signed URL each time).
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated or not user.profile_photo_path:
        return {"profile_photo_url": None}

    path = user.profile_photo_path
    if path.startswith("reviewers/"):
        from reviewer_dashboard import storage as reviewer_storage
        return {"profile_photo_url": reviewer_storage.public_url(path)}
    if path.startswith("avatars/"):
        from applicant_dashboard import storage as application_storage
        return {"profile_photo_url": application_storage.public_url(path)}
    return {"profile_photo_url": signup_storage.create_signed_url(path)}
