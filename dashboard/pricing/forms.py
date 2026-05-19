"""
dashboard/pricing/forms.py
===========================
All ModelForms for the Pricing & Promotions dashboard.

Covers (18 forms — gift cards excluded per spec):
  - Currency, ExchangeRate
  - PriceList, PriceListCustomerGroup, PriceListEntry
  - DiscountCode, DiscountRule
  - AutomaticDiscount, AutomaticDiscountCondition, AutomaticDiscountBenefit
  - BuyXGetYPromotion, BuyXGetYItem
  - VolumePricingTier
  - FlashSale, FlashSaleItem
  - TaxCategory, TaxZone, TaxRate

Design rules:
  - Every form is a ModelForm with an explicit `fields` list.
  - All widgets carry Tailwind CSS classes.
  - help_text is propagated to the template via field.help_text.
  - Read-only / auto-managed fields (usage_count, balance, code, etc.)
    are excluded from forms — they appear as read-only display spans
    in the template when editing.
  - ForeignKey fields use Select widgets with Tailwind classes.
  - JSONField fields use Textarea (staff enters JSON manually).
  - Choices fields render as <select>.
  - Decimal/Integer fields use number inputs.
  - DateTimeField uses datetime-local HTML5 input.
  - BooleanField uses checkbox (styled separately in template).
"""

from django import forms
from django.utils.translation import gettext_lazy as _

from dashboard.pricing.models import (
    Currency,
    ExchangeRate,
    PriceList,
    PriceListCustomerGroup,
    PriceListEntry,
    DiscountCode,
    DiscountRule,
    AutomaticDiscount,
    AutomaticDiscountCondition,
    AutomaticDiscountBenefit,
    BuyXGetYPromotion,
    BuyXGetYItem,
    VolumePricingTier,
    FlashSale,
    FlashSaleItem,
    TaxCategory,
    TaxZone,
    TaxRate,
)


# ─────────────────────────────────────────────────────────────
# SHARED WIDGET CLASSES
# (Applied consistently to every field type across all forms)
# ─────────────────────────────────────────────────────────────

# Reusable Tailwind class strings to avoid repetition and ensure consistency.
_INPUT = (
    "block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 "
    "rounded-lg text-sm text-slate-900 dark:text-white "
    "bg-white dark:bg-slate-700 "
    "focus:ring-2 focus:ring-primary focus:border-transparent "
    "placeholder-slate-400 dark:placeholder-slate-500"
)
_SELECT = (
    "block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 "
    "rounded-lg text-sm text-slate-900 dark:text-white "
    "bg-white dark:bg-slate-700 "
    "focus:ring-2 focus:ring-primary focus:border-transparent"
)
_SEARCHABLE_SELECT = f"{_SELECT} js-searchable-select"
_TEXTAREA = (
    "block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 "
    "rounded-lg text-sm text-slate-900 dark:text-white "
    "bg-white dark:bg-slate-700 "
    "focus:ring-2 focus:ring-primary focus:border-transparent "
    "resize-y min-h-[80px]"
)
_CHECKBOX = "rounded border-slate-300 dark:border-slate-600 text-primary focus:ring-primary"
_DATETIME = (
    "block w-full px-3 py-2 border border-slate-300 dark:border-slate-600 "
    "rounded-lg text-sm text-slate-900 dark:text-white "
    "bg-white dark:bg-slate-700 "
    "focus:ring-2 focus:ring-primary focus:border-transparent"
)

# ─────────────────────────────────────────────────────────────
# SECTION 1 — CURRENCY
# ─────────────────────────────────────────────────────────────

class CurrencyForm(forms.ModelForm):
    """
    Form for creating and editing Currency records.
    The `is_base_currency` flag triggers a save-level side effect on the model
    (clearing other base currencies). The form simply exposes it as a checkbox.
    """

    class Meta:
        model = Currency
        fields = [
            "code",
            "name",
            "symbol",
            "symbol_position",
            "decimal_places",
            "thousands_separator",
            "decimal_separator",
            "rounding_mode",
            "is_base_currency",
            "is_enabled",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. USD, NGN, GBP", "maxlength": 3}),
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. US Dollar"}),
            "symbol": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. $, ₦, £"}),
            "symbol_position": forms.Select(attrs={"class": _SELECT}),
            "decimal_places": forms.NumberInput(attrs={"class": _INPUT, "min": 0, "max": 4}),
            "thousands_separator": forms.TextInput(attrs={"class": _INPUT, "maxlength": 2, "placeholder": ","}),
            "decimal_separator": forms.TextInput(attrs={"class": _INPUT, "maxlength": 2, "placeholder": "."}),
            "rounding_mode": forms.Select(attrs={"class": _SELECT}),
            "is_base_currency": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "is_enabled": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }

    def clean_code(self):
        """Enforce uppercase ISO 4217 format."""
        code = self.cleaned_data.get("code", "").strip().upper()
        return code


# ─────────────────────────────────────────────────────────────
# SECTION 1 — EXCHANGE RATE
# ─────────────────────────────────────────────────────────────

class ExchangeRateForm(forms.ModelForm):
    """
    Form for creating and editing ExchangeRate records.
    The pair (base_currency, target_currency) must be unique —
    enforced at DB level. The form validates that base ≠ target.
    """

    class Meta:
        model = ExchangeRate
        fields = [
            "base_currency",
            "target_currency",
            "rate",
            "rate_buy",
            "rate_sell",
            "markup_percentage",
            "is_manual_override",
            "provider",
            "fetched_at",
        ]
        widgets = {
            "base_currency": forms.Select(attrs={"class": _SELECT}),
            "target_currency": forms.Select(attrs={"class": _SELECT}),
            "rate": forms.NumberInput(attrs={"class": _INPUT, "step": "0.000001", "min": "0.000001"}),
            "rate_buy": forms.NumberInput(attrs={"class": _INPUT, "step": "0.000001"}),
            "rate_sell": forms.NumberInput(attrs={"class": _INPUT, "step": "0.000001"}),
            "markup_percentage": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0", "max": "50"}),
            "is_manual_override": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "provider": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. fixer.io, manual"}),
            "fetched_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def clean(self):
        """Validate that base and target currencies are different."""
        cleaned = super().clean()
        base = cleaned.get("base_currency")
        target = cleaned.get("target_currency")
        if base and target and base == target:
            raise forms.ValidationError(
                _("Base currency and target currency cannot be the same.")
            )
        return cleaned


# ─────────────────────────────────────────────────────────────
# SECTION 2 — PRICE LIST
# ─────────────────────────────────────────────────────────────

class PriceListForm(forms.ModelForm):
    """
    Form for creating and editing PriceList records.
    global_discount_percentage and global_multiplier are conditionally
    relevant (based on price_list_type) — the template uses JS to show/hide.
    Activation dates come from ActivatableModel (starts_at, ends_at).
    is_active also comes from ActivatableModel.
    """

    class Meta:
        model = PriceList
        fields = [
            "name",
            "code",
            "description",
            "currency",
            "price_list_type",
            "calculation_base",
            "global_discount_percentage",
            "global_multiplier",
            "rounding_increment",
            "is_public",
            "requires_login",
            "priority",
            "allow_discount_stacking",
            "internal_note",
            "is_active",
            "starts_at",
            "ends_at",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. Wholesale Prices"}),
            "code": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. WHOLESALE"}),
            "description": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Description..."}),
            "currency": forms.Select(attrs={"class": _SELECT}),
            "price_list_type": forms.Select(attrs={"class": _SELECT, "id": "id_price_list_type"}),
            "calculation_base": forms.Select(attrs={"class": _SELECT}),
            "global_discount_percentage": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0", "max": "100"}),
            "global_multiplier": forms.NumberInput(attrs={"class": _INPUT, "step": "0.0001", "min": "0.0001", "max": "10"}),
            "rounding_increment": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01"}),
            "is_public": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "requires_login": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "priority": forms.NumberInput(attrs={"class": _INPUT, "min": "0"}),
            "allow_discount_stacking": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "internal_note": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Internal notes..."}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "starts_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def clean_code(self):
        """Codes must be uppercase machine-readable identifiers."""
        return self.cleaned_data.get("code", "").strip().upper()


# ─────────────────────────────────────────────────────────────
# SECTION 2 — PRICE LIST CUSTOMER GROUP ASSIGNMENT
# ─────────────────────────────────────────────────────────────

class PriceListCustomerGroupForm(forms.ModelForm):
    """
    Assigns a PriceList to a CustomerGroup or an individual Customer.
    The price_list FK is set from the URL context (the parent PriceList),
    so it is excluded here and set in the view's form_valid().
    At least one of customer_group or customer must be set — enforced in clean().
    """

    class Meta:
        model = PriceListCustomerGroup
        fields = [
            "customer_group",
            "customer",
            "override_priority",
        ]
        widgets = {
            "customer_group": forms.Select(attrs={"class": _SELECT}),
            "customer": forms.Select(attrs={"class": _SELECT}),
            "override_priority": forms.NumberInput(attrs={"class": _INPUT, "min": "0"}),
        }

    def clean(self):
        """At least one of customer_group or customer must be provided."""
        cleaned = super().clean()
        if not cleaned.get("customer_group") and not cleaned.get("customer"):
            raise forms.ValidationError(
                _("You must assign this price list to either a Customer Group or an Individual Customer.")
            )
        return cleaned


# ─────────────────────────────────────────────────────────────
# SECTION 2 — PRICE LIST ENTRY
# ─────────────────────────────────────────────────────────────

class PriceListEntryForm(forms.ModelForm):
    """
    A specific price override for a Product, Variant, or Category within a PriceList.
    price_list FK is set from the URL context and excluded here.
    entry_type determines which price fields are relevant — template shows/hides via JS.
    At least one target (product, variant, or category) must be set.
    """

    class Meta:
        model = PriceListEntry
        fields = [
            "product",
            "variant",
            "category",
            "entry_type",
            "price",
            "min_price",
            "discount_percentage",
            "fixed_discount",
            "multiplier",
            "compare_at_price",
            "is_active",
            "min_quantity",
        ]
        widgets = {
            "product": forms.Select(attrs={"class": _SELECT}),
            "variant": forms.Select(attrs={"class": _SELECT}),
            "category": forms.Select(attrs={"class": _SELECT}),
            "entry_type": forms.Select(attrs={"class": _SELECT, "id": "id_entry_type"}),
            "price": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "min_price": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "discount_percentage": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0", "max": "100"}),
            "fixed_discount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "multiplier": forms.NumberInput(attrs={"class": _INPUT, "step": "0.0001", "min": "0.0001", "max": "10"}),
            "compare_at_price": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01"}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "min_quantity": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
        }

    def clean(self):
        """At least one target must be specified."""
        cleaned = super().clean()
        if not any([cleaned.get("product"), cleaned.get("variant"), cleaned.get("category")]):
            raise forms.ValidationError(
                _("You must specify at least one target: Product, Variant, or Category.")
            )
        return cleaned


# ─────────────────────────────────────────────────────────────
# SECTION 3 — DISCOUNT CODE
# ─────────────────────────────────────────────────────────────

class DiscountCodeForm(forms.ModelForm):
    """
    Form for creating and editing DiscountCode (coupon) records.
    Excluded read-only fields: usage_count (auto-incremented), last_used_at (auto-set).
    The code is always stored uppercase — enforced in clean_code().
    value_type determines which value fields apply — template shows/hides via JS.
    """

    class Meta:
        model = DiscountCode
        fields = [
            "code",
            "title",
            "description",
            "value_type",
            "percentage_value",
            "fixed_amount",
            "currency",
            "free_item_variant",
            "buy_x_get_y_promotion",
            "scope",
            "allocation_method",
            "usage_limit",
            "usage_limit_per_customer",
            "minimum_order_amount",
            "minimum_quantity",
            "requires_first_order",
            "customer_eligibility",
            "is_combinable_with_price_lists",
            "is_combinable_with_automatic_discounts",
            "is_combinable_with_other_codes",
            "max_discount_amount",
            "internal_note",
            "is_active",
            "starts_at",
            "ends_at",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. SUMMER20", "style": "text-transform:uppercase"}),
            "title": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Internal name"}),
            "description": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": "Customer-facing description..."}),
            "value_type": forms.Select(attrs={"class": _SELECT, "id": "id_value_type"}),
            "percentage_value": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01", "max": "100"}),
            "fixed_amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01"}),
            "currency": forms.TextInput(attrs={"class": _INPUT, "maxlength": 3, "placeholder": "USD"}),
            "free_item_variant": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "buy_x_get_y_promotion": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "scope": forms.Select(attrs={"class": _SELECT}),
            "allocation_method": forms.Select(attrs={"class": _SELECT}),
            "usage_limit": forms.NumberInput(attrs={"class": _INPUT, "min": "1", "placeholder": "Leave blank for unlimited"}),
            "usage_limit_per_customer": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
            "minimum_order_amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "minimum_quantity": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
            "requires_first_order": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "customer_eligibility": forms.Select(attrs={"class": _SELECT}),
            "is_combinable_with_price_lists": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "is_combinable_with_automatic_discounts": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "is_combinable_with_other_codes": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "max_discount_amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01"}),
            "internal_note": forms.Textarea(attrs={"class": _TEXTAREA}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "starts_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def clean_code(self):
        """Enforce uppercase; strip whitespace."""
        return self.cleaned_data.get("code", "").strip().upper()


# ─────────────────────────────────────────────────────────────
# SECTION 3 — DISCOUNT RULE
# ─────────────────────────────────────────────────────────────

class DiscountRuleForm(forms.ModelForm):
    """
    A single eligibility rule attached to a DiscountCode.
    discount_code FK is set from URL context (parent discount code PK).
    rule_type determines which target field is relevant — template shows/hides via JS.
    """

    class Meta:
        model = DiscountRule
        fields = [
            "rule_type",
            "match_condition",
            "product",
            "variant",
            "category",
            "customer_group",
            "customer",
            "amount_threshold",
            "quantity_threshold",
        ]
        widgets = {
            "rule_type": forms.Select(attrs={"class": _SELECT, "id": "id_rule_type"}),
            "match_condition": forms.Select(attrs={"class": _SELECT}),
            "product": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "variant": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "category": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "customer_group": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "customer": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "amount_threshold": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "quantity_threshold": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
        }


# ─────────────────────────────────────────────────────────────
# SECTION 4 — AUTOMATIC DISCOUNT
# ─────────────────────────────────────────────────────────────

class AutomaticDiscountForm(forms.ModelForm):
    """
    Form for creating and editing AutomaticDiscount records.
    Excluded: usage_count (editable=False on model, auto-incremented).
    discount_method determines which value fields are relevant.
    """

    class Meta:
        model = AutomaticDiscount
        fields = [
            "title",
            "customer_facing_title",
            "description",
            "discount_method",
            "percentage_value",
            "fixed_amount",
            "max_discount_amount",
            "buy_x_get_y_promotion",
            "free_item_variant",
            "free_item_quantity",
            "allow_stacking",
            "is_combinable_with_codes",
            "priority",
            "usage_limit",
            "usage_limit_per_customer",
            "internal_note",
            "is_active",
            "starts_at",
            "ends_at",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. Summer Collection 10% Off"}),
            "customer_facing_title": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Shown in cart when applied"}),
            "description": forms.Textarea(attrs={"class": _TEXTAREA}),
            "discount_method": forms.Select(attrs={"class": _SELECT, "id": "id_discount_method"}),
            "percentage_value": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01", "max": "100"}),
            "fixed_amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01"}),
            "max_discount_amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01"}),
            "buy_x_get_y_promotion": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "free_item_variant": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "free_item_quantity": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
            "allow_stacking": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "is_combinable_with_codes": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "priority": forms.NumberInput(attrs={"class": _INPUT, "min": "0"}),
            "usage_limit": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
            "usage_limit_per_customer": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
            "internal_note": forms.Textarea(attrs={"class": _TEXTAREA}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "starts_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }


# ─────────────────────────────────────────────────────────────
# SECTION 4 — AUTOMATIC DISCOUNT CONDITION
# ─────────────────────────────────────────────────────────────

class AutomaticDiscountConditionForm(forms.ModelForm):
    """
    A single prerequisite condition for an AutomaticDiscount.
    automatic_discount FK is set from URL context.
    condition_type determines which value fields are relevant.
    """

    class Meta:
        model = AutomaticDiscountCondition
        fields = [
            "condition_type",
            "amount_threshold",
            "quantity_threshold",
            "integer_threshold",
            "customer_group",
            "product",
            "string_value",
        ]
        widgets = {
            "condition_type": forms.Select(attrs={"class": _SELECT, "id": "id_condition_type"}),
            "amount_threshold": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "quantity_threshold": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
            "integer_threshold": forms.NumberInput(attrs={"class": _INPUT, "min": "0"}),
            "customer_group": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "product": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "string_value": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. tag name"}),
        }


# ─────────────────────────────────────────────────────────────
# SECTION 4 — AUTOMATIC DISCOUNT BENEFIT
# ─────────────────────────────────────────────────────────────

class AutomaticDiscountBenefitForm(forms.ModelForm):
    """
    A specific benefit granted by an AutomaticDiscount.
    automatic_discount FK is set from URL context.
    """

    class Meta:
        model = AutomaticDiscountBenefit
        fields = [
            "benefit_scope",
            "percentage_value",
            "fixed_amount",
            "tier_min_subtotal",
            "tier_order",
            "product",
        ]
        widgets = {
            "benefit_scope": forms.Select(attrs={"class": _SELECT}),
            "percentage_value": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01", "max": "100"}),
            "fixed_amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01"}),
            "tier_min_subtotal": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "tier_order": forms.NumberInput(attrs={"class": _INPUT, "min": "0"}),
            "product": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
        }


# ─────────────────────────────────────────────────────────────
# SECTION 5 — BUY X GET Y PROMOTION
# ─────────────────────────────────────────────────────────────

class BuyXGetYPromotionForm(forms.ModelForm):
    """
    Form for creating and editing BuyXGetYPromotion records.
    Excluded: usage_count (read-only).
    """

    class Meta:
        model = BuyXGetYPromotion
        fields = [
            "title",
            "description",
            "buy_type",
            "buy_quantity",
            "buy_minimum_amount",
            "get_type",
            "get_quantity",
            "get_discount_percentage",
            "get_specific_variant",
            "apply_to",
            "max_applications_per_order",
            "one_per_customer",
            "usage_limit",
            "internal_note",
            "is_active",
            "starts_at",
            "ends_at",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. Buy 2 Get 1 Free"}),
            "description": forms.Textarea(attrs={"class": _TEXTAREA}),
            "buy_type": forms.Select(attrs={"class": _SELECT, "id": "id_buy_type"}),
            "buy_quantity": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
            "buy_minimum_amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "get_type": forms.Select(attrs={"class": _SELECT, "id": "id_get_type"}),
            "get_quantity": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
            "get_discount_percentage": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0", "max": "100"}),
            "get_specific_variant": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "apply_to": forms.Select(attrs={"class": _SELECT}),
            "max_applications_per_order": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
            "one_per_customer": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "usage_limit": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
            "internal_note": forms.Textarea(attrs={"class": _TEXTAREA}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "starts_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }


# ─────────────────────────────────────────────────────────────
# SECTION 5 — BUY X GET Y ITEM
# ─────────────────────────────────────────────────────────────

class BuyXGetYItemForm(forms.ModelForm):
    """
    An eligible product on the Buy or Get side of a BuyXGetYPromotion.
    promotion FK is set from URL context.
    At least one of product, variant, or category must be set.
    """

    class Meta:
        model = BuyXGetYItem
        fields = [
            "side",
            "product",
            "variant",
            "category",
            "minimum_quantity",
        ]
        widgets = {
            "side": forms.Select(attrs={"class": _SELECT}),
            "product": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "variant": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "category": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "minimum_quantity": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
        }

    def clean(self):
        """At least one target must be specified."""
        cleaned = super().clean()
        if not any([cleaned.get("product"), cleaned.get("variant"), cleaned.get("category")]):
            raise forms.ValidationError(
                _("You must specify at least one target: Product, Variant, or Category.")
            )
        return cleaned


# ─────────────────────────────────────────────────────────────
# SECTION 5 — VOLUME PRICING TIER
# ─────────────────────────────────────────────────────────────

class VolumePricingTierForm(forms.ModelForm):
    """
    Quantity-break pricing for a specific ProductVariant.
    price_type determines which price fields are relevant — template shows/hides via JS.
    """

    class Meta:
        model = VolumePricingTier
        fields = [
            "variant",
            "customer_group",
            "min_quantity",
            "max_quantity",
            "price_type",
            "price",
            "discount_percentage",
            "fixed_discount",
            "is_active",
            "applies_on_top_of_price_lists",
            "show_savings_label",
        ]
        widgets = {
            "variant": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "customer_group": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "min_quantity": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
            "max_quantity": forms.NumberInput(attrs={"class": _INPUT, "min": "1", "placeholder": "Leave blank for no upper limit"}),
            "price_type": forms.Select(attrs={"class": _SELECT, "id": "id_price_type"}),
            "price": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "discount_percentage": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01", "max": "100"}),
            "fixed_discount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01"}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "applies_on_top_of_price_lists": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "show_savings_label": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }

    def clean(self):
        """Validate min_quantity < max_quantity when both are set."""
        cleaned = super().clean()
        min_qty = cleaned.get("min_quantity")
        max_qty = cleaned.get("max_quantity")
        if min_qty and max_qty and max_qty <= min_qty:
            raise forms.ValidationError(
                _("Maximum quantity must be greater than minimum quantity.")
            )
        return cleaned


# ─────────────────────────────────────────────────────────────
# SECTION 5 — FLASH SALE
# ─────────────────────────────────────────────────────────────

class FlashSaleForm(forms.ModelForm):
    """
    Form for creating and editing FlashSale records.
    starts_at and ends_at come from ActivatableModel.
    created_by is set from request.user in the view, not from the form.
    """

    class Meta:
        model = FlashSale
        fields = [
            "name",
            "slug",
            "description",
            "banner_image",
            "badge_label",
            "show_countdown_timer",
            "is_publicly_visible",
            "applies_to_all_products",
            "global_discount_percentage",
            "priority",
            "is_active",
            "starts_at",
            "ends_at",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. Black Friday Flash Sale"}),
            "slug": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. black-friday-2025"}),
            "description": forms.Textarea(attrs={"class": _TEXTAREA}),
            "banner_image": forms.ClearableFileInput(attrs={"class": "block w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-primary file:text-white hover:file:bg-blue-600"}),
            "badge_label": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. FLASH SALE", "maxlength": 50}),
            "show_countdown_timer": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "is_publicly_visible": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "applies_to_all_products": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "global_discount_percentage": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01", "max": "100"}),
            "priority": forms.NumberInput(attrs={"class": _INPUT, "min": "0"}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "starts_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }


# ─────────────────────────────────────────────────────────────
# SECTION 5 — FLASH SALE ITEM
# ─────────────────────────────────────────────────────────────

class FlashSaleItemForm(forms.ModelForm):
    """
    A specific product/variant included in a FlashSale.
    flash_sale FK is set from URL context.
    Excluded: units_sold (read-only — auto-incremented via thread-safe method).
    At least one of product or variant must be set.
    """

    class Meta:
        model = FlashSaleItem
        fields = [
            "product",
            "variant",
            "discount_percentage",
            "sale_price",
            "original_price_override",
            "stock_limit",
            "per_customer_limit",
            "is_active",
        ]
        widgets = {
            "product": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "variant": forms.Select(attrs={"class": _SEARCHABLE_SELECT, "data-searchable": "true"}),
            "discount_percentage": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0.01", "max": "100"}),
            "sale_price": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "original_price_override": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01"}),
            "stock_limit": forms.NumberInput(attrs={"class": _INPUT, "min": "1", "placeholder": "Leave blank for no limit"}),
            "per_customer_limit": forms.NumberInput(attrs={"class": _INPUT, "min": "1"}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
        }

    def clean(self):
        """At least one of product or variant must be set."""
        cleaned = super().clean()
        if not cleaned.get("product") and not cleaned.get("variant"):
            raise forms.ValidationError(
                _("You must specify at least one of Product or Variant.")
            )
        return cleaned


# ─────────────────────────────────────────────────────────────
# SECTION 7 — TAX CATEGORY
# ─────────────────────────────────────────────────────────────

class TaxCategoryForm(forms.ModelForm):
    """
    Form for creating and editing TaxCategory records.
    is_default triggers a model-level save side-effect (clears other defaults).
    """

    class Meta:
        model = TaxCategory
        fields = [
            "name",
            "code",
            "description",
            "is_default",
            "is_taxable",
            "sort_order",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. Standard Rate"}),
            "code": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. STANDARD", "style": "text-transform:uppercase"}),
            "description": forms.Textarea(attrs={"class": _TEXTAREA}),
            "is_default": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "is_taxable": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "sort_order": forms.NumberInput(attrs={"class": _INPUT, "min": "0"}),
        }

    def clean_code(self):
        return self.cleaned_data.get("code", "").strip().upper()


# ─────────────────────────────────────────────────────────────
# SECTION 7 — TAX ZONE
# ─────────────────────────────────────────────────────────────

class TaxZoneForm(forms.ModelForm):
    """
    Form for creating and editing TaxZone records.
    JSON fields (countries, states, cities, postal_codes, exclude_countries)
    use Textarea — staff enters valid JSON arrays (e.g. ["NG", "GH"]).
    """

    class Meta:
        model = TaxZone
        fields = [
            "name",
            "code",
            "zone_type",
            "countries",
            "states",
            "cities",
            "postal_codes",
            "exclude_countries",
            "use_billing_address",
            "tax_registration_number",
            "is_active",
            "priority",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. Nigeria"}),
            "code": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. NG", "style": "text-transform:uppercase"}),
            "zone_type": forms.Select(attrs={"class": _SELECT}),
            "countries": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": '["NG", "GH", "KE"]', "rows": 3}),
            "states": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": '["CA", "NY"]', "rows": 3}),
            "cities": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": '["Lagos", "Abuja"]', "rows": 3}),
            "postal_codes": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": '["10001", "100*"]', "rows": 3}),
            "exclude_countries": forms.Textarea(attrs={"class": _TEXTAREA, "placeholder": '["US", "CA"]', "rows": 3}),
            "use_billing_address": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "tax_registration_number": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. VAT number"}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "priority": forms.NumberInput(attrs={"class": _INPUT, "min": "0"}),
        }

    def clean_code(self):
        return self.cleaned_data.get("code", "").strip().upper()


# ─────────────────────────────────────────────────────────────
# SECTION 7 — TAX RATE
# ─────────────────────────────────────────────────────────────

class TaxRateForm(forms.ModelForm):
    """
    Form for creating and editing TaxRate records.
    The pair (tax_zone, tax_category) must be unique — enforced at DB level.
    Activation fields (is_active, starts_at, ends_at) come from ActivatableModel.
    """

    class Meta:
        model = TaxRate
        fields = [
            "tax_zone",
            "tax_category",
            "name",
            "tax_type",
            "rate",
            "is_included_in_price",
            "is_compound",
            "applies_to_shipping",
            "applies_to_digital_goods",
            "threshold_amount",
            "de_minimis_threshold",
            "tax_authority",
            "tax_code",
            "priority",
            "is_active",
            "starts_at",
            "ends_at",
        ]
        widgets = {
            "tax_zone": forms.Select(attrs={"class": _SELECT}),
            "tax_category": forms.Select(attrs={"class": _SELECT}),
            "name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. VAT (7.5%)"}),
            "tax_type": forms.Select(attrs={"class": _SELECT}),
            "rate": forms.NumberInput(attrs={"class": _INPUT, "step": "0.0001", "min": "0", "max": "100"}),
            "is_included_in_price": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "is_compound": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "applies_to_shipping": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "applies_to_digital_goods": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "threshold_amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "de_minimis_threshold": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "min": "0"}),
            "tax_authority": forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. FIRS, HMRC"}),
            "tax_code": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Official tax code"}),
            "priority": forms.NumberInput(attrs={"class": _INPUT, "min": "0"}),
            "is_active": forms.CheckboxInput(attrs={"class": _CHECKBOX}),
            "starts_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"class": _DATETIME, "type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }
