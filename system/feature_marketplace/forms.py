from django import forms

from sabistart.ui.forms import TailwindFormMixin
from system.feature_marketplace.models import (
    BillingCycle,
    BundleItem,
    Coupon,
    DiscountCampaign,
    FeatureBundle,
    FeatureCategory,
    FeatureDefinition,
    FeaturePrice,
    TenantFeatureOverride,
)


class FeatureCategoryForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = FeatureCategory
        fields = ["name", "slug", "description", "icon", "display_order", "is_active"]


class FeatureDefinitionForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = FeatureDefinition
        fields = [
            "category",
            "name",
            "code",
            "short_description",
            "description",
            "feature_type",
            "default_boolean_value",
            "default_limit_value",
            "default_usage_value",
            "unit_label",
            "badge_label",
            "icon",
            "store_setting_key",
            "sidebar_key",
            "storefront_flag",
            "is_active",
            "is_purchasable",
            "is_featured",
            "is_globally_enabled",
            "is_globally_disabled",
            "display_order",
            "metadata",
        ]


class FeaturePriceForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = FeaturePrice
        fields = [
            "feature",
            "currency",
            "billing_cycle",
            "amount",
            "credits_included",
            "limit_increment",
            "display_name",
            "is_active",
            "valid_from",
            "valid_until",
        ]
        widgets = {
            "valid_from": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "valid_until": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class FeatureBundleForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = FeatureBundle
        fields = [
            "name",
            "slug",
            "description",
            "tagline",
            "price",
            "currency",
            "billing_cycle",
            "discount_percentage",
            "icon",
            "is_active",
            "is_featured",
            "display_order",
            "valid_from",
            "valid_until",
        ]
        widgets = {
            "valid_from": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "valid_until": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class BundleItemForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = BundleItem
        fields = ["bundle", "feature", "quantity_override", "boolean_override", "sort_order"]


class DiscountCampaignForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = DiscountCampaign
        fields = [
            "name",
            "description",
            "discount_type",
            "discount_value",
            "applicable_features",
            "applicable_bundles",
            "valid_from",
            "valid_until",
            "is_active",
            "max_uses",
        ]
        widgets = {
            "applicable_features": forms.CheckboxSelectMultiple,
            "applicable_bundles": forms.CheckboxSelectMultiple,
            "valid_from": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "valid_until": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class CouponForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Coupon
        fields = [
            "code",
            "description",
            "discount_type",
            "discount_value",
            "applicable_features",
            "applicable_bundles",
            "max_uses",
            "max_uses_per_tenant",
            "valid_from",
            "valid_until",
            "is_active",
        ]
        widgets = {
            "applicable_features": forms.CheckboxSelectMultiple,
            "applicable_bundles": forms.CheckboxSelectMultiple,
            "valid_from": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "valid_until": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


class ManualGrantForm(TailwindFormMixin, forms.Form):
    feature_code = forms.ChoiceField(choices=())
    billing_cycle = forms.ChoiceField(choices=BillingCycle.choices, required=False)
    quantity = forms.IntegerField(min_value=1, initial=1, required=False)
    note = forms.CharField(widget=forms.Textarea, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        feature_choices = [("", "Select a feature")]
        feature_choices.extend(
            [
                (feature.code, f"{feature.name} ({feature.code})")
                for feature in FeatureDefinition.objects.filter(is_active=True).order_by("display_order", "name")
            ]
        )
        self.fields["feature_code"].choices = feature_choices


class TenantFeatureOverrideForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = TenantFeatureOverride
        fields = [
            "shop",
            "schema_name",
            "feature",
            "mode",
            "is_active",
            "currency",
            "billing_cycle",
            "custom_price",
            "custom_discount_percent",
            "custom_discount_amount",
            "effective_from",
            "effective_until",
            "notes",
        ]
        widgets = {
            "effective_from": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "effective_until": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
