"""Deleting a user's profile photo from whichever bucket it lives in.

`User.profile_photo_path` can point into three different buckets depending
on when the photo was last set (see admin_dashboard.views._cleanup_user_
storage's history): a "reviewers/<id>/..." path is the "profile" bucket
(reviewer Profile & Expertise), "avatars/<id>/..." is the "application"
bucket (applicant / admin Profile & Security), and anything else is the
private "signup" bucket photo uploaded at signup. Best-effort, like every
other Storage call here -- never raises.
"""


def delete_profile_photo(object_path):
    if not object_path:
        return False
    from applicant_dashboard import storage as application_storage
    from reviewer_dashboard import storage as reviewer_storage

    from . import storage as signup_storage

    if object_path.startswith("reviewers/"):
        return reviewer_storage.delete_object(object_path)
    if object_path.startswith("avatars/"):
        return application_storage.delete_object(object_path)
    return signup_storage.delete_object(object_path)
