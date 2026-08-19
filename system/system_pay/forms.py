from django import forms

from sabistart.ui.forms import TailwindFormMixin
from system.system_pay.models import (
    GatewayWebhookConfig,
    PaymentGatewayDefinition,
    PlatformCommissionRule,
    PlatformGatewayCredential,
    PlatformPaymentSetting,
)


class PaymentGatewayDefinitionForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = PaymentGatewayDefinition
        fields = [
            "provider",
            "name",
            "description",
            "badge_label",
            "display_order",
            "logo_url",
            "website_url",
            "documentation_url",
            "dashboard_url",
            "is_enabled",
            "is_available_for_direct_mode",
            "requires_business_verification",
            "supported_countries",
            "supported_currencies",
            "supports_recurring",
            "supports_refunds",
            "supports_partial_refunds",
            "supports_tokenization",
            "supports_3ds",
            "supports_split_payment",
            "supports_virtual_accounts",
            "supports_authorization",
            "min_transaction_amount",
            "max_transaction_amount",
            "settlement_days",
            "settlement_note",
            "credential_schema",
            "webhook_events",
        ]


class PlatformGatewayCredentialForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = PlatformGatewayCredential
        fields = [
            "name",
            "environment",
            "is_active",
            "priority",
            "public_key",
            "secret_key",
            "encryption_key",
            "webhook_secret",
            "extra_credentials",
            "account_id",
            "subaccount_code",
            "daily_transaction_limit",
            "monthly_volume_limit",
            "supported_countries",
            "default_currency",
            "is_healthy",
            "health_note",
        ]


class GatewayWebhookConfigForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = GatewayWebhookConfig
        fields = [
            "webhook_url",
            "signature_header",
            "signature_algorithm",
            "ip_whitelist",
            "is_active",
        ]


class PlatformPaymentSettingForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = PlatformPaymentSetting
        fields = [
            "name",
            "default_currency",
            "supported_currencies",
            "allow_multi_currency",
            "automatic_payout_review",
            "default_payout_schedule",
            "default_payout_hold_days",
            "default_minimum_payout_amount",
            "default_gateway_timeout_minutes",
            "enable_direct_mode_reviews",
            "enable_platform_refund_tools",
            "enable_platform_dispute_tools",
            "metadata",
        ]


class PlatformCommissionRuleForm(TailwindFormMixin, forms.ModelForm):
    preview_amount = forms.DecimalField(required=False, min_value=0)

    class Meta:
        model = PlatformCommissionRule
        fields = [
            "name",
            "gateway",
            "subscription_plan",
            "country_code",
            "currency",
            "percentage_rate",
            "flat_fee",
            "cap_amount",
            "minimum_fee",
            "priority",
            "is_active",
            "notes",
        ]
