from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone
from django_tenants.utils import get_public_schema_name, get_tenant_model, schema_context

from system.core.models import Shop
from system.system_pay.models import (
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
from system.system_pay.utils import (
    SystemGatewayResult,
    get_all_platform_credentials,
    get_enabled_gateways,
    get_gateway_webhook_config,
    get_platform_credential,
    get_system_payment_stats,
    register_new_gateway_definition,
    validate_platform_credential_health,
)


@dataclass
class PlatformPaymentActionResult:
    success: bool = False
    message: str = ""
    errors: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


def get_or_create_platform_payment_setting() -> PlatformPaymentSetting:
    setting, _ = PlatformPaymentSetting.objects.get_or_create(name="default")
    return setting


def get_platform_payment_overview() -> dict:
    return {
        "tenant_count": TenantPaymentSnapshot.objects.count(),
        "gateway_count": PaymentGatewayDefinition.objects.filter(is_enabled=True).count(),
        "credential_count": PlatformGatewayCredential.objects.filter(is_active=True).count(),
        "transaction_count": PlatformTransactionIndex.objects.count(),
        "payout_count": PlatformPayoutIndex.objects.count(),
        "refund_count": PlatformRefundIndex.objects.count(),
        "dispute_count": PlatformDisputeIndex.objects.count(),
        "transaction_volume": PlatformTransactionIndex.objects.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
    }


def _tenant_shop_lookup(schema_name: str) -> Shop:
    return Shop.objects.get(schema_name=schema_name)


def _health_status(*, account_status: str, kyb_status: str, active_gateway_count: int) -> str:
    if account_status == "suspended":
        return "critical"
    if account_status == "restricted":
        return "warning"
    if active_gateway_count <= 0:
        return "warning"
    if kyb_status in {"under_review", "submitted"}:
        return "attention"
    if account_status == "active":
        return "healthy"
    return "unknown"


@transaction.atomic
def sync_tenant_payment_snapshot(shop: Shop) -> TenantPaymentSnapshot | None:
    with schema_context(shop.schema_name):
        from dashboard.payments_tenant.models import (
            Dispute,
            PayoutRequest,
            Refund,
            TenantBalance,
            TenantGatewayMode,
            TenantPaymentProfile,
            Transaction,
        )

        profile = TenantPaymentProfile.objects.first()
        if profile is None:
            snapshot, _ = TenantPaymentSnapshot.objects.update_or_create(
                schema_name=shop.schema_name,
                defaults={
                    "shop": shop,
                    "business_name": shop.name,
                    "last_synced_at": timezone.now(),
                    "health_status": "missing_profile",
                },
            )
            TenantGatewaySnapshot.objects.filter(schema_name=shop.schema_name).delete()
            return snapshot

        balances = TenantBalance.objects.all()
        default_balance = balances.filter(currency=profile.default_currency).first() or balances.first()
        gateway_modes = list(TenantGatewayMode.objects.select_related("gateway").all())
        transaction_qs = Transaction.objects.all()
        transaction_count = transaction_qs.count()
        transaction_volume = transaction_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        last_transaction_at = transaction_qs.order_by("-paid_at", "-created_at").values_list("paid_at", flat=True).first()

        snapshot, _ = TenantPaymentSnapshot.objects.update_or_create(
            schema_name=shop.schema_name,
            defaults={
                "shop": shop,
                "business_name": profile.business_name or shop.name,
                "account_status": profile.account_status,
                "kyb_status": profile.kyb_status,
                "payout_enabled": profile.payout_enabled,
                "default_currency": profile.default_currency,
                "available_balance": getattr(default_balance, "available_balance", Decimal("0.00")),
                "pending_balance": getattr(default_balance, "pending_balance", Decimal("0.00")),
                "reserved_balance": getattr(default_balance, "reserved_balance", Decimal("0.00")),
                "total_transaction_count": transaction_count,
                "total_transaction_volume": transaction_volume,
                "gateway_count": len(gateway_modes),
                "active_gateway_count": sum(1 for mode in gateway_modes if mode.status == mode.ActivationStatus.ACTIVE),
                "direct_gateway_count": sum(1 for mode in gateway_modes if mode.mode == mode.PaymentMode.DIRECT),
                "platform_gateway_count": sum(1 for mode in gateway_modes if mode.mode == mode.PaymentMode.PLATFORM),
                "last_transaction_at": last_transaction_at,
                "health_status": _health_status(
                    account_status=profile.account_status,
                    kyb_status=profile.kyb_status,
                    active_gateway_count=sum(1 for mode in gateway_modes if mode.status == mode.ActivationStatus.ACTIVE),
                ),
                "last_synced_at": timezone.now(),
            },
        )

        existing_gateway_keys = set()
        for mode in gateway_modes:
            existing_gateway_keys.add(mode.gateway.provider)
            gateway_transactions = transaction_qs.filter(gateway_provider=mode.gateway.provider)
            TenantGatewaySnapshot.objects.update_or_create(
                schema_name=shop.schema_name,
                gateway_provider=mode.gateway.provider,
                defaults={
                    "shop": shop,
                    "gateway": mode.gateway,
                    "gateway_name": mode.gateway.name,
                    "mode": mode.mode,
                    "status": mode.status,
                    "currency": (mode.accepted_currencies or [profile.default_currency])[0],
                    "is_default": mode.is_default,
                    "is_healthy": mode.status == mode.ActivationStatus.ACTIVE,
                    "transaction_count": gateway_transactions.count(),
                    "transaction_volume": gateway_transactions.aggregate(total=Sum("amount"))["total"] or Decimal("0.00"),
                    "last_transaction_at": gateway_transactions.order_by("-paid_at").values_list("paid_at", flat=True).first(),
                    "notes": mode.review_notes,
                    "last_synced_at": timezone.now(),
                },
            )
        TenantGatewaySnapshot.objects.filter(schema_name=shop.schema_name).exclude(
            gateway_provider__in=existing_gateway_keys
        ).delete()

        existing_transaction_ids = set()
        for txn in transaction_qs.iterator():
            existing_transaction_ids.add(txn.id)
            PlatformTransactionIndex.objects.update_or_create(
                transaction_id=txn.id,
                defaults={
                    "shop": shop,
                    "schema_name": shop.schema_name,
                    "internal_reference": txn.internal_reference,
                    "order_id": txn.order_id,
                    "order_number": txn.order_number,
                    "gateway_transaction_id": txn.gateway_transaction_id,
                    "gateway_reference": txn.gateway_reference,
                    "amount": txn.amount,
                    "currency": txn.currency,
                    "status": txn.status,
                    "payment_mode": txn.payment_mode,
                    "gateway_provider": txn.gateway_provider,
                    "customer_email": txn.customer_email,
                    "customer_name": txn.customer_name,
                    "payment_method_type": txn.payment_method_type,
                    "paid_at": txn.paid_at,
                    "created_at_source": txn.created_at,
                    "is_flagged": txn.is_flagged,
                    "metadata": txn.mode_snapshot,
                    "last_synced_at": timezone.now(),
                },
            )
        PlatformTransactionIndex.objects.filter(schema_name=shop.schema_name).exclude(transaction_id__in=existing_transaction_ids).delete()

        payout_ids = set()
        for payout in PayoutRequest.objects.select_related("bank_account").all().iterator():
            payout_ids.add(payout.id)
            PlatformPayoutIndex.objects.update_or_create(
                payout_request_id=payout.id,
                defaults={
                    "shop": shop,
                    "schema_name": shop.schema_name,
                    "payout_reference": payout.payout_reference,
                    "amount": payout.amount,
                    "currency": payout.currency,
                    "status": payout.status,
                    "bank_name": payout.bank_account.bank_name,
                    "bank_account_masked": payout.bank_account.account_number_masked,
                    "gateway_provider": payout.bank_account.gateway_provider,
                    "gateway_transfer_reference": payout.gateway_transfer_reference,
                    "requested_at": payout.requested_at,
                    "approved_at": payout.approved_at,
                    "completed_at": payout.completed_at,
                    "metadata": {"request_type": payout.request_type},
                    "last_synced_at": timezone.now(),
                },
            )
        PlatformPayoutIndex.objects.filter(schema_name=shop.schema_name).exclude(payout_request_id__in=payout_ids).delete()

        refund_ids = set()
        for refund in Refund.objects.select_related("transaction").all().iterator():
            refund_ids.add(refund.id)
            PlatformRefundIndex.objects.update_or_create(
                refund_id=refund.id,
                defaults={
                    "shop": shop,
                    "schema_name": shop.schema_name,
                    "refund_reference": refund.refund_reference,
                    "transaction_reference": refund.transaction.internal_reference,
                    "order_number": refund.transaction.order_number,
                    "amount": refund.amount,
                    "currency": refund.currency,
                    "status": refund.status,
                    "reason": refund.reason,
                    "requested_at": refund.created_at,
                    "completed_at": refund.processed_at,
                    "metadata": {"gateway_refund_id": refund.gateway_refund_id},
                    "last_synced_at": timezone.now(),
                },
            )
        PlatformRefundIndex.objects.filter(schema_name=shop.schema_name).exclude(refund_id__in=refund_ids).delete()

        dispute_ids = set()
        for dispute in Dispute.objects.select_related("transaction").all().iterator():
            dispute_ids.add(dispute.id)
            PlatformDisputeIndex.objects.update_or_create(
                dispute_id=dispute.id,
                defaults={
                    "shop": shop,
                    "schema_name": shop.schema_name,
                    "dispute_reference": dispute.dispute_reference,
                    "transaction_reference": dispute.transaction.internal_reference,
                    "amount": dispute.dispute_amount,
                    "currency": dispute.currency,
                    "status": dispute.status,
                    "reason": dispute.reason,
                    "opened_at": dispute.opened_at or dispute.created_at,
                    "evidence_deadline": dispute.evidence_deadline,
                    "resolved_at": dispute.resolved_at,
                    "metadata": {"gateway_dispute_id": dispute.gateway_dispute_id},
                    "last_synced_at": timezone.now(),
                },
            )
        PlatformDisputeIndex.objects.filter(schema_name=shop.schema_name).exclude(dispute_id__in=dispute_ids).delete()

        return snapshot


def rebuild_payment_projections(*, schema_name: str | None = None) -> int:
    queryset = Shop.objects.exclude(schema_name=get_public_schema_name())
    if schema_name:
        queryset = queryset.filter(schema_name=schema_name)
    synced = 0
    for shop in queryset:
        try:
            sync_tenant_payment_snapshot(shop)
            synced += 1
        except (OperationalError, ProgrammingError):
            continue
    return synced


def update_tenant_payment_account_status(*, schema_name: str, account_status: str, reason: str = "") -> PlatformPaymentActionResult:
    shop = _tenant_shop_lookup(schema_name)
    with schema_context(schema_name):
        from dashboard.payments_tenant.models import TenantPaymentProfile

        profile = TenantPaymentProfile.objects.first()
        if profile is None:
            return PlatformPaymentActionResult(success=False, errors=["Tenant payment profile does not exist."])
        profile.account_status = account_status
        profile.restriction_reason = reason
        profile.save(update_fields=["account_status", "restriction_reason", "updated_at"])
    sync_tenant_payment_snapshot(shop)
    return PlatformPaymentActionResult(success=True, message="Tenant payment status updated.")


def set_tenant_payout_enabled(*, schema_name: str, enabled: bool) -> PlatformPaymentActionResult:
    shop = _tenant_shop_lookup(schema_name)
    with schema_context(schema_name):
        from dashboard.payments_tenant.models import TenantPaymentProfile

        profile = TenantPaymentProfile.objects.first()
        if profile is None:
            return PlatformPaymentActionResult(success=False, errors=["Tenant payment profile does not exist."])
        profile.payout_enabled = enabled
        profile.save(update_fields=["payout_enabled", "updated_at"])
    sync_tenant_payment_snapshot(shop)
    return PlatformPaymentActionResult(success=True, message="Tenant payout setting updated.")


def review_tenant_direct_mode(*, schema_name: str, gateway_provider: str, approved: bool, notes: str = "") -> PlatformPaymentActionResult:
    shop = _tenant_shop_lookup(schema_name)
    with schema_context(schema_name):
        from dashboard.payments_tenant.models import TenantGatewayMode

        mode = TenantGatewayMode.objects.select_related("gateway").filter(gateway__provider=gateway_provider).first()
        if mode is None:
            return PlatformPaymentActionResult(success=False, errors=["Tenant gateway mode not found."])
        mode.review_notes = notes
        mode.review_approved_at = timezone.now() if approved else None
        mode.status = mode.ActivationStatus.ACTIVE if approved else mode.ActivationStatus.SUSPENDED
        mode.save(update_fields=["review_notes", "review_approved_at", "status", "updated_at"])
    sync_tenant_payment_snapshot(shop)
    return PlatformPaymentActionResult(success=True, message="Tenant direct mode review saved.")


__all__ = [
    "SystemGatewayResult",
    "PlatformPaymentActionResult",
    "get_enabled_gateways",
    "get_platform_credential",
    "get_all_platform_credentials",
    "get_gateway_webhook_config",
    "validate_platform_credential_health",
    "get_system_payment_stats",
    "register_new_gateway_definition",
    "get_platform_payment_overview",
    "get_or_create_platform_payment_setting",
    "sync_tenant_payment_snapshot",
    "rebuild_payment_projections",
    "update_tenant_payment_account_status",
    "set_tenant_payout_enabled",
    "review_tenant_direct_mode",
]
