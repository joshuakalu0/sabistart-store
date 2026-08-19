"""
system/account/forms.py
=======================
Forms for platform-level authentication.

These forms handle:
- Platform user registration (with tenant creation)
- Platform user login
"""

from django import forms
from django.core.validators import MinLengthValidator
from django.core.exceptions import ValidationError

from sabistart.ui.forms import TailwindFormMixin
from system.account.models import PlatformUser
from system.feature_marketplace.models import FeatureBundle


class PlatformRegistrationForm(TailwindFormMixin, forms.ModelForm):
    """
    Registration form for platform users.

    Includes tenant name/domain validation:
    - Tenant name must be unique
    - Domain must be valid and available
    """

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Create a password',
        }),
        validators=[MinLengthValidator(8)],
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Confirm your password',
        }),
    )
    tenant_name = forms.CharField(
        label="Store Name",
        max_length=100,
        help_text="Your online store name (e.g., 'My Awesome Shop')",
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter your store name',
        }),
    )
    tenant_subdomain = forms.SlugField(
        label="Store Subdomain",
        max_length=63,
        help_text="Your store URL: subdomain.yourplatform.com",
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g., myshop',
        }),
    )
    agree_terms = forms.BooleanField(
        label="I agree to the Terms of Service and Privacy Policy",
        required=True,
        widget=forms.CheckboxInput(),
    )

    class Meta:
        model = PlatformUser
        fields = ['email', 'first_name', 'last_name']
        widgets = {
            'email': forms.EmailInput(attrs={
                'placeholder': 'your@email.com',
            }),
            'first_name': forms.TextInput(attrs={
                'placeholder': 'First name',
            }),
            'last_name': forms.TextInput(attrs={
                'placeholder': 'Last name',
            }),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if PlatformUser.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "An account with this email already exists.",
                code='email_exists',
            )
        return email.lower()

    def clean_tenant_subdomain(self):
        subdomain = self.cleaned_data.get('tenant_subdomain')
        if subdomain:
            subdomain = subdomain.lower()
            # Check reserved subdomains
            reserved = {'www', 'admin', 'mail', 'ftp', 'localhost', 'api',
                        'blog', 'shop', 'store', 'platform', 'public', 'private'}
            if subdomain in reserved:
                raise ValidationError(
                    f"'{subdomain}' is a reserved subdomain. Please choose another.",
                    code='reserved_subdomain',
                )
            # Check valid characters
            import re
            if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', subdomain):
                raise ValidationError(
                    "Subdomain can only contain letters, numbers, and hyphens. "
                    "It must start and end with a letter or number.",
                    code='invalid_subdomain',
                )
        return subdomain

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError("The two password fields didn't match.")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.account_status = PlatformUser.AccountStatus.ACTIVE
        user.is_verified = False  # Require email verification
        if commit:
            user.save()
        return user


class PlatformLoginForm(TailwindFormMixin, forms.Form):
    """
    Login form for platform users.
    """

    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            'placeholder': 'your@email.com',
            'autofocus': True,
        }),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Your password',
        }),
    )
    remember_me = forms.BooleanField(
        label="Remember me",
        required=False,
        widget=forms.CheckboxInput(),
    )


class PlatformPasswordResetRequestForm(TailwindFormMixin, forms.Form):
    """
    Form to request a password reset email.
    """

    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            'placeholder': 'your@email.com',
        }),
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not PlatformUser.objects.filter(email__iexact=email).exists():
            # Don't reveal whether the email exists
            pass
        return email.lower()


class PlatformPasswordResetConfirmForm(TailwindFormMixin, forms.Form):
    """
    Form to set a new password after clicking reset link.
    """

    password1 = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Create a new password',
        }),
        validators=[MinLengthValidator(8)],
    )
    password2 = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Confirm your new password',
        }),
    )

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError("The two password fields didn't match.")
        return password2


class OnboardingAccountForm(TailwindFormMixin, forms.Form):
    email = forms.EmailField(label="Work Email")
    first_name = forms.CharField(label="First Name", max_length=100)
    last_name = forms.CharField(label="Last Name", max_length=100)
    business_name = forms.CharField(label="Business Name", max_length=120)
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, validators=[MinLengthValidator(8)])
    password2 = forms.CharField(label="Confirm Password", widget=forms.PasswordInput)
    agree_terms = forms.BooleanField(label="I agree to the Terms of Service and Privacy Policy")

    def __init__(self, *args, existing_email: str = "", **kwargs):
        self.existing_email = (existing_email or "").strip().lower()
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").lower()
        if email and email == self.existing_email:
            return email
        if PlatformUser.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError("The two password fields didn't match.")
        return password2


class OnboardingPlanForm(TailwindFormMixin, forms.Form):
    bundle_slug = forms.ChoiceField(label="Store Plan", choices=())
    addon_feature_codes = forms.MultipleChoiceField(
        label="Optional Add-ons",
        required=False,
        choices=(),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, bundle_choices=None, addon_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bundle_slug"].choices = bundle_choices or [("", "Choose a starter plan")]
        self.fields["addon_feature_codes"].choices = addon_choices or []

    def clean_bundle_slug(self):
        slug = self.cleaned_data.get("bundle_slug")
        if slug and not FeatureBundle.objects.filter(slug=slug, is_active=True).exists():
            raise ValidationError("The selected plan is no longer available.")
        return slug


class OnboardingCheckoutForm(TailwindFormMixin, forms.Form):
    gateway_provider = forms.ChoiceField(label="Billing Gateway", choices=())

    def __init__(self, *args, gateway_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gateway_provider"].choices = gateway_choices or []

    def clean_gateway_provider(self):
        provider = (self.cleaned_data.get("gateway_provider") or "").strip()
        if not provider:
            raise ValidationError("Choose a billing gateway to continue.")
        valid_providers = {choice[0] for choice in self.fields["gateway_provider"].choices}
        if provider not in valid_providers:
            raise ValidationError("The selected billing gateway is no longer available.")
        return provider


class OnboardingSubdomainForm(TailwindFormMixin, forms.Form):
    desired_subdomain = forms.SlugField(
        label="Store Subdomain",
        max_length=63,
        help_text="Your store URL will use this prefix.",
    )

    def clean_desired_subdomain(self):
        subdomain = (self.cleaned_data.get("desired_subdomain") or "").lower()
        reserved = {'www', 'admin', 'mail', 'ftp', 'localhost', 'api', 'blog', 'shop', 'store', 'platform', 'public', 'private'}
        if subdomain in reserved:
            raise ValidationError(f"'{subdomain}' is a reserved subdomain.")
        import re
        if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', subdomain):
            raise ValidationError("Subdomain can only contain letters, numbers, and hyphens.")
        return subdomain
