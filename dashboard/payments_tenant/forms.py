"""
dashboard/payments_tenant/forms.py
====================================
All ModelForms for the tenant-facing payments dashboard.

Models covered:
  - TenantPaymentProfileForm      (edit only — 1 per tenant)
  - TenantGatewayCredentialForm   (tenant own API keys — write-only for encrypted fields)
  - SupportedCurrencyForm
  - RefundForm                    (initiate a refund — wrapped by request_refund util)
  - DisputeEvidenceForm           (attach evidence to a chargeback)
  - TenantBankAccountForm         (register a bank account for payouts)
  - PayoutRequestForm             (request a payout — wrapped by request_payout util)
  - TenantFraudRuleForm           (tenant-specific fraud rules)
  - TenantBlocklistEntryForm      (tenant-specific blocklist)

EXCLUDED / READ-ONLY models (append-only ledgers, no forms):
  - Transaction            → list + detail only
  - PaymentIntent          → list only
  - TenantBalance          → list only
  - TenantBalanceTransaction → list only
  - CommissionEntry        → list only
  - TransactionEvent       → shown in timeline on Transaction detail
  - FraudAssessment        → list only
  - ReconciliationReport   → list + detail only
  - ReconciliationEntry    → embedded in ReconciliationReport detail
  - SavedPaymentMethod     → list only

KEY DECISIONS:
  - Encrypted key fields use write-only PasswordInput — never echoed back to browser.
  - TenantPaymentProfile.kyb_documents, kyb_status, kyb_verified_at are excluded
    from the form (managed by platform admin only).
  - TenantBankAccount.account_number is a write-only field.
  - PayoutRequest: amount must be validated ≤ available balance (done in view via utility).
"""
import json
import logging
from decimal import Decimal

from django import forms
from sabistart_store.ui.forms import TailwindFormMixin

logger = logging.getLogger("dashboard.payments_tenant.forms")

# ── Tailwind CSS classes ──
_INPUT    = "w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-700 dark:text-white focus:ring-2 focus:ring-primary focus:outline-none"
_SELECT   = "w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-700 dark:text-white focus:ring-2 focus:ring-primary"
_TEXTAREA = "w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-700 dark:text-white focus:ring-2 focus:ring-primary resize-y min-h-[80px]"
_CHECK    = "h-4 w-4 rounded border-slate-300 text-primary focus:ring-primary"
_PASSWORD = "w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-700 dark:text-white focus:ring-2 focus:ring-primary font-mono"
_NUMBER   = "w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg text-sm bg-white dark:bg-slate-700 dark:text-white focus:ring-2 focus:ring-primary text-right font-mono"


# ─────────────────────────────────────────────────────────────
# TenantPaymentProfile — edit only
# ─────────────────────────────────────────────────────────────

class TenantPaymentProfileForm(TailwindFormMixin, forms.ModelForm):
    """
    Edit form for the tenant's master payment profile.
    KYB-related fields are excluded — those are managed by platform admins.
    account_status and payout_enabled are excluded from self-edit (platform manages).
    """

    class Meta:
        from dashboard.payments_tenant.models import TenantPaymentProfile
        model = TenantPaymentProfile
        fields = [
            "business_name",
            "business_type",
            "business_registration_number",
            "tax_identification_number",
            "business_address",
            "business_country",
            "business_phone",
            "support_email",
            "business_website",
            "default_currency",
            "transaction_description_template",
            "send_customer_receipt",
            "auto_capture",
            "payment_timeout_minutes",
            "payout_schedule",
            "minimum_payout_amount",
            "payout_currency",
            "notify_on_payment",
            "notify_on_failed_payment",
            "notify_on_dispute",
            "notify_on_payout",
            "payment_notification_email",
            "notes",
        ]
        # Excluded (read-only / platform-managed):
        #   id, created_at, updated_at, account_status, kyb_status, kyb_verified_at,
        #   kyb_documents, payout_enabled, has_custom_commission, custom_commission_rate,
        #   custom_commission_flat_fee, custom_commission_cap, onboarded_at, restriction_reason
        widgets = {
            "business_name":                   forms.TextInput(attrs={"class": _INPUT}),
            "business_type":                   forms.Select(attrs={"class": _SELECT}),
            "business_registration_number":    forms.TextInput(attrs={"class": _INPUT}),
            "tax_identification_number":       forms.TextInput(attrs={"class": _INPUT}),
            "business_address":                forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
            "business_country":                forms.TextInput(attrs={"class": _INPUT, "maxlength": "2",
                                                                      "placeholder": "NG"}),
            "business_phone":                  forms.TextInput(attrs={"class": _INPUT}),
            "support_email":                   forms.EmailInput(attrs={"class": _INPUT}),
            "business_website":                forms.URLInput(attrs={"class": _INPUT}),
            "default_currency":                forms.TextInput(attrs={"class": _INPUT, "maxlength": "3",
                                                                      "placeholder": "NGN"}),
            "transaction_description_template":forms.TextInput(attrs={"class": _INPUT}),
            "send_customer_receipt":           forms.CheckboxInput(attrs={"class": _CHECK}),
            "auto_capture":                    forms.CheckboxInput(attrs={"class": _CHECK}),
            "payment_timeout_minutes":         forms.NumberInput(attrs={"class": _NUMBER}),
            "payout_schedule":                 forms.Select(attrs={"class": _SELECT}),
            "minimum_payout_amount":           forms.NumberInput(attrs={"class": _NUMBER, "step": "0.01"}),
            "payout_currency":                 forms.TextInput(attrs={"class": _INPUT, "maxlength": "3"}),
            "notify_on_payment":               forms.CheckboxInput(attrs={"class": _CHECK}),
            "notify_on_failed_payment":        forms.CheckboxInput(attrs={"class": _CHECK}),
            "notify_on_dispute":               forms.CheckboxInput(attrs={"class": _CHECK}),
            "notify_on_payout":                forms.CheckboxInput(attrs={"class": _CHECK}),
            "payment_notification_email":      forms.EmailInput(attrs={"class": _INPUT}),
            "notes":                           forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
        }


# ─────────────────────────────────────────────────────────────
# TenantGatewayCredential (DIRECT MODE tenant own API keys)
# ─────────────────────────────────────────────────────────────

class TenantGatewayCredentialForm(TailwindFormMixin, forms.ModelForm):
    """
    Form to submit tenant's own API keys for DIRECT MODE activation.
    Encrypted fields use write-only PasswordInput — never echoed to browser.
    """

    public_key = forms.CharField(
        label="Public Key",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"class": _PASSWORD, "autocomplete": "off",
                   "placeholder": "Leave blank to keep existing key"},
        ),
        help_text="Only enter a new value to update the existing key.",
    )
    secret_key = forms.CharField(
        label="Secret Key *",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"class": _PASSWORD, "autocomplete": "off",
                   "placeholder": "Leave blank to keep existing key"},
        ),
    )
    encryption_key = forms.CharField(
        label="Encryption Key",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"class": _PASSWORD, "autocomplete": "off",
                   "placeholder": "Leave blank to keep existing key"},
        ),
    )
    webhook_secret = forms.CharField(
        label="Webhook Secret",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"class": _PASSWORD, "autocomplete": "off",
                   "placeholder": "Leave blank to keep existing key"},
        ),
    )

    class Meta:
        from dashboard.payments_tenant.models import TenantGatewayCredential
        model = TenantGatewayCredential
        fields = [
            "gateway",
            "label",
            "environment",
            "public_key",
            "secret_key",
            "encryption_key",
            "webhook_secret",
            "extra_credentials",
            "gateway_account_id",
            "gateway_business_name",
            "gateway_email",
        ]
        # Excluded (set by platform/system): payment_profile, status, validated_at,
        # validation_note, invalid_reason, revoked_at, revoked_by, revoke_reason, submitted_by
        widgets = {
            "gateway":              forms.Select(attrs={"class": _SELECT}),
            "label":                forms.TextInput(attrs={"class": _INPUT,
                                                           "placeholder": "e.g. 'Live Keys', 'Test Keys'"}),
            "environment":          forms.Select(attrs={"class": _SELECT}),
            "extra_credentials":    forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
            "gateway_account_id":   forms.TextInput(attrs={"class": _INPUT}),
            "gateway_business_name":forms.TextInput(attrs={"class": _INPUT}),
            "gateway_email":        forms.EmailInput(attrs={"class": _INPUT}),
        }

    def save(self, commit=True):
        """Preserve existing encrypted key values if new ones not supplied."""
        instance = super().save(commit=False)
        for field_name in ("public_key", "secret_key", "encryption_key", "webhook_secret"):
            new_val = self.cleaned_data.get(field_name, "").strip()
            if not new_val and self.instance.pk:
                existing = self.__class__.Meta.model.objects.get(pk=self.instance.pk)
                setattr(instance, field_name, getattr(existing, field_name, ""))
        if commit:
            instance.save()
        return instance


# ─────────────────────────────────────────────────────────────
# SupportedCurrency
# ─────────────────────────────────────────────────────────────

class SupportedCurrencyForm(TailwindFormMixin, forms.ModelForm):
    """Form for adding/editing currencies the tenant accepts."""

    class Meta:
        from dashboard.payments_tenant.models import SupportedCurrency
        model = SupportedCurrency
        fields = [
            "currency_code",
            "is_default",
            "is_enabled",
            "preferred_gateway",
            "exchange_rate_to_default",
        ]
        # Excluded: payment_profile (set in view)
        widgets = {
            "currency_code":          forms.TextInput(attrs={"class": _INPUT, "maxlength": "3",
                                                             "placeholder": "USD"}),
            "is_default":             forms.CheckboxInput(attrs={"class": _CHECK}),
            "is_enabled":             forms.CheckboxInput(attrs={"class": _CHECK}),
            "preferred_gateway":      forms.Select(attrs={"class": _SELECT}),
            "exchange_rate_to_default":forms.NumberInput(attrs={"class": _NUMBER, "step": "0.000001"}),
        }


# ─────────────────────────────────────────────────────────────
# Refund
# ─────────────────────────────────────────────────────────────

class RefundForm(TailwindFormMixin, forms.Form):
    """
    Custom form (not ModelForm) for initiating a refund.

    We use a plain Form rather than ModelForm because:
      - The refund is created via the utility layer (not raw form.save())
      - Several fields (transaction, payment_profile, currency) are derived from the
        transaction being refunded, not entered by the user.
      - The utility validates that amount ≤ refundable_amount and calls the gateway.
    """

    amount = forms.DecimalField(
        label="Refund Amount *",
        min_value=Decimal("0.01"),
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": _NUMBER, "step": "0.01"}),
    )
    reason = forms.ChoiceField(
        label="Reason *",
        choices=[
            ("customer_request",  "Customer Request"),
            ("item_not_received", "Item Not Received"),
            ("item_defective",    "Item Defective"),
            ("duplicate_charge",  "Duplicate Charge"),
            ("fraud",             "Fraud"),
            ("order_cancelled",   "Order Cancelled"),
            ("goodwill",          "Goodwill"),
            ("other",             "Other"),
        ],
        widget=forms.Select(attrs={"class": _SELECT}),
    )
    reason_detail = forms.CharField(
        label="Reason Detail",
        required=False,
        widget=forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
    )
    customer_note = forms.CharField(
        label="Customer Note (visible to customer)",
        required=False,
        widget=forms.Textarea(attrs={"class": _TEXTAREA, "rows": 2}),
    )
    internal_note = forms.CharField(
        label="Internal Note",
        required=False,
        widget=forms.Textarea(attrs={"class": _TEXTAREA, "rows": 2}),
    )

    def __init__(self, *args, transaction=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.transaction = transaction
        if transaction:
            max_refundable = transaction.refundable_amount
            self.fields["amount"].max_value = max_refundable
            self.fields["amount"].widget.attrs["max"] = str(max_refundable)
            self.fields["amount"].help_text = (
                f"Max refundable: {max_refundable} {transaction.currency}"
            )

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if self.transaction and amount and amount > self.transaction.refundable_amount:
            raise forms.ValidationError(
                f"Refund amount ({amount}) exceeds refundable amount "
                f"({self.transaction.refundable_amount} {self.transaction.currency})."
            )
        return amount


# ─────────────────────────────────────────────────────────────
# DisputeEvidence
# ─────────────────────────────────────────────────────────────

class DisputeEvidenceForm(TailwindFormMixin, forms.ModelForm):
    """Form to submit evidence against a chargeback/dispute."""

    class Meta:
        from dashboard.payments_tenant.models import DisputeEvidence
        model = DisputeEvidence
        fields = [
            "evidence_type",
            "description",
            "file_url",
            "file_type",
            "text_content",
        ]
        # Excluded: dispute (set in view), submitted_at (auto in view), submitted_by (request.user)
        widgets = {
            "evidence_type":  forms.Select(attrs={"class": _SELECT}),
            "description":    forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
            "file_url":       forms.URLInput(attrs={"class": _INPUT,
                                                    "placeholder": "https://…/shipping-receipt.pdf"}),
            "file_type":      forms.TextInput(attrs={"class": _INPUT, "placeholder": "pdf, jpg, png"}),
            "text_content":   forms.Textarea(attrs={"class": _TEXTAREA, "rows": 5,
                                                    "placeholder": "Paste relevant text content here…"}),
        }


# ─────────────────────────────────────────────────────────────
# TenantBankAccount
# ─────────────────────────────────────────────────────────────

class TenantBankAccountForm(TailwindFormMixin, forms.ModelForm):
    """
    Form for registering a bank account for payout.
    account_number is a write-only field — handled as password input.
    account_number_masked is auto-generated in the model's save().
    """

    account_number = forms.CharField(
        label="Account Number *",
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"class": _PASSWORD, "autocomplete": "off",
                   "placeholder": "Enter full account number (encrypted at rest)"},
        ),
        help_text="Your account number is encrypted and never displayed after saving.",
    )

    class Meta:
        from dashboard.payments_tenant.models import TenantBankAccount
        model = TenantBankAccount
        fields = [
            "account_name",
            "bank_name",
            "bank_code",
            "account_number",
            "account_type",
            "currency",
            "country_code",
            "routing_number",
            "iban",
            "swift_bic",
            "branch_code",
            "is_primary",
            "label",
            "notes",
        ]
        # Excluded: payment_profile, account_number_masked, gateway_recipient_code,
        #           gateway_provider (set by system), status, verified_at, verified_by,
        #           verification_method, verification_data, verification_note,
        #           failure_reason, display_order, max_payout_per_day, added_by, deactivated_at
        widgets = {
            "account_name":  forms.TextInput(attrs={"class": _INPUT}),
            "bank_name":     forms.TextInput(attrs={"class": _INPUT}),
            "bank_code":     forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. 058"}),
            "account_type":  forms.Select(attrs={"class": _SELECT}),
            "currency":      forms.TextInput(attrs={"class": _INPUT, "maxlength": "3", "placeholder": "NGN"}),
            "country_code":  forms.TextInput(attrs={"class": _INPUT, "maxlength": "2", "placeholder": "NG"}),
            "routing_number":forms.TextInput(attrs={"class": _INPUT}),
            "iban":          forms.TextInput(attrs={"class": _INPUT}),
            "swift_bic":     forms.TextInput(attrs={"class": _INPUT}),
            "branch_code":   forms.TextInput(attrs={"class": _INPUT}),
            "is_primary":    forms.CheckboxInput(attrs={"class": _CHECK}),
            "label":         forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. Operations Account"}),
            "notes":         forms.Textarea(attrs={"class": _TEXTAREA, "rows": 2}),
        }


# ─────────────────────────────────────────────────────────────
# PayoutRequest
# ─────────────────────────────────────────────────────────────

class PayoutRequestForm(TailwindFormMixin, forms.Form):
    """
    Custom Form (not ModelForm) for requesting a payout.
    Uses utility `request_payout()` instead of raw model save.
    Validation of the amount against available balance happens in the view,
    after this form validates the structural correctness.
    """

    bank_account = forms.ModelChoiceField(
        queryset=None,  # Set dynamically in __init__
        label="Bank Account *",
        widget=forms.Select(attrs={"class": _SELECT}),
        help_text="Only verified bank accounts are shown.",
    )
    amount = forms.DecimalField(
        label="Amount *",
        min_value=Decimal("1.00"),
        max_digits=18,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": _NUMBER, "step": "0.01"}),
    )
    narration = forms.CharField(
        label="Bank Statement Narration",
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": _INPUT, "placeholder": "e.g. SabiStart payout — March 2026"}),
    )
    tenant_note = forms.CharField(
        label="Internal Note",
        required=False,
        widget=forms.Textarea(attrs={"class": _TEXTAREA, "rows": 2}),
    )

    def __init__(self, *args, payment_profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        if payment_profile:
            from dashboard.payments_tenant.models import TenantBankAccount
            # Only show verified bank accounts for payout
            self.fields["bank_account"].queryset = TenantBankAccount.objects.filter(
                payment_profile=payment_profile,
                status=TenantBankAccount.AccountStatus.VERIFIED,
            )


# ─────────────────────────────────────────────────────────────
# FraudRule — tenant-specific
# ─────────────────────────────────────────────────────────────

class TenantFraudRuleForm(TailwindFormMixin, forms.ModelForm):
    """
    Fraud rule scoped to a specific tenant.
    payment_profile is set by the view — not exposed on the form.
    """

    class Meta:
        from dashboard.payments_tenant.models import FraudRule
        model = FraudRule
        fields = [
            "name",
            "rule_type",
            "action",
            "risk_score_contribution",
            "is_active",
            "priority",
            "threshold_amount",
            "count_threshold",
            "time_window_minutes",
            "blocked_values",
            "description",
        ]
        widgets = {
            "name":                     forms.TextInput(attrs={"class": _INPUT}),
            "rule_type":                forms.Select(attrs={"class": _SELECT}),
            "action":                   forms.Select(attrs={"class": _SELECT}),
            "risk_score_contribution":  forms.NumberInput(attrs={"class": _INPUT, "min": "0", "max": "100"}),
            "is_active":                forms.CheckboxInput(attrs={"class": _CHECK}),
            "priority":                 forms.NumberInput(attrs={"class": _INPUT}),
            "threshold_amount":         forms.NumberInput(attrs={"class": _NUMBER, "step": "0.01"}),
            "count_threshold":          forms.NumberInput(attrs={"class": _INPUT}),
            "time_window_minutes":      forms.NumberInput(attrs={"class": _INPUT}),
            "blocked_values":           forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3,
                                                              "placeholder": '["NG", "IR"] or ["123456"]'}),
            "description":              forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
        }

    def clean_blocked_values(self):
        val = self.cleaned_data.get("blocked_values")
        if isinstance(val, str) and val.strip():
            try:
                parsed = json.loads(val)
                if not isinstance(parsed, list):
                    raise forms.ValidationError("Must be a JSON array.")
                return parsed
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON. Must be a JSON array.")
        return val or []


# ─────────────────────────────────────────────────────────────
# BlocklistEntry — tenant-specific
# ─────────────────────────────────────────────────────────────

class TenantBlocklistEntryForm(TailwindFormMixin, forms.ModelForm):
    """
    Blocklist entry scoped to a specific tenant.
    payment_profile and added_by set in the view.
    is_platform_wide forced to False (tenant-only scope).
    """

    class Meta:
        from dashboard.payments_tenant.models import BlocklistEntry
        model = BlocklistEntry
        fields = [
            "entry_type",
            "value",
            "reason",
            "source",
            "expires_at",
            "source_transaction_id",
        ]
        widgets = {
            "entry_type":            forms.Select(attrs={"class": _SELECT}),
            "value":                 forms.TextInput(attrs={"class": _INPUT}),
            "reason":                forms.Textarea(attrs={"class": _TEXTAREA, "rows": 3}),
            "source":                forms.Select(attrs={"class": _SELECT}),
            "expires_at":            forms.DateTimeInput(attrs={"class": _INPUT, "type": "datetime-local"}),
            "source_transaction_id": forms.TextInput(attrs={"class": _INPUT,
                                                            "placeholder": "UUID (optional)"}),
        }

    def clean_value(self):
        val = self.cleaned_data.get("value", "").strip()
        if not val:
            raise forms.ValidationError("Blocklist value cannot be empty.")
        return val
