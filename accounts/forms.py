from django import forms
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.password_validation import validate_password

from .models import User


class SignupForm(forms.Form):
    """Validates the core fields from templates/pages/signup.html.

    Field names deliberately match the existing HTML `name="..."` attributes
    (camelCase) so the hand-built template needs no changes to post here.

    The page has ~60 inputs across three optional role-specific sections
    (applicant/reviewer/committee) that only get shown+required client-side
    once a role checkbox is ticked. Rather than encode every one of those
    as a Django field, the shared fields required for every signup are
    validated properly here; each role's extra answers are pulled straight
    off request.POST/FILES in the view and stored in the matching
    *_profile JSONField -- they're supplementary detail for a human
    reviewer, not data the app branches logic on.
    """

    role = forms.MultipleChoiceField(
        choices=[("applicant", "Applicant"), ("reviewer", "Reviewer"), ("committee", "Committee Member")],
        required=True,
        error_messages={"required": "Select at least one role."},
    )

    firstName = forms.CharField(max_length=150)
    middleName = forms.CharField(max_length=150, required=False)
    lastName = forms.CharField(max_length=150)
    title = forms.CharField(max_length=20, required=False)
    email = forms.EmailField()
    confirmEmail = forms.EmailField()
    phone = forms.CharField(max_length=40)
    countryResidence = forms.CharField(max_length=120)
    highestQualification = forms.CharField(max_length=150)
    password = forms.CharField(min_length=8)
    confirmPassword = forms.CharField(min_length=8)

    noInstitution = forms.BooleanField(required=False)
    institution = forms.CharField(max_length=200, required=False)
    department = forms.CharField(max_length=200, required=False)
    position = forms.CharField(max_length=150, required=False)
    institutionCountry = forms.CharField(max_length=120, required=False)
    institutionAddress = forms.CharField(max_length=255, required=False)
    profileUrl = forms.URLField(required=False)

    confirmAccurate = forms.BooleanField(error_messages={"required": "You must certify the information is accurate."})
    confirmTerms = forms.BooleanField(error_messages={"required": "You must agree to the Terms of Use and Privacy Notice."})
    confirmConfidentiality = forms.BooleanField(required=False)
    confirmCoi = forms.BooleanField(required=False)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        confirm_email = cleaned.get("confirmEmail")
        if email and confirm_email and email.strip().lower() != confirm_email.strip().lower():
            self.add_error("confirmEmail", "Email addresses do not match.")

        password = cleaned.get("password")
        confirm_password = cleaned.get("confirmPassword")
        if password and confirm_password and password != confirm_password:
            self.add_error("confirmPassword", "Passwords do not match.")

        
        if password:
            temp_user = User(
                email=email or "", first_name=cleaned.get("firstName", ""),
                last_name=cleaned.get("lastName", ""),
            )
            try:
                validate_password(password, user=temp_user)
            except DjangoValidationError as exc:
                for message in exc.messages:
                    self.add_error("password", message)

        roles = cleaned.get("role") or []
        if ("reviewer" in roles or "committee" in roles) and not (
            cleaned.get("confirmConfidentiality") and cleaned.get("confirmCoi")
        ):
            raise forms.ValidationError(
                "Reviewer and Committee roles require the confidentiality and conflict-of-interest declarations."
            )
        return cleaned


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        password = cleaned.get("password")
        if email and password:
            email = email.strip().lower()

          
            try:
                candidate = User.objects.get(email=email)
            except User.DoesNotExist:
                candidate = None

            if candidate is not None and candidate.check_password(password) and not candidate.is_active:
                raise forms.ValidationError(
                    "This account has been suspended. Contact an administrator to have it reactivated."
                )

            self.user_cache = authenticate(self.request, email=email, password=password)
            if self.user_cache is None:
                raise forms.ValidationError("Incorrect email or password.")
        return cleaned

    def get_user(self):
        return self.user_cache
