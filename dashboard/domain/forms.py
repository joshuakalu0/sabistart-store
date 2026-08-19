from __future__ import annotations

import re

from django import forms
from django.core.exceptions import ValidationError

from dashboard.domain.commerce_models import (
    DomainProviderCredential,
    DomainPurchaseOrder,
    ManagedDomainDNSRecord,
    TenantDomainContact,
    TldCatalogEntry,
)
from dashboard.domain.domain_utils import normalize_domain_name
from dashboard.domain.models import CustomDomain
from sabistart.ui.forms import TailwindFormMixin


TAILWIND_TEXT = "block w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
TAILWIND_CHECK = "h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary/20"
TAILWIND_SELECT = TAILWIND_TEXT
TAILWIND_TEXTAREA = "block min-h-[120px] w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"


class AddDomainForm(TailwindFormMixin, forms.Form):
    domain = forms.CharField(
        max_length=253,
        widget=forms.TextInput(
            attrs={
                "class": TAILWIND_TEXT,
                "placeholder": "example.com or shop.example.com",
                "autocomplete": "off",
            }
        ),
        help_text="Enter a domain you already own. Use the buy flow below for new registrations.",
    )

    def clean_domain(self):
        domain = normalize_domain_name(self.cleaned_data.get("domain", ""))
        domain_pattern = r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9][a-z0-9-]{0,61}[a-z0-9]$"
        if not re.match(domain_pattern, domain):
            raise ValidationError("Please enter a valid domain name.")
        if CustomDomain.objects.filter(domain=domain).exclude(status=CustomDomain.Status.REMOVED).exists():
            raise ValidationError("This domain is already connected in our system.")
        blocked_domains = ["sabistart.com", "localhost", "127.0.0.1"]
        if any(blocked in domain for blocked in blocked_domains):
            raise ValidationError("You cannot use this domain.")
        return domain


class DomainSearchForm(TailwindFormMixin, forms.Form):
    query = forms.CharField(
        max_length=253,
        widget=forms.TextInput(
            attrs={
                "class": TAILWIND_TEXT,
                "placeholder": "Search brandname.com or just brandname",
                "autocomplete": "off",
            }
        ),
        help_text="Search exact domains or enter a brand name to generate TLD suggestions.",
    )

    def clean_query(self):
        value = normalize_domain_name(self.cleaned_data.get("query", ""))
        if not value:
            raise ValidationError("Enter a domain keyword to search.")
        if value.startswith("."):
            raise ValidationError("Enter the domain without a leading dot.")
        return value


class DomainSettingsForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = CustomDomain
        fields = ["notes", "is_primary"]
        widgets = {
            "notes": forms.Textarea(attrs={"class": TAILWIND_TEXTAREA, "rows": 3, "placeholder": "Internal notes"}),
            "is_primary": forms.CheckboxInput(attrs={"class": TAILWIND_CHECK}),
        }


class TenantDomainContactForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = TenantDomainContact
        fields = [
            "label",
            "first_name",
            "last_name",
            "organization",
            "email",
            "phone",
            "address1",
            "address2",
            "city",
            "state_province",
            "postal_code",
            "country_code",
            "is_default",
        ]
        widgets = {
            "label": forms.TextInput(attrs={"class": TAILWIND_TEXT, "placeholder": "Default registrant"}),
            "first_name": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "last_name": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "organization": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "email": forms.EmailInput(attrs={"class": TAILWIND_TEXT}),
            "phone": forms.TextInput(attrs={"class": TAILWIND_TEXT, "placeholder": "+2348012345678"}),
            "address1": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "address2": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "city": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "state_province": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "postal_code": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "country_code": forms.TextInput(attrs={"class": TAILWIND_TEXT, "placeholder": "NG"}),
            "is_default": forms.CheckboxInput(attrs={"class": TAILWIND_CHECK}),
        }


class DomainCheckoutForm(TailwindFormMixin, forms.Form):
    domain_name = forms.CharField(widget=forms.HiddenInput())
    years = forms.TypedChoiceField(
        coerce=int,
        choices=[(i, f"{i} year{'s' if i > 1 else ''}") for i in range(1, 11)],
        widget=forms.Select(attrs={"class": TAILWIND_SELECT}),
        initial=1,
    )
    contact = forms.ModelChoiceField(
        queryset=TenantDomainContact.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": TAILWIND_SELECT}),
        empty_label="Create a new registrant contact",
    )
    auto_renew = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput(attrs={"class": TAILWIND_CHECK}))
    privacy_enabled = forms.BooleanField(required=False, initial=False, widget=forms.CheckboxInput(attrs={"class": TAILWIND_CHECK}))
    nameserver_mode = forms.ChoiceField(
        choices=DomainPurchaseOrder.NameserverMode.choices,
        initial=DomainPurchaseOrder.NameserverMode.PROVIDER_DEFAULT,
        widget=forms.Select(attrs={"class": TAILWIND_SELECT}),
    )
    custom_nameservers = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": TAILWIND_TEXTAREA,
                "rows": 3,
                "placeholder": "ns1.example.com\nns2.example.com",
            }
        ),
    )
    gateway_provider = forms.ChoiceField(
        required=False,
        choices=[("", "Select a payment gateway")],
        widget=forms.Select(attrs={"class": TAILWIND_SELECT}),
    )

    # Inline fallback contact fields
    first_name = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": TAILWIND_TEXT}))
    last_name = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": TAILWIND_TEXT}))
    organization = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": TAILWIND_TEXT}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": TAILWIND_TEXT}))
    phone = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": TAILWIND_TEXT}))
    address1 = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": TAILWIND_TEXT}))
    address2 = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": TAILWIND_TEXT}))
    city = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": TAILWIND_TEXT}))
    state_province = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": TAILWIND_TEXT}))
    postal_code = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": TAILWIND_TEXT}))
    country_code = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": TAILWIND_TEXT, "placeholder": "NG"}))
    save_contact_as_default = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput(attrs={"class": TAILWIND_CHECK}))

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.tenant = tenant
        if tenant is not None:
            self.fields["contact"].queryset = tenant.domain_contacts.order_by("-is_default", "first_name", "last_name")

    def clean_domain_name(self):
        return normalize_domain_name(self.cleaned_data.get("domain_name", ""))

    def clean_custom_nameservers(self):
        raw = (self.cleaned_data.get("custom_nameservers") or "").replace(",", "\n")
        values = [line.strip().lower() for line in raw.splitlines() if line.strip()]
        return values

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("nameserver_mode") == DomainPurchaseOrder.NameserverMode.CUSTOM and len(cleaned.get("custom_nameservers", [])) < 2:
            self.add_error("custom_nameservers", "Enter at least two nameservers for the custom mode.")
        if cleaned.get("contact") is None:
            required_fields = [
                "first_name",
                "last_name",
                "email",
                "phone",
                "address1",
                "city",
                "state_province",
                "postal_code",
                "country_code",
            ]
            missing = [field for field in required_fields if not cleaned.get(field)]
            if missing:
                raise ValidationError("Fill in the registrant contact details or choose a saved contact.")
        return cleaned


class ManagedDomainDNSRecordForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ManagedDomainDNSRecord
        fields = ["host", "record_type", "value", "ttl", "priority"]
        widgets = {
            "host": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "record_type": forms.Select(attrs={"class": TAILWIND_SELECT}),
            "value": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "ttl": forms.NumberInput(attrs={"class": TAILWIND_TEXT}),
            "priority": forms.NumberInput(attrs={"class": TAILWIND_TEXT}),
        }


class NameserverUpdateForm(TailwindFormMixin, forms.Form):
    nameservers = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": TAILWIND_TEXTAREA,
                "rows": 3,
                "placeholder": "ns1.example.com\nns2.example.com",
            }
        )
    )

    def clean_nameservers(self):
        values = [line.strip().lower() for line in (self.cleaned_data.get("nameservers") or "").replace(",", "\n").splitlines() if line.strip()]
        if len(values) < 2:
            raise ValidationError("Provide at least two nameservers.")
        return values


class DomainProviderCredentialForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = DomainProviderCredential
        fields = [
            "provider",
            "name",
            "api_user",
            "username",
            "api_key",
            "client_ip",
            "environment",
            "request_timeout_seconds",
            "is_active",
            "is_default",
        ]
        widgets = {
            "provider": forms.Select(attrs={"class": TAILWIND_SELECT}),
            "name": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "api_user": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "username": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "api_key": forms.PasswordInput(attrs={"class": TAILWIND_TEXT, "render_value": True}),
            "client_ip": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "environment": forms.Select(attrs={"class": TAILWIND_SELECT}),
            "request_timeout_seconds": forms.NumberInput(attrs={"class": TAILWIND_TEXT}),
            "is_active": forms.CheckboxInput(attrs={"class": TAILWIND_CHECK}),
            "is_default": forms.CheckboxInput(attrs={"class": TAILWIND_CHECK}),
        }


class TldCatalogEntryForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = TldCatalogEntry
        fields = [
            "provider",
            "tld",
            "currency",
            "registration_price",
            "renewal_price",
            "transfer_price",
            "platform_markup_amount",
            "platform_markup_percent",
            "minimum_years",
            "maximum_years",
            "is_enabled",
            "supports_registration",
            "supports_renewal",
            "supports_dns",
            "sort_order",
        ]
        widgets = {
            "provider": forms.Select(attrs={"class": TAILWIND_SELECT}),
            "tld": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "currency": forms.TextInput(attrs={"class": TAILWIND_TEXT}),
            "registration_price": forms.NumberInput(attrs={"class": TAILWIND_TEXT, "step": "0.01"}),
            "renewal_price": forms.NumberInput(attrs={"class": TAILWIND_TEXT, "step": "0.01"}),
            "transfer_price": forms.NumberInput(attrs={"class": TAILWIND_TEXT, "step": "0.01"}),
            "platform_markup_amount": forms.NumberInput(attrs={"class": TAILWIND_TEXT, "step": "0.01"}),
            "platform_markup_percent": forms.NumberInput(attrs={"class": TAILWIND_TEXT, "step": "0.01"}),
            "minimum_years": forms.NumberInput(attrs={"class": TAILWIND_TEXT}),
            "maximum_years": forms.NumberInput(attrs={"class": TAILWIND_TEXT}),
            "is_enabled": forms.CheckboxInput(attrs={"class": TAILWIND_CHECK}),
            "supports_registration": forms.CheckboxInput(attrs={"class": TAILWIND_CHECK}),
            "supports_renewal": forms.CheckboxInput(attrs={"class": TAILWIND_CHECK}),
            "supports_dns": forms.CheckboxInput(attrs={"class": TAILWIND_CHECK}),
            "sort_order": forms.NumberInput(attrs={"class": TAILWIND_TEXT}),
        }


class DomainOrderFilterForm(TailwindFormMixin, forms.Form):
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses"), *DomainPurchaseOrder.Status.choices],
        widget=forms.Select(attrs={"class": TAILWIND_SELECT}),
    )
    order_type = forms.ChoiceField(
        required=False,
        choices=[("", "All order types"), *DomainPurchaseOrder.OrderType.choices],
        widget=forms.Select(attrs={"class": TAILWIND_SELECT}),
    )
