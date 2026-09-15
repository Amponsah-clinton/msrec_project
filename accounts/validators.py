import re

from django.core.exceptions import ValidationError


class StrongPasswordValidator:
    """Requires at least one uppercase letter, one lowercase letter, one
    digit, and one symbol.

    Django's built-in validators (configured in AUTH_PASSWORD_VALIDATORS)
    check length, similarity to the user's own info, membership in a
    common-password list, and "not all digits" -- none of them check
    character variety, so "aaaaaaaa" or "password1" would otherwise sail
    straight through. Registered globally, so it applies everywhere
    Django's validate_password() is called: signup (accounts/forms.py)
    and changing password from Profile & Security
    (applicant_dashboard/views.py's _handle_update_profile).
    """

    def validate(self, password, user=None):
        missing = []
        if not re.search(r"[A-Z]", password):
            missing.append("an uppercase letter")
        if not re.search(r"[a-z]", password):
            missing.append("a lowercase letter")
        if not re.search(r"[0-9]", password):
            missing.append("a number")
        if not re.search(r"[^A-Za-z0-9]", password):
            missing.append("a symbol (e.g. ! @ # $)")
        if missing:
            raise ValidationError(
                "Password must include " + ", ".join(missing) + ".",
                code="password_missing_character_types",
            )

    def get_help_text(self):
        return "Must include an uppercase letter, a lowercase letter, a number, and a symbol."
