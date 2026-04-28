from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from dashboard.payments_tenant.models import Refund, Transaction, TransactionEvent
from dashboard.payments_tenant.services.dashboard import (
    get_balance_overview,
    get_gateway_status_overview,
    get_payments_attention_queue,
    get_payments_dashboard_kpis,
    get_payments_health_checks,
    get_recent_transactions,
)
from dashboard.payments_tenant.services.gateway import (
    activate_gateway_mode,
    get_active_gateway_mode,
    get_default_gateway,
    list_tenant_gateways,
    resolve_gateway_for_checkout,
    submit_direct_credentials,
    switch_tenant_to_direct_mode,
    switch_tenant_to_platform_mode,
    validate_tenant_credentials,
)
from dashboard.payments_tenant.services.intent_transactions import (
    calculate_commission,
    credit_tenant_balance,
    debit_tenant_balance,
    flag_transaction,
    get_balance_ledger,
    get_balance_summary,
    get_commission_summary,
    get_order_transactions,
    get_tenant_balance,
    get_transaction_timeline,
    unflag_transaction,
)
from dashboard.payments_tenant.services.payout_fraud import (
    add_bank_account,
    assess_fraud_risk,
    check_blocklist,
    check_payout_eligibility,
    get_fraud_queue,
    get_payout_history,
    request_payout as _request_payout_service,
)
from dashboard.payments_tenant.services.reconciliation import (
    detect_discrepancies,
    generate_daily_reconciliation,
    get_unreconciled_transactions,
    mark_reconciliation_resolved,
)


@transaction.atomic
def request_refund(
    *,
    transaction: Transaction,
    amount: Decimal,
    reason: str,
    reason_detail: str = "",
    customer_note: str = "",
    internal_note: str = "",
    initiated_by=None,
):
    if amount <= 0:
        raise ValueError("Refund amount must be greater than zero.")
    if amount > transaction.refundable_amount:
        raise ValueError("Refund amount exceeds the refundable balance for this transaction.")

    commission_ratio = Decimal("0.00")
    tenant_net_ratio = Decimal("0.00")
    if transaction.amount:
        commission_ratio = transaction.platform_commission / transaction.amount
        tenant_net_ratio = transaction.tenant_net / transaction.amount

    commission_reversed = (amount * commission_ratio).quantize(Decimal("0.01"))
    tenant_net_refunded = (amount * tenant_net_ratio).quantize(Decimal("0.01"))

    refund = Refund.objects.create(
        transaction=transaction,
        payment_profile=transaction.payment_profile,
        amount=amount,
        currency=transaction.currency,
        commission_reversed=commission_reversed,
        tenant_net_refunded=tenant_net_refunded,
        status=Refund.RefundStatus.SUCCESS,
        reason=reason,
        reason_detail=reason_detail,
        customer_note=customer_note,
        internal_note=internal_note,
        processed_at=timezone.now(),
        initiated_by=initiated_by,
        initiated_by_type="staff",
        gateway_refund_id=f"refund_{str(transaction.id).replace('-', '')[:12]}",
    )

    transaction.amount_refunded = (transaction.amount_refunded + amount).quantize(Decimal("0.01"))
    transaction.is_refunded = transaction.amount_refunded >= transaction.amount
    transaction.is_partially_refunded = not transaction.is_refunded and transaction.amount_refunded > 0
    transaction.save(
        update_fields=["amount_refunded", "is_refunded", "is_partially_refunded", "updated_at"]
    )

    if transaction.payment_mode == "platform" and tenant_net_refunded > 0:
        debit_tenant_balance(
            payment_profile=transaction.payment_profile,
            amount=tenant_net_refunded,
            currency=transaction.currency,
            transaction_type="refund_debit",
            description=f"Refund {refund.refund_reference} for {transaction.internal_reference}",
            source_transaction_id=transaction.id,
            source_refund_id=refund.id,
            order_id=transaction.order_id,
            order_number=transaction.order_number,
            performed_by=initiated_by,
        )

    TransactionEvent.objects.create(
        transaction=transaction,
        event_type=TransactionEvent.EventType.REFUND_PROCESSED,
        from_status=transaction.status,
        to_status=transaction.status,
        detail=f"Refund processed for {amount} {transaction.currency}.",
        source="dashboard",
        performed_by=initiated_by,
    )

    return refund


@transaction.atomic
def request_payout(
    *,
    payment_profile,
    bank_account,
    amount,
    narration="",
    tenant_note="",
    requested_by=None,
):
    result = _request_payout_service(
        payment_profile=payment_profile,
        amount=amount,
        currency=bank_account.currency or payment_profile.payout_currency,
        bank_account_id=str(bank_account.id),
        narration=narration,
        tenant_note=tenant_note,
        actor=requested_by,
    )
    if not result.success:
        raise ValueError("; ".join(result.errors) or result.message or "Payout request failed.")

    from dashboard.payments_tenant.models import PayoutRequest

    return PayoutRequest.objects.get(id=result.payout_request_id)


@transaction.atomic
def cancel_payout_request(*, payout, cancelled_by=None):
    if payout.status != payout.RequestStatus.PENDING:
        raise ValueError("Only pending payout requests can be cancelled.")

    credit_tenant_balance(
        payment_profile=payout.payment_profile,
        amount=payout.amount,
        currency=payout.currency,
        transaction_type="payout_reversal",
        description=f"Payout {payout.payout_reference} cancelled by tenant.",
        source_payout_id=payout.id,
        performed_by=cancelled_by,
    )

    payout.status = payout.RequestStatus.CANCELLED
    payout.reviewed_by = cancelled_by
    payout.reviewed_at = timezone.now()
    payout.review_note = "Cancelled by tenant."
    payout.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "updated_at"])
    return payout
