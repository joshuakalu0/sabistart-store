"""
public/userauth/forms.py
=======================
Forms for tenant-level authentication.

These forms handle:
- Tenant user registration
- Tenant user login
"""

from django import forms
from django.core.validators import MinLengthValidator
from django.core.exceptions import ValidationError

from public.userauth.models.tenant_user import TenantUser


class TenantRegistrationForm(forms.ModelForm):
    """
    Registration form for tenant users (customers in a store).

    This form is used when customers create accounts in a tenant store.
    The form is schema-aware and creates users in the current tenant schema.
    """

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Create a password',
        }),
        validators=[MinLengthValidator(8)],
    )
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password',
        }),
    )
    agree_terms = forms.BooleanField(
        label="I agree to the Terms of Service and Privacy Policy",
        required=True,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        }),
    )

    class Meta:
        model = TenantUser
        fields = ['email', 'first_name', 'last_name', 'phone']
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'your@email.com',
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'First name',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Last name',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+2348012345678',
            }),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and TenantUser.objects.filter(email__iexact=email).exists():
            raise ValidationError(
                "An account with this email already exists in this store.",
                code='email_exists',
            )
        return email.lower()

    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError("The two password fields didn't match.")
        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.user_type = TenantUser.UserType.CUSTOMER
        user.account_status = TenantUser.AccountStatus.ACTIVE
        user.is_verified = False  # Require email verification
        if commit:
            user.save()
        return user


class TenantLoginForm(forms.Form):
    """
    Login form for tenant users.
    """

    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'your@email.com',
            'autofocus': True,
        }),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your password',
        }),
    )
    remember_me = forms.BooleanField(
        label="Remember me",
        required=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input',
        }),
    )
