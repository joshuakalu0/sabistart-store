"""
dashboard/user_s/forms.py
==========================
Production-ready forms for the userauth dashboard.

Security rules:
  - Password fields use PasswordInput (never pre-fill)
  - TOTP secret is never shown or editable through forms
  - backup_codes_enc is write-only, never rendered
  - Soft-delete is a view action, not a form field
"""
from django import forms
from django.utils.text import slugify

from public.userauth.models import (
    TenantUser,
    StoreStaff,
    Role,
    Customer,
    CustomerGroup,
    CustomerNote,
    CustomerAddress,
)
from sabistart_store.ui.forms import TailwindFormMixin


# ─────────────────────────────────────────────────────────────
# TENANT USER FORMS
# ─────────────────────────────────────────────────────────────

class TenantUserForm(TailwindFormMixin, forms.ModelForm):
    """
    Used when creating a brand-new TenantUser from the admin dashboard.
    Password is set via set_password() in the view — never stored in plain text.
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        min_length=8,
        label="Initial Password",
        help_text="Must be at least 8 characters. Share these credentials with the user securely.",
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        label="Confirm Password",
    )

    class Meta:
        model = TenantUser
        fields = [
            "email", "first_name", "last_name", "phone",
            "user_type", "account_status", "is_verified",
            "gender", "date_of_birth", "locale", "timezone",
            "preferred_currency", "email_marketing_consent",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "account_status": forms.Select(),
            "user_type": forms.Select(),
            "gender": forms.Select(),
        }

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get("password")
        cpw = cleaned.get("confirm_password")
        if pw and cpw and pw != cpw:
            raise forms.ValidationError({"confirm_password": "Passwords do not match."})
        return cleaned


class TenantUserEditForm(TailwindFormMixin, forms.ModelForm):
    """
    Editing an existing TenantUser.
    Password fields are intentionally excluded — use the dedicated
    force_password_reset action or the user's own change-password flow.
    """
    class Meta:
        model = TenantUser
        fields = [
            "email", "first_name", "last_name", "phone",
            "user_type", "account_status", "is_verified",
            "force_password_reset",
            "gender", "date_of_birth", "locale", "timezone",
            "preferred_currency", "email_marketing_consent",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "account_status": forms.Select(),
            "user_type": forms.Select(),
            "gender": forms.Select(),
        }
        help_texts = {
            "force_password_reset": "When checked, user must change password on next login.",
            "is_verified": "Whether this user's email address has been verified.",
        }


# ─────────────────────────────────────────────────────────────
# STORE STAFF FORM
# ─────────────────────────────────────────────────────────────

class StoreStaffForm(TailwindFormMixin, forms.ModelForm):
    """
    Create or edit a StoreStaff record.
    - On create: the admin selects a TenantUser (STAFF type) and a Role.
    - On edit: role, status, 2FA enforcement, and IP restrictions can be changed.

    extra_permissions / removed_permissions are managed via the detail page
    permission matrix, not this form.
    """
    class Meta:
        model = StoreStaff
        fields = [
            "user", "role", "status", "require_2fa",
        ]
        widgets = {
            "user": forms.Select(),
            "role": forms.Select(),
            "status": forms.Select(),
        }
        help_texts = {
            "require_2fa": "When enabled, this staff member must have 2FA active before accessing the dashboard.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show STAFF-type users in the user selector
        self.fields["user"].queryset = TenantUser.objects.filter(
            user_type=TenantUser.UserType.STAFF
        ).order_by("first_name", "last_name")
        self.fields["user"].label_from_instance = lambda u: f"{u.get_full_name()} <{u.email}>"
        # Only offer active roles
        self.fields["role"].queryset = Role.objects.filter(is_active=True).order_by("sort_order")


# ─────────────────────────────────────────────────────────────
# ROLE FORM
# ─────────────────────────────────────────────────────────────

class RoleForm(TailwindFormMixin, forms.ModelForm):
    """
    Create or edit a Role.
    Permission selection is handled separately in the view via POST list
    (checkbox matrix), NOT via a ModelMultipleChoiceField, to allow
    the custom grouped-by-category display.
    """
    class Meta:
        model = Role
        fields = ["name", "description", "color", "sort_order"]
        widgets = {
            "color": forms.TextInput(attrs={"type": "color"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def save(self, commit=True):
        role = super().save(commit=False)
        # Auto-generate slug from name
        role.slug = slugify(role.name)
        role.is_system = False
        role.role_type = "custom"
        if commit:
            role.save()
        return role


# ─────────────────────────────────────────────────────────────
# CUSTOMER FORM
# ─────────────────────────────────────────────────────────────

class CustomerForm(TailwindFormMixin, forms.ModelForm):
    """
    Edit a Customer's commerce-specific profile.
    Identity fields (name, email, phone) live on TenantUser and are
    shown read-only on the detail page — not editable here to avoid
    divergence. Staff edit those via the TenantUser edit form.
    """
    tags_input = forms.CharField(
        required=False,
        label="Tags",
        widget=forms.TextInput(attrs={
            "placeholder": "Enter tags, press Enter or comma to add",
            "data-tags-input": "true",
        }),
        help_text="Comma-separated tags, e.g. vip, wholesale, b2b",
    )

    class Meta:
        model = Customer
        fields = [
            "status", "tier", "loyalty_points",
            "company", "is_b2b", "tax_exempt_status", "tax_id",
            "acquisition_source", "referral_code",
            "utm_source", "utm_medium", "utm_campaign",
            "staff_note",
        ]
        widgets = {
            "status": forms.Select(),
            "tier": forms.Select(),
            "tax_exempt_status": forms.Select(),
            "acquisition_source": forms.Select(),
            "staff_note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill the tags text field from the JSONField list
        if self.instance and self.instance.pk:
            self.fields["tags_input"].initial = ", ".join(self.instance.tags or [])

    def clean_tags_input(self):
        """Convert comma-separated string into a list for the JSONField."""
        raw = self.cleaned_data.get("tags_input", "")
        if not raw.strip():
            return []
        return [tag.strip() for tag in raw.replace(",", " ").split() if tag.strip()]

    def save(self, commit=True):
        customer = super().save(commit=False)
        customer.tags = self.cleaned_data.get("tags_input", [])
        if commit:
            customer.save()
        return customer


# ─────────────────────────────────────────────────────────────
# CUSTOMER GROUP FORM
# ─────────────────────────────────────────────────────────────

class CustomerGroupForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = CustomerGroup
        fields = ["name", "slug", "description", "group_type", "color", "sort_order"]
        widgets = {
            "group_type": forms.Select(),
            "color": forms.TextInput(attrs={"type": "color"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Auto-generate slug if empty
        self.fields["slug"].required = False
        self.fields["slug"].help_text = "Leave blank to auto-generate from name."

    def clean_slug(self):
        slug = self.cleaned_data.get("slug")
        if not slug:
            slug = slugify(self.cleaned_data.get("name", ""))
        return slug


# ─────────────────────────────────────────────────────────────
# CUSTOMER NOTE FORM
# ─────────────────────────────────────────────────────────────

class CustomerNoteForm(TailwindFormMixin, forms.ModelForm):
    """
    Append-only note form. written_by and written_by_name
    are set from the view (request.user).
    """
    class Meta:
        model = CustomerNote
        fields = ["note_type", "content", "is_pinned"]
        widgets = {
            "note_type": forms.Select(),
            "content": forms.Textarea(attrs={"rows": 4, "placeholder": "Write a note about this customer..."}),
        }


# ─────────────────────────────────────────────────────────────
# CUSTOMER ADDRESS FORM
# ─────────────────────────────────────────────────────────────

class CustomerAddressForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = CustomerAddress
        fields = [
            "address_type",
            "first_name", "last_name", "company",
            "address1", "address2",
            "city", "state", "postal_code", "country_code",
            "phone",
            "is_default_shipping", "is_default_billing",
        ]
        widgets = {
            "address_type": forms.Select(),
        }
