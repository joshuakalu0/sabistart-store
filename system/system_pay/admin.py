from django.contrib import admin

from .models import (
    GatewayWebhookConfig,
    PaymentGatewayDefinition,
    PlatformCommissionRule,
    PlatformDisputeIndex,
    PlatformGatewayCredential,
    PlatformPaymentSetting,
    PlatformPayoutIndex,
    PlatformRefundIndex,
    PlatformTransactionIndex,
    TenantGatewaySnapshot,
    TenantPaymentSnapshot,
)


class PlatformGatewayCredentialInline(admin.TabularInline):
    model = PlatformGatewayCredential
    extra = 0
    fields = (
        "name",
        "environment",
        "is_active",
        "priority",
        "default_currency",
        "is_healthy",
        "last_health_check_at",
    )
    readonly_fields = ("last_health_check_at", "last_used_at")
    show_change_link = True


class GatewayWebhookConfigInline(admin.StackedInline):
    model = GatewayWebhookConfig
    extra = 0
    max_num = 1
    fields = (
        "webhook_url",
        "signature_header",
        "signature_algorithm",
        "ip_whitelist",
        "is_active",
        "last_received_at",
        "total_events_received",
    )
    readonly_fields = ("last_received_at", "total_events_received")


@admin.register(PaymentGatewayDefinition)
class PaymentGatewayDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "provider",
        "is_enabled",
        "is_available_for_direct_mode",
        "supports_refunds",
        "supports_tokenization",
        "country_count",
        "currency_count",
        "display_order",
    )
    list_filter = (
        "is_enabled",
        "is_available_for_direct_mode",
        "requires_business_verification",
        "supports_refunds",
        "supports_partial_refunds",
        "supports_recurring",
        "supports_tokenization",
        "supports_3ds",
        "supports_split_payment",
        "supports_virtual_accounts",
        "supports_authorization",
        "provider",
    )
    search_fields = ("name", "provider", "description", "badge_label")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("display_order", "name")
    inlines = (PlatformGatewayCredentialInline, GatewayWebhookConfigInline)
    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    "id",
                    "provider",
                    "name",
                    "description",
                    "badge_label",
                    "display_order",
                )
            },
        ),
        (
            "Availability",
            {
                "fields": (
                    "is_enabled",
                    "is_available_for_direct_mode",
                    "requires_business_verification",
                    "supported_countries",
                    "supported_currencies",
                    "min_transaction_amount",
                    "max_transaction_amount",
                    "settlement_days",
                    "settlement_note",
                )
            },
        ),
        (
            "Feature Support",
            {
                "fields": (
                    "supports_recurring",
                    "supports_refunds",
                    "supports_partial_refunds",
                    "supports_tokenization",
                    "supports_3ds",
                    "supports_split_payment",
                    "supports_virtual_accounts",
                    "supports_authorization",
                )
            },
        ),
        (
            "External References",
            {
                "fields": (
                    "logo_url",
                    "website_url",
                    "documentation_url",
                    "dashboard_url",
                    "credential_schema",
                    "webhook_events",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Countries")
    def country_count(self, obj):
        return len(obj.supported_countries or [])

    @admin.display(description="Currencies")
    def currency_count(self, obj):
        return len(obj.supported_currencies or [])


@admin.register(PlatformGatewayCredential)
class PlatformGatewayCredentialAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "gateway",
        "environment",
        "is_active",
        "priority",
        "default_currency",
        "is_healthy",
        "last_health_check_at",
    )
    list_filter = ("is_active", "is_healthy", "environment", "gateway__provider")
    search_fields = ("name", "gateway__name", "gateway__provider", "account_id", "subaccount_code")
    readonly_fields = ("id", "created_at", "updated_at", "last_used_at", "last_health_check_at")
    ordering = ("gateway__name", "-priority", "name")
    fieldsets = (
        (
            "Identity",
            {"fields": ("id", "gateway", "name", "environment", "is_active", "priority")},
        ),
        (
            "Keys",
            {
                "fields": (
                    "public_key",
                    "secret_key",
                    "encryption_key",
                    "webhook_secret",
                    "extra_credentials",
                )
            },
        ),
        (
            "Gateway Account",
            {
                "fields": (
                    "account_id",
                    "subaccount_code",
                    "default_currency",
                    "supported_countries",
                )
            },
        ),
        (
            "Limits and Health",
            {
                "fields": (
                    "daily_transaction_limit",
                    "monthly_volume_limit",
                    "is_healthy",
                    "health_note",
                    "last_used_at",
                    "last_health_check_at",
                )
            },
        ),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(GatewayWebhookConfig)
class GatewayWebhookConfigAdmin(admin.ModelAdmin):
    list_display = (
        "gateway",
        "signature_algorithm",
        "is_active",
        "total_events_received",
        "last_received_at",
    )
    list_filter = ("is_active", "signature_algorithm", "gateway__provider")
    search_fields = ("gateway__name", "gateway__provider", "webhook_url", "signature_header")
    readonly_fields = ("id", "created_at", "updated_at", "last_received_at", "total_events_received")
    ordering = ("gateway__name",)


@admin.register(PlatformPaymentSetting)
class PlatformPaymentSettingAdmin(admin.ModelAdmin):
    list_display = ("name", "default_currency", "allow_multi_currency", "default_payout_schedule", "automatic_payout_review")


@admin.register(PlatformCommissionRule)
class PlatformCommissionRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "gateway", "currency", "percentage_rate", "flat_fee", "priority", "is_active")
    list_filter = ("is_active", "currency", "gateway")
    search_fields = ("name", "subscription_plan", "country_code")


@admin.register(TenantPaymentSnapshot)
class TenantPaymentSnapshotAdmin(admin.ModelAdmin):
    list_display = ("business_name", "schema_name", "account_status", "kyb_status", "payout_enabled", "default_currency", "health_status", "last_synced_at")
    list_filter = ("account_status", "kyb_status", "payout_enabled", "health_status", "default_currency")
    search_fields = ("business_name", "schema_name")


@admin.register(TenantGatewaySnapshot)
class TenantGatewaySnapshotAdmin(admin.ModelAdmin):
    list_display = ("schema_name", "gateway_name", "mode", "status", "transaction_count", "transaction_volume", "is_healthy")
    list_filter = ("mode", "status", "gateway_provider", "is_healthy")
    search_fields = ("schema_name", "gateway_name", "gateway_provider")


@admin.register(PlatformTransactionIndex)
class PlatformTransactionIndexAdmin(admin.ModelAdmin):
    list_display = ("internal_reference", "schema_name", "amount", "currency", "status", "gateway_provider", "payment_mode", "paid_at")
    list_filter = ("status", "currency", "gateway_provider", "payment_mode", "is_flagged")
    search_fields = ("internal_reference", "order_number", "gateway_reference", "customer_email", "schema_name")


@admin.register(PlatformPayoutIndex)
class PlatformPayoutIndexAdmin(admin.ModelAdmin):
    list_display = ("payout_reference", "schema_name", "amount", "currency", "status", "bank_name", "requested_at")
    list_filter = ("status", "currency", "gateway_provider")
    search_fields = ("payout_reference", "schema_name", "bank_name", "gateway_transfer_reference")


@admin.register(PlatformRefundIndex)
class PlatformRefundIndexAdmin(admin.ModelAdmin):
    list_display = ("refund_reference", "schema_name", "amount", "currency", "status", "reason", "requested_at")
    list_filter = ("status", "currency", "reason")
    search_fields = ("refund_reference", "schema_name", "transaction_reference", "order_number")


@admin.register(PlatformDisputeIndex)
class PlatformDisputeIndexAdmin(admin.ModelAdmin):
    list_display = ("dispute_reference", "schema_name", "amount", "currency", "status", "reason", "opened_at")
    list_filter = ("status", "currency", "reason")
    search_fields = ("dispute_reference", "schema_name", "transaction_reference")
