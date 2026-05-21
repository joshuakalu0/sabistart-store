from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from public.userauth.models import CustomerAddress, TenantUser


class GuestCheckoutForm(forms.Form):
    email = forms.EmailField(label="Email address")


class CheckoutContactForm(forms.Form):
    email = forms.EmailField(label="Email address", required=False)
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    phone = forms.CharField(max_length=30, required=False)
    company = forms.CharField(max_length=200, required=False)
    address1 = forms.CharField(max_length=300, label="Address line 1")
    address2 = forms.CharField(max_length=300, required=False, label="Address line 2")
    city = forms.CharField(max_length=100)
    state = forms.CharField(max_length=100, required=False)
    postal_code = forms.CharField(max_length=20, required=False)
    country_code = forms.CharField(max_length=2, initial="NG")
    delivery_instructions = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    marketing_opt_in = forms.BooleanField(required=False)


class ShippingMethodForm(forms.Form):
    shipping_method = forms.ChoiceField(choices=())

    def __init__(self, *args, methods=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["shipping_method"].choices = [
            (method["code"], f'{method["label"]} ({method["amount_display"]})')
            for method in (methods or [])
        ]


class PaymentMethodForm(forms.Form):
    payment_method = forms.ChoiceField(choices=())
    terms_accepted = forms.BooleanField(required=True)

    def __init__(self, *args, methods=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].choices = [
            (method["code"], method["label"]) for method in (methods or [])
        ]


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label="Email address")


class PasswordResetConfirmForm(forms.Form):
    new_password1 = forms.CharField(widget=forms.PasswordInput())
    new_password2 = forms.CharField(widget=forms.PasswordInput())

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("new_password1") != cleaned_data.get("new_password2"):
            raise ValidationError("The new passwords do not match.")
        return cleaned_data


class ProfileForm(forms.ModelForm):
    class Meta:
        model = TenantUser
        fields = ["first_name", "last_name", "phone", "locale", "preferred_currency"]


class SecurityForm(forms.Form):
    current_password = forms.CharField(widget=forms.PasswordInput())
    new_password1 = forms.CharField(widget=forms.PasswordInput())
    new_password2 = forms.CharField(widget=forms.PasswordInput())

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("new_password1") != cleaned_data.get("new_password2"):
            raise ValidationError("The new passwords do not match.")
        return cleaned_data


class AddressForm(forms.ModelForm):
    class Meta:
        model = CustomerAddress
        fields = [
            "address_type",
            "first_name",
            "last_name",
            "company",
            "address1",
            "address2",
            "city",
            "state",
            "postal_code",
            "country_code",
            "phone",
            "is_default_shipping",
            "is_default_billing",
        ]


class ContactForm(forms.Form):
    name = forms.CharField(max_length=150)
    email = forms.EmailField()
    subject = forms.CharField(max_length=200)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}))


class NewsletterSignupForm(forms.Form):
    email = forms.EmailField(label="Email address")


class ReviewSubmissionForm(forms.Form):
    title = forms.CharField(max_length=160, required=False)
    rating = forms.IntegerField(min_value=1, max_value=5)
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 6}))


class ReferralInviteForm(forms.Form):
    name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(label="Friend's email")
    note = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}), required=False)


class B2BLeadForm(forms.Form):
    company_name = forms.CharField(max_length=200)
    contact_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone = forms.CharField(max_length=30, required=False)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), required=False)


class RegionSelectionForm(forms.Form):
    region = forms.CharField(max_length=10)
    language = forms.CharField(max_length=10, required=False)
