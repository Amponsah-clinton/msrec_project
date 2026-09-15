"""Who counts as "the Secretariat" on the staff side of a support
conversation. Deliberately a role check, not a fixed participant list --
anyone currently an admin/secretariat can open and answer any applicant's
conversation, so the applicant is never stuck waiting on one specific
person's account.
"""


def is_staff_side(user):
    from accounts.models import User
    return user.is_authenticated and (
        user.is_superuser or user.role in (User.Role.ADMIN, User.Role.SECRETARIAT)
    )


def staff_role_label(user):
    """Which of the two staff roles sent a message, so an applicant
    talking to "MSREC" can still see whether Admin or the Secretariat
    replied -- '' for the applicant's own messages (no label needed for
    your own side of the thread)."""
    from accounts.models import User
    if user.is_superuser or user.role == User.Role.ADMIN:
        return "Admin"
    if user.role == User.Role.SECRETARIAT:
        return "Secretariat"
    return ""
