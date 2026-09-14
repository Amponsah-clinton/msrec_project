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
