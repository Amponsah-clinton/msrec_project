from accounts.models import User

from .models import InstitutionSecretary


def secretary_flag(request):
    """`is_institution_secretary` on every page, so each dashboard sidebar can
    show the merged Institutional Secretary section for an appointed member
    (or a from-scratch secretary). One indexed lookup per request."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {}
    is_sec = (
        user.role == User.Role.INSTITUTION_SECRETARY
        or InstitutionSecretary.objects.filter(user=user).exists()
    )
    return {"is_institution_secretary": is_sec}
