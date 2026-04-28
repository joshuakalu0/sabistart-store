from django import forms

from sabistart_store.ui.forms import TailwindFormMixin
from system.feature_marketplace.models import BillingCycle


class MarketplaceCheckoutForm(TailwindFormMixin, forms.Form):
    feature_code = forms.CharField(max_length=100, required=False, widget=forms.HiddenInput)
    bundle_slug = forms.CharField(max_length=100, required=False, widget=forms.HiddenInput)
    currency = forms.CharField(max_length=3, initial="NGN")
    billing_cycle = forms.ChoiceField(choices=BillingCycle.choices, initial=BillingCycle.MONTHLY)
    quantity = forms.IntegerField(min_value=1, initial=1)
    coupon_code = forms.CharField(max_length=50, required=False)
    gateway_provider = forms.ChoiceField(choices=(), required=False)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("feature_code") and not cleaned.get("bundle_slug"):
            raise forms.ValidationError("Choose a feature or bundle to continue.")
        return cleaned
