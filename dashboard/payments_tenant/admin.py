from django.contrib import admin

from dashboard.payments_tenant.models import (
    BlocklistEntry,
    CardDetail,
    CommissionEntry,
    CommissionRule,
    Dispute,
    DisputeEvidence,
    FraudAssessment,
    FraudRule,
    PaymentIntent,
    PaymentMethodVaultToken,
    PayoutBatch,
    PayoutItem,
    PayoutRequest,
    PayoutTransfer,
    ReconciliationEntry,
    ReconciliationReport,
    Refund,
    RefundLineItem,
    SavedPaymentMethod,
    SupportedCurrency,
    TenantBalance,
    TenantBalanceTransaction,
    TenantBankAccount,
    TenantGatewayCredential,
    TenantGatewayMode,
    TenantPaymentProfile,
    Transaction,
    TransactionEvent,
    TransactionMetadata,
)


class TimestampedAdmin(admin.ModelAdmin):
    readonly_fields = ("id", "created_at", "updated_at")


class AppendOnlyAdmin(admin.ModelAdmin):
    readonly_fields = ("id", "created_at")


class SupportedCurrencyInline(admin.TabularInline):
    model = SupportedCurrency
    extra = 0
    fields = ("currency_code", "is_default", "is_enabled")
    show_change_link = True


class TenantGatewayModeInline(admin.TabularInline):
    model = TenantGatewayMode
    extra = 0
    fields = (
        "gateway",
        "mode",
        "status",
        "is_default",
        "checkout_label",
        "checkout_display_order",
    )
    readonly_fields = ("mode_switched_at",)
    show_change_link = True


class TenantBalanceInline(admin.TabularInline):
    model = TenantBalance
    extra = 0
    fields = ("currency", "available_balance", "pending_balance", "reserved_balance")
    show_change_link = True


@admin.register(TenantPaymentProfile)
class TenantPaymentProfileAdmin(TimestampedAdmin):
    list_display = (
        "business_name",
        "account_status",
        "kyb_status",
        "default_currency",
        "payout_enabled",
        "support_email",
        "updated_at",
    )
    list_filter = ("account_status", "kyb_status", "default_currency", "payout_enabled")
    search_fields = ("business_name", "support_email", "business_phone", "business_registration_number")
    inlines = (SupportedCurrencyInline, TenantGatewayModeInline, TenantBalanceInline)


@admin.register(TenantGatewayMode)
class TenantGatewayModeAdmin(TimestampedAdmin):
    list_display = (
        "payment_profile",
        "gateway",
        "mode",
        "status",
        "is_default",
        "checkout_display_order",
        "updated_at",
    )
    list_filter = ("mode", "status", "is_default", "gateway__provider")
    search_fields = ("payment_profile__business_name", "gateway__name", "checkout_label")


@admin.register(TenantGatewayCredential)
class TenantGatewayCredentialAdmin(TimestampedAdmin):
    list_display = (
        "payment_profile",
        "gateway",
        "label",
        "environment",
        "status",
        "validated_at",
        "updated_at",
    )
    list_filter = ("environment", "status", "gateway__provider")
    search_fields = ("payment_profile__business_name", "label", "gateway_business_name", "gateway_account_id")


@admin.register(Transaction)
class TransactionAdmin(TimestampedAdmin):
    list_display = (
        "internal_reference",
        "gateway_provider",
        "payment_mode",
        "amount",
        "currency",
        "status",
        "customer_email",
        "created_at",
    )
    list_filter = ("status", "payment_mode", "gateway_provider", "currency", "is_flagged")
    search_fields = ("internal_reference", "gateway_reference", "order_number", "customer_email")


@admin.register(Refund)
class RefundAdmin(TimestampedAdmin):
    list_display = (
        "refund_reference",
        "transaction",
        "amount",
        "currency",
        "status",
        "initiated_by_type",
        "processed_at",
    )
    list_filter = ("status", "initiated_by_type", "currency")
    search_fields = ("transaction__internal_reference", "gateway_refund_id", "reason", "customer_note")


@admin.register(Dispute)
class DisputeAdmin(TimestampedAdmin):
    list_display = (
        "dispute_reference",
        "transaction",
        "dispute_amount",
        "currency",
        "status",
        "evidence_deadline",
        "created_at",
    )
    list_filter = ("status", "currency")
    search_fields = ("transaction__internal_reference", "gateway_dispute_id", "reason_code", "customer_reason")


@admin.register(TenantBankAccount)
class TenantBankAccountAdmin(TimestampedAdmin):
    list_display = (
        "payment_profile",
        "account_name",
        "bank_name",
        "currency",
        "status",
        "is_primary",
        "is_verified",
        "updated_at",
    )
    list_filter = ("status", "is_primary", "currency")
    search_fields = ("payment_profile__business_name", "account_name", "bank_name", "account_number_masked")


@admin.register(PayoutRequest)
class PayoutRequestAdmin(TimestampedAdmin):
    list_display = (
        "payout_reference",
        "payment_profile",
        "amount",
        "currency",
        "status",
        "request_type",
        "requested_at",
    )
    list_filter = ("status", "request_type", "currency")
    search_fields = ("idempotency_key", "tenant_note", "bank_account__account_name", "bank_account__bank_name")


@admin.register(FraudRule)
class FraudRuleAdmin(TimestampedAdmin):
    list_display = ("name", "rule_type", "action", "is_active", "priority", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")


@admin.register(FraudAssessment)
class FraudAssessmentAdmin(TimestampedAdmin):
    list_display = (
        "transaction",
        "decision",
        "risk_score",
        "reviewer_decision",
        "is_proxy_ip",
        "created_at",
    )
    list_filter = ("decision", "reviewer_decision", "is_proxy_ip")
    search_fields = ("transaction__internal_reference", "payment_intent__gateway_intent_id")


@admin.register(ReconciliationReport)
class ReconciliationReportAdmin(TimestampedAdmin):
    list_display = (
        "report_date",
        "payment_profile",
        "gateway_provider",
        "currency",
        "status",
        "amount_discrepancy",
        "count_discrepancy",
    )
    list_filter = ("status", "gateway_provider", "currency", "report_date")
    search_fields = ("payment_profile__business_name", "gateway_provider", "gateway_settlement_id")


admin.site.register(CommissionRule, TimestampedAdmin)
admin.site.register(CommissionEntry, AppendOnlyAdmin)
admin.site.register(PaymentIntent, TimestampedAdmin)
admin.site.register(TransactionEvent, AppendOnlyAdmin)
admin.site.register(TransactionMetadata, TimestampedAdmin)
admin.site.register(CardDetail, TimestampedAdmin)
admin.site.register(SavedPaymentMethod, TimestampedAdmin)
admin.site.register(PaymentMethodVaultToken, TimestampedAdmin)
admin.site.register(RefundLineItem, TimestampedAdmin)
admin.site.register(DisputeEvidence, TimestampedAdmin)
admin.site.register(TenantBalance, TimestampedAdmin)
admin.site.register(TenantBalanceTransaction, AppendOnlyAdmin)
admin.site.register(PayoutBatch, TimestampedAdmin)
admin.site.register(PayoutItem, TimestampedAdmin)
admin.site.register(PayoutTransfer, TimestampedAdmin)
admin.site.register(BlocklistEntry, TimestampedAdmin)
admin.site.register(ReconciliationEntry, AppendOnlyAdmin)
