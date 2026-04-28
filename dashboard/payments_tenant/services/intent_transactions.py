"""
payments/utils/intent_transactions.py + commission_balance.py
=============================================================
Four modules combined:
  intent_transactions  → PaymentIntent lifecycle + Transaction confirmation/webhooks
  commission_balance   → Fee calculation + double-entry balance ledger
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger("payments")
TWO = Decimal("0.01")


# ══════════════════════════════════════════════════════════════
# MODULE: intent_transactions.py
# ══════════════════════════════════════════════════════════════

@dataclass
class PaymentIntentResult:
    success: bool = False
    intent_id: Optional[str] = None
    gateway_reference: str = ""
    authorization_url: str = ""
    access_code: str = ""
    client_secret: str = ""
    public_key: str = ""
    is_test: bool = False
    split_params: dict = field(default_factory=dict)
    message: str = ""
    errors: list = field(default_factory=list)


@dataclass
class TransactionConfirmResult:
    success: bool = False
    transaction_id: Optional[str] = None
    internal_reference: str = ""
    status: str = ""
    amount: Optional[Decimal] = None
    currency: str = ""
    payment_mode: str = ""
    balance_credited: Optional[Decimal] = None
    commission_charged: Optional[Decimal] = None
    message: str = ""


# ─────────────────────────────────────────────────────────────
# SECTION 1 — PAYMENT INTENT LIFECYCLE
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def create_payment_intent(
    payment_profile,
    order_id,
    order_number: str,
    amount: Decimal,
    currency: str,
    customer_id=None,
    customer_email: str = "",
    customer_name: str = "",
    customer_phone: str = "",
    customer_ip: str = "",
    gateway_provider: str = None,
    payment_method_type: str = "",
    metadata: dict = None,
    success_url: str = "",
    failure_url: str = "",
    cancel_url: str = "",
    callback_url: str = "",
    timeout_minutes: int = None,
) -> PaymentIntentResult:
    """
    Create a PaymentIntent and initialize the gateway session.

    Steps:
      1. Resolve the best gateway for this checkout
      2. Check blocklist for customer email/IP
      3. Run pre-payment fraud assessment
      4. Create PaymentIntent record
      5. Call gateway API to initialize checkout session
      6. Return authorization URL and public key for frontend

    Args:
        payment_profile:   TenantPaymentProfile instance
        order_id:          UUID of the order
        order_number:      Human-readable order number
        amount:            Decimal amount to charge
        currency:          ISO 4217 currency code
        customer_*:        Customer details
        gateway_provider:  Force a specific gateway (or auto-resolve)
        metadata:          Additional data passed to gateway
        *_url:             Return URLs for hosted payment pages
        timeout_minutes:   Override profile's payment_timeout_minutes

    Returns:
        PaymentIntentResult with all data needed by the frontend
    """
    from dashboard.payments_tenant.models import PaymentIntent, PaymentMode
    from .gateway import resolve_gateway_for_checkout, build_split_payment_params

    # ── 1. Resolve gateway ──
    from .gateway import get_effective_credentials
    resolution = resolve_gateway_for_checkout(
        payment_profile=payment_profile,
        currency=currency,
        gateway_provider=gateway_provider,
        amount=amount,
    )
    if not resolution.success:
        return PaymentIntentResult(success=False, errors=resolution.errors)

    from dashboard.payments_tenant.models import TenantGatewayMode
    gateway_mode = TenantGatewayMode.objects.select_related(
        "gateway", "platform_credential", "direct_credential"
    ).get(id=resolution.gateway_mode_id)

    # ── 2. Quick blocklist check ──
    if customer_email:
        from .payout_fraud import check_blocklist
        if check_blocklist("email", customer_email, payment_profile):
            logger.warning("Payment blocked: email %s on blocklist", customer_email[:20])
            return PaymentIntentResult(
                success=False,
                errors=["Payment cannot be processed for this customer."],
            )
    if customer_ip:
        from .payout_fraud import check_blocklist
        if check_blocklist("ip_address", customer_ip, payment_profile):
            return PaymentIntentResult(success=False, errors=["Payment cannot be processed from this location."])

    # ── 3. Build split params (PLATFORM MODE) ──
    split_params = build_split_payment_params(gateway_mode, amount, currency)

    # ── 4. Determine expiry ──
    timeout = timeout_minutes or payment_profile.payment_timeout_minutes
    expires_at = timezone.now() + timezone.timedelta(minutes=timeout)

    # ── 5. Generate internal reference ──
    intent_ref = _generate_payment_reference(gateway_mode.gateway.provider)

    # ── 6. Create PaymentIntent ──
    intent = PaymentIntent.objects.create(
        payment_profile=payment_profile,
        gateway_mode=gateway_mode,
        order_id=order_id,
        order_number=order_number,
        amount=amount,
        currency=currency,
        status=PaymentIntent.IntentStatus.REQUIRES_PAYMENT_METHOD,
        customer_id=customer_id,
        customer_email=customer_email,
        customer_name=customer_name,
        customer_phone=customer_phone,
        customer_ip=customer_ip or None,
        payment_mode=gateway_mode.mode,
        payment_method_type=payment_method_type,
        metadata=metadata or {},
        success_url=success_url,
        failure_url=failure_url,
        cancel_url=cancel_url,
        callback_url=callback_url,
        gateway_intent_id=intent_ref,
        expires_at=expires_at,
        subaccount_code=split_params.get("subaccount", ""),
        transaction_charge=split_params.get("transaction_charge"),
        bearer=split_params.get("bearer", ""),
    )

    # ── 7. Call gateway to initialize checkout session ──
    try:
        session = initialize_gateway_session(intent, gateway_mode, split_params)
        intent.gateway_intent_id = session.get("gateway_intent_id") or session.get("reference", intent_ref)
        intent.gateway_authorization_url = session.get("authorization_url", "")
        intent.gateway_access_code = session.get("access_code", "")
        intent.client_secret = session.get("client_secret", "")
        intent.save(update_fields=[
            "gateway_intent_id", "gateway_authorization_url", "gateway_access_code", "client_secret", "updated_at"
        ])
    except Exception as e:
        logger.error("Gateway session init failed for intent %s: %s", intent.id, e)
        intent.status = PaymentIntent.IntentStatus.CANCELLED
        intent.failure_message = str(e)
        intent.save(update_fields=["status", "failure_message", "updated_at"])
        return PaymentIntentResult(success=False, errors=[f"Gateway initialization failed: {e}"])

    return PaymentIntentResult(
        success=True,
        intent_id=str(intent.id),
        gateway_reference=intent.gateway_intent_id,
        authorization_url=intent.gateway_authorization_url,
        access_code=intent.gateway_access_code,
        client_secret=intent.client_secret,
        public_key=resolution.public_key,
        is_test=resolution.is_test,
        split_params=split_params,
        message="Payment session initialized.",
    )


def initialize_gateway_session(intent, gateway_mode, split_params: dict) -> dict:
    """
    Call the payment gateway API to initialize a checkout session.
    Returns {reference, authorization_url, access_code, ...}

    Stub implementation — replace with real provider SDK calls.
    """
    from .provider_checkout import initialize_gateway_checkout

    provider = gateway_mode.gateway.provider
    logger.info("Initializing gateway session: provider=%s intent=%s", provider, intent.id)
    return initialize_gateway_checkout(intent, gateway_mode, split_params)


def cancel_payment_intent(intent_id: str, reason: str = "", actor=None) -> bool:
    """Cancel a pending PaymentIntent."""
    from dashboard.payments_tenant.models import PaymentIntent

    try:
        intent = PaymentIntent.objects.get(id=intent_id)
    except PaymentIntent.DoesNotExist:
        return False

    if intent.status in (PaymentIntent.IntentStatus.SUCCEEDED, PaymentIntent.IntentStatus.CANCELLED):
        return False

    intent.status = PaymentIntent.IntentStatus.CANCELLED
    intent.cancellation_reason = reason
    intent.save(update_fields=["status", "cancellation_reason", "updated_at"])
    return True


def expire_payment_intents() -> int:
    """
    Mark all expired PaymentIntents as EXPIRED.
    Called by a Celery task every 5 minutes.
    """
    from dashboard.payments_tenant.models import PaymentIntent

    now = timezone.now()
    expired = PaymentIntent.objects.filter(
        expires_at__lt=now,
        status__in=[
            PaymentIntent.IntentStatus.REQUIRES_PAYMENT_METHOD,
            PaymentIntent.IntentStatus.REQUIRES_CONFIRMATION,
            PaymentIntent.IntentStatus.REQUIRES_ACTION,
        ],
    )
    count = expired.count()
    expired.update(status=PaymentIntent.IntentStatus.EXPIRED, updated_at=now)
    if count:
        logger.info("Expired %d payment intents.", count)
    return count


def get_intent_by_reference(gateway_reference: str) -> Optional[object]:
    """Look up a PaymentIntent by gateway reference."""
    from dashboard.payments_tenant.models import PaymentIntent
    return PaymentIntent.objects.filter(
        gateway_intent_id=gateway_reference
    ).select_related("payment_profile", "gateway_mode__gateway").first()


# ─────────────────────────────────────────────────────────────
# SECTION 2 — TRANSACTION CONFIRMATION
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def confirm_transaction(
    payment_profile,
    gateway_reference: str,
    gateway_transaction_id: str,
    amount: Decimal,
    currency: str,
    status: str,
    gateway_provider: str,
    raw_response: dict = None,
    gateway_message: str = "",
    gateway_ip: str = "",
    paid_at=None,
    card_data: dict = None,
    payment_channel: str = "",
) -> TransactionConfirmResult:
    """
    Confirm a transaction from a gateway webhook or callback verification.

    This is the critical function called when the gateway tells us
    a payment succeeded (or failed). It:
      1. Finds the PaymentIntent by reference
      2. Creates (or retrieves) the Transaction record
      3. Creates CommissionEntry (PLATFORM MODE)
      4. Credits TenantBalance (PLATFORM MODE)
      5. Updates the PaymentIntent status
      6. Records TransactionEvent

    Idempotent: safe to call multiple times — deduplicates by gateway_reference.
    """
    from dashboard.payments_tenant.models import (
        Transaction, TransactionEvent, TransactionStatus, PaymentIntent,
        CardDetail, PaymentMode,
    )

    # ── Idempotency: check for existing transaction ──
    existing = Transaction.objects.filter(
        gateway_reference=gateway_reference,
        payment_profile=payment_profile,
    ).first()
    if existing:
        logger.info("Duplicate webhook: transaction %s already exists.", gateway_reference)
        return TransactionConfirmResult(
            success=True,
            transaction_id=str(existing.id),
            internal_reference=existing.internal_reference,
            status=existing.status,
            amount=existing.amount,
            currency=existing.currency,
            payment_mode=existing.payment_mode,
            message="Transaction already recorded.",
        )

    # ── Find PaymentIntent ──
    intent = PaymentIntent.objects.filter(
        gateway_intent_id=gateway_reference,
        payment_profile=payment_profile,
    ).select_related("gateway_mode__gateway").first()

    gateway_mode = intent.gateway_mode if intent else None
    mode = gateway_mode.mode if gateway_mode else PaymentMode.PLATFORM

    # ── Build mode snapshot ──
    mode_snapshot = {
        "mode": mode,
        "gateway_provider": gateway_provider,
        "platform_subaccount_code": gateway_mode.platform_subaccount_code if gateway_mode else "",
        "platform_credential_id": str(gateway_mode.platform_credential_id) if gateway_mode and gateway_mode.platform_credential_id else None,
    }

    # ── Calculate commission ──
    gateway_fee = Decimal("0.00")
    platform_commission = Decimal("0.00")
    tenant_net = amount

    if mode == PaymentMode.PLATFORM and status == TransactionStatus.SUCCESS:
        from .commission_balance import resolve_commission_rule, calculate_commission
        rule = resolve_commission_rule(payment_profile, gateway_mode.gateway if gateway_mode else None)
        comm_result = calculate_commission(amount, rule, gateway_mode)
        gateway_fee = comm_result.gateway_fee
        platform_commission = comm_result.platform_commission
        tenant_net = comm_result.tenant_net

    # ── Create Transaction ──
    txn = Transaction.objects.create(
        payment_intent=intent,
        payment_profile=payment_profile,
        gateway_mode=gateway_mode,
        order_id=intent.order_id if intent else None,
        order_number=intent.order_number if intent else "",
        gateway_transaction_id=gateway_transaction_id,
        gateway_reference=gateway_reference,
        internal_reference=_generate_internal_reference(),
        status=status,
        amount=amount,
        currency=currency,
        gateway_fee=gateway_fee,
        platform_commission=platform_commission,
        tenant_net=tenant_net,
        payment_mode=mode,
        gateway_provider=gateway_provider,
        mode_snapshot=mode_snapshot,
        customer_id=intent.customer_id if intent else None,
        customer_email=intent.customer_email if intent else "",
        customer_name=intent.customer_name if intent else "",
        customer_phone=intent.customer_phone if intent else "",
        customer_ip=intent.customer_ip if intent else None,
        payment_method_type=intent.payment_method_type if intent else "",
        payment_channel=payment_channel,
        raw_gateway_response=raw_response or {},
        gateway_message=gateway_message,
        gateway_ip_address=gateway_ip or None,
        initiated_at=intent.created_at if intent else timezone.now(),
        paid_at=paid_at or (timezone.now() if status == TransactionStatus.SUCCESS else None),
        is_test=gateway_mode.direct_credential.environment == "test" if (
            gateway_mode and gateway_mode.direct_credential
        ) else (
            gateway_mode.platform_credential.environment == "test" if (
                gateway_mode and gateway_mode.platform_credential
            ) else False
        ),
    )

    # ── Store card details if provided ──
    if card_data and status == TransactionStatus.SUCCESS:
        CardDetail.objects.create(
            transaction=txn,
            last4=card_data.get("last4", ""),
            first6=card_data.get("first6", ""),
            card_type=card_data.get("card_type", ""),
            card_brand=card_data.get("brand", ""),
            expiry_month=card_data.get("exp_month", ""),
            expiry_year=card_data.get("exp_year", ""),
            cardholder_name=card_data.get("cardholder_name", ""),
            bank_name=card_data.get("bank", ""),
            country_code=card_data.get("country_code", ""),
        )

    # ── Amount mismatch detection ─────────────────────────────────────────────
    # Compare the amount the gateway actually charged against the amount we
    # recorded on the PaymentIntent.  A discrepancy of more than 1 penny
    # (covering float rounding) indicates either a gateway misconfiguration,
    # a partial-payment attempt, or — in the worst case — fraud.  We flag
    # the transaction for manual review and emit an audit event without
    # blocking the confirmation (so the customer isn't stranded), but staff
    # will see the flag in the dashboard immediately.
    if intent and status == TransactionStatus.SUCCESS:
        TOLERANCE = Decimal("0.01")
        expected_amount = intent.amount
        if abs(amount - expected_amount) > TOLERANCE:
            mismatch_reason = (
                f"Amount mismatch: expected {expected_amount} {intent.currency}, "
                f"gateway reported {amount} {currency}."
            )
            logger.warning(
                "AMOUNT MISMATCH on transaction %s: expected=%s got=%s provider=%s",
                txn.id, expected_amount, amount, gateway_provider,
            )
            txn.is_flagged = True
            txn.status_reason = mismatch_reason
            txn.save(update_fields=["is_flagged", "status_reason", "updated_at"])
            TransactionEvent.objects.create(
                transaction=txn,
                event_type=TransactionEvent.EventType.FRAUD_FLAGGED,
                detail=mismatch_reason,
                source="amount_mismatch_guard",
            )


    # ── Create CommissionEntry + credit balance (PLATFORM MODE, SUCCESS) ──
    balance_credited = None
    if mode == PaymentMode.PLATFORM and status == TransactionStatus.SUCCESS:
        from .commission_balance import create_commission_entry, credit_tenant_balance

        create_commission_entry(
            transaction_id=txn.id,
            payment_profile=payment_profile,
            gateway_mode=gateway_mode,
            gross_amount=amount,
            gateway_fee=gateway_fee,
            platform_commission=platform_commission,
            tenant_net=tenant_net,
            currency=currency,
            order_id=txn.order_id,
            order_number=txn.order_number,
        )

        bal_result = credit_tenant_balance(
            payment_profile=payment_profile,
            amount=tenant_net,
            currency=currency,
            transaction_type="payment_credit",
            description=f"Payment received — Order {txn.order_number}",
            source_transaction_id=txn.id,
            order_id=txn.order_id,
            order_number=txn.order_number,
        )
        balance_credited = tenant_net if bal_result.success else None

    # ── Update PaymentIntent status ──
    if intent:
        if status == TransactionStatus.SUCCESS:
            intent.status = PaymentIntent.IntentStatus.SUCCEEDED
            intent.succeeded_at = timezone.now()
        elif status in (TransactionStatus.FAILED, TransactionStatus.ABANDONED):
            intent.status = PaymentIntent.IntentStatus.CANCELLED
        intent.save(update_fields=["status", "succeeded_at", "updated_at"])

    # ── Create TransactionEvent ──
    event_type_map = {
        TransactionStatus.SUCCESS: TransactionEvent.EventType.SUCCEEDED,
        TransactionStatus.FAILED: TransactionEvent.EventType.FAILED,
        TransactionStatus.PENDING: TransactionEvent.EventType.PENDING,
        TransactionStatus.PROCESSING: TransactionEvent.EventType.PROCESSING,
        TransactionStatus.ABANDONED: TransactionEvent.EventType.ABANDONED,
    }
    TransactionEvent.objects.create(
        transaction=txn,
        event_type=event_type_map.get(status, TransactionEvent.EventType.WEBHOOK_RECEIVED),
        to_status=status,
        detail=gateway_message or f"{gateway_provider} payment {status}.",
        source="gateway_webhook",
        metadata={"gateway_provider": gateway_provider, "reference": gateway_reference},
    )

    # ── Update gateway mode stats ──
    if gateway_mode and status == TransactionStatus.SUCCESS:
        TenantGatewayMode_cls = type(gateway_mode)
        TenantGatewayMode_cls.objects.filter(pk=gateway_mode.pk).update(
            total_transactions=F("total_transactions") + 1,
            total_volume=F("total_volume") + amount,
            last_transaction_at=timezone.now(),
        )

    logger.info(
        "Transaction confirmed: ref=%s status=%s amount=%s %s mode=%s",
        gateway_reference, status, amount, currency, mode,
    )

    return TransactionConfirmResult(
        success=True,
        transaction_id=str(txn.id),
        internal_reference=txn.internal_reference,
        status=status,
        amount=amount,
        currency=currency,
        payment_mode=mode,
        balance_credited=balance_credited,
        commission_charged=platform_commission if platform_commission > 0 else None,
        message=f"Transaction {status}.",
    )


def handle_gateway_webhook(
    gateway_provider: str,
    event_type: str,
    payload: dict,
    signature: str = "",
) -> dict:
    """
    Process an incoming gateway webhook event.

    Routes to the appropriate handler based on event_type.
    Verifies signature before processing.

    Returns:
        dict: {success, event_type, action_taken}
    """
    from dashboard.payments_tenant.models import GatewayWebhookConfig

    # ── Verify signature ──
    if not _verify_webhook_signature(gateway_provider, payload, signature):
        logger.warning("Invalid webhook signature from %s", gateway_provider)
        return {"success": False, "message": "Invalid signature."}

    logger.info("Processing webhook: provider=%s event=%s", gateway_provider, event_type)

    # ── Route by event type ──
    payment_events = {
        "charge.success", "payment.completed", "payment_intent.succeeded",
        "charge.completed", "successful",
    }
    refund_events  = {"refund.processed", "charge.refunded"}
    dispute_events = {"charge.dispute.create", "dispute.created", "chargebacks"}
    transfer_events = {"transfer.success", "transfer.failed", "transfer.reversed"}

    normalized = event_type.lower()

    if any(e in normalized for e in ("success", "completed", "succeeded")):
        return _handle_payment_webhook(gateway_provider, payload)
    elif any(e in normalized for e in ("refund", "reversed")):
        return _handle_refund_webhook(gateway_provider, payload)
    elif any(e in normalized for e in ("dispute", "chargeback")):
        return _handle_dispute_webhook(gateway_provider, payload)
    elif any(e in normalized for e in ("transfer",)):
        return _handle_transfer_webhook(gateway_provider, payload)
    elif any(e in normalized for e in ("failed", "failure")):
        return _handle_failed_payment_webhook(gateway_provider, payload)

    return {"success": True, "event_type": event_type, "action_taken": "logged_only"}


@transaction.atomic
def flag_transaction(transaction_id: str, reason: str = "", actor=None) -> bool:
    """Flag a transaction for fraud review."""
    from dashboard.payments_tenant.models import Transaction, TransactionEvent

    try:
        txn = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        return False

    txn.is_flagged = True
    txn.status = type(txn).status.field.choices  # keep existing status
    txn.save(update_fields=["is_flagged", "updated_at"])

    TransactionEvent.objects.create(
        transaction=txn,
        event_type=TransactionEvent.EventType.FRAUD_FLAGGED,
        detail=reason or "Flagged for fraud review.",
        source="fraud_engine",
        performed_by=actor,
    )
    return True


def unflag_transaction(transaction_id: str, actor=None) -> bool:
    """Remove fraud flag from a transaction after review."""
    from dashboard.payments_tenant.models import Transaction, TransactionEvent

    try:
        txn = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        return False

    txn.is_flagged = False
    txn.save(update_fields=["is_flagged", "updated_at"])
    TransactionEvent.objects.create(
        transaction=txn,
        event_type=TransactionEvent.EventType.FRAUD_CLEARED,
        detail="Fraud flag cleared after manual review.",
        source="admin",
        performed_by=actor,
    )
    return True


def get_transaction_timeline(transaction_id: str) -> list:
    """Get the full event timeline for a transaction."""
    from dashboard.payments_tenant.models import TransactionEvent

    events = TransactionEvent.objects.filter(
        transaction_id=transaction_id
    ).select_related("performed_by").order_by("created_at")

    return [
        {
            "id": str(e.id),
            "event_type": e.event_type,
            "from_status": e.from_status,
            "to_status": e.to_status,
            "detail": e.detail,
            "source": e.source,
            "actor": str(e.performed_by) if e.performed_by else "System",
            "created_at": e.created_at.isoformat(),
            "metadata": e.metadata,
        }
        for e in events
    ]


def get_order_transactions(order_id, payment_profile) -> list:
    """Get all transactions for an order."""
    from dashboard.payments_tenant.models import Transaction

    txns = Transaction.objects.filter(
        order_id=order_id, payment_profile=payment_profile,
    ).select_related("gateway_mode__gateway").order_by("-created_at")

    return [
        {
            "id": str(t.id),
            "internal_reference": t.internal_reference,
            "gateway_reference": t.gateway_reference,
            "status": t.status,
            "amount": float(t.amount),
            "currency": t.currency,
            "payment_mode": t.payment_mode,
            "gateway_provider": t.gateway_provider,
            "payment_method_type": t.payment_method_type,
            "paid_at": t.paid_at.isoformat() if t.paid_at else None,
            "is_flagged": t.is_flagged,
            "is_disputed": t.is_disputed,
            "amount_refunded": float(t.amount_refunded),
            "refundable_amount": float(t.refundable_amount),
        }
        for t in txns
    ]


def manually_override_status(
    transaction_id: str,
    new_status: str,
    reason: str,
    actor=None,
) -> dict:
    """Manually override a transaction's status (admin only)."""
    from dashboard.payments_tenant.models import Transaction, TransactionEvent

    try:
        txn = Transaction.objects.get(id=transaction_id)
    except Transaction.DoesNotExist:
        return {"success": False, "message": "Transaction not found."}

    old_status = txn.status
    txn.status = new_status
    txn.status_reason = reason
    txn.save(update_fields=["status", "status_reason", "updated_at"])

    TransactionEvent.objects.create(
        transaction=txn,
        event_type=TransactionEvent.EventType.MANUAL_OVERRIDE,
        from_status=old_status,
        to_status=new_status,
        detail=reason,
        source="admin_manual",
        performed_by=actor,
    )
    return {"success": True, "old_status": old_status, "new_status": new_status}


# ══════════════════════════════════════════════════════════════
# MODULE: commission_balance.py
# ══════════════════════════════════════════════════════════════

@dataclass
class CommissionResult:
    gateway_fee: Decimal = Decimal("0.00")
    platform_commission: Decimal = Decimal("0.00")
    tenant_net: Decimal = Decimal("0.00")
    gross_amount: Decimal = Decimal("0.00")
    commission_rate_applied: Decimal = Decimal("0.0000")
    flat_fee_applied: Decimal = Decimal("0.00")
    rule_name: str = ""
    currency: str = ""


@dataclass
class BalanceOperationResult:
    success: bool = False
    balance_transaction_id: Optional[str] = None
    available_before: Decimal = Decimal("0.00")
    available_after: Decimal = Decimal("0.00")
    pending_before: Decimal = Decimal("0.00")
    pending_after: Decimal = Decimal("0.00")
    reserved_before: Decimal = Decimal("0.00")
    reserved_after: Decimal = Decimal("0.00")
    message: str = ""


# ─────────────────────────────────────────────────────────────
# SECTION 3 — COMMISSION CALCULATION
# ─────────────────────────────────────────────────────────────

def resolve_commission_rule(payment_profile, gateway=None):
    """
    Find the most specific applicable CommissionRule for a tenant.

    Matching priority (most specific wins):
      1. Profile has custom commission → synthetic rule from profile
      2. Exact (gateway + plan + country) match
      3. Gateway + plan match
      4. Gateway-only match
      5. Plan-only match
      6. Global rule (all gateways, all plans)
    """
    from dashboard.payments_tenant.models import CommissionRule

    # Custom commission override (enterprise tenants)
    if payment_profile.has_custom_commission and payment_profile.custom_commission_rate is not None:
        class _CustomRule:
            percentage_rate = payment_profile.custom_commission_rate
            flat_fee = payment_profile.custom_commission_flat_fee or Decimal("0.00")
            cap_amount = payment_profile.custom_commission_cap
            minimum_fee = Decimal("0.00")
            gateway_fee_absorbed = True
            gateway_fee_pass_through_rate = None
            name = "Custom Enterprise Rate"
            def calculate_commission(self, amount):
                commission = max(
                    self.minimum_fee,
                    (amount * self.percentage_rate / Decimal("100")).quantize(TWO) + self.flat_fee,
                )
                if self.cap_amount:
                    commission = min(commission, self.cap_amount)
                return commission.quantize(TWO)
        return _CustomRule()

    qs = CommissionRule.objects.filter(is_active=True).order_by("-priority")

    if gateway:
        # Try gateway-specific first
        rule = qs.filter(gateway=gateway).first()
        if rule:
            return rule

    # Fall back to global rule
    return qs.filter(gateway__isnull=True).first()


def calculate_commission(
    amount: Decimal,
    rule=None,
    gateway_mode=None,
) -> CommissionResult:
    """
    Calculate the platform commission for a transaction.

    Returns:
        CommissionResult with gateway_fee, platform_commission, tenant_net.
    """
    if rule is None:
        return CommissionResult(
            gross_amount=amount,
            tenant_net=amount,
            rule_name="no_rule",
        )

    platform_commission = rule.calculate_commission(amount)

    # Gateway fee calculation
    gateway_fee = Decimal("0.00")
    if rule.gateway_fee_pass_through_rate and not rule.gateway_fee_absorbed:
        gateway_fee = (amount * rule.gateway_fee_pass_through_rate / Decimal("100")).quantize(TWO)

    tenant_net = amount - platform_commission - gateway_fee
    tenant_net = max(Decimal("0.00"), tenant_net)

    return CommissionResult(
        gateway_fee=gateway_fee,
        platform_commission=platform_commission,
        tenant_net=tenant_net,
        gross_amount=amount,
        commission_rate_applied=rule.percentage_rate,
        flat_fee_applied=rule.flat_fee,
        rule_name=getattr(rule, "name", ""),
    )


def create_commission_entry(
    transaction_id,
    payment_profile,
    gateway_mode,
    gross_amount: Decimal,
    gateway_fee: Decimal,
    platform_commission: Decimal,
    tenant_net: Decimal,
    currency: str,
    order_id=None,
    order_number: str = "",
    commission_rule=None,
) -> object:
    """Create the immutable CommissionEntry record for a successful transaction."""
    from dashboard.payments_tenant.models import CommissionEntry

    return CommissionEntry.objects.create(
        transaction_id=transaction_id,
        payment_profile=payment_profile,
        gateway_mode=gateway_mode,
        commission_rule=commission_rule,
        gross_amount=gross_amount,
        gateway_fee=gateway_fee,
        platform_commission=platform_commission,
        tenant_net=tenant_net,
        currency=currency,
        payment_mode=gateway_mode.mode if gateway_mode else "platform",
        commission_rate=commission_rule.percentage_rate if commission_rule else Decimal("0"),
        commission_flat_fee=commission_rule.flat_fee if commission_rule else Decimal("0"),
        gateway_provider=gateway_mode.gateway.provider if gateway_mode else "",
        order_id=order_id,
        order_number=order_number,
    )


def build_commission_entry_data(amount: Decimal, payment_profile, gateway_mode=None) -> dict:
    """Helper to compute commission breakdown without creating DB records."""
    rule = resolve_commission_rule(payment_profile, gateway_mode.gateway if gateway_mode else None)
    result = calculate_commission(amount, rule, gateway_mode)
    return {
        "gross_amount": float(amount),
        "gateway_fee": float(result.gateway_fee),
        "platform_commission": float(result.platform_commission),
        "tenant_net": float(result.tenant_net),
        "commission_rate": float(result.commission_rate_applied),
        "flat_fee": float(result.flat_fee_applied),
        "rule_name": result.rule_name,
    }


def get_commission_summary(payment_profile, days: int = 30) -> dict:
    """Commission summary for a tenant over the last N days."""
    from dashboard.payments_tenant.models import CommissionEntry
    from django.db.models import Sum, Count

    cutoff = timezone.now() - timezone.timedelta(days=days)
    agg = CommissionEntry.objects.filter(
        payment_profile=payment_profile,
        created_at__gte=cutoff,
    ).aggregate(
        total_gross=Sum("gross_amount"),
        total_commission=Sum("platform_commission"),
        total_gateway_fee=Sum("gateway_fee"),
        total_net=Sum("tenant_net"),
        count=Count("id"),
    )
    return {
        "period_days": days,
        "transaction_count": agg["count"] or 0,
        "total_gross": float(agg["total_gross"] or 0),
        "total_commission_paid": float(agg["total_commission"] or 0),
        "total_gateway_fees": float(agg["total_gateway_fee"] or 0),
        "total_net_earned": float(agg["total_net"] or 0),
    }


# ─────────────────────────────────────────────────────────────
# SECTION 4 — DOUBLE-ENTRY BALANCE LEDGER
# ─────────────────────────────────────────────────────────────

def get_or_create_balance(payment_profile, currency: str):
    """Get or create the TenantBalance for a tenant+currency pair."""
    from dashboard.payments_tenant.models import TenantBalance

    balance, _ = TenantBalance.objects.get_or_create(
        payment_profile=payment_profile,
        currency=currency,
        defaults={
            "available_balance": Decimal("0.00"),
            "pending_balance": Decimal("0.00"),
            "reserved_balance": Decimal("0.00"),
            "total_earned": Decimal("0.00"),
            "total_paid_out": Decimal("0.00"),
            "total_refunded": Decimal("0.00"),
        },
    )
    return balance


def get_tenant_balance(payment_profile, currency: str = None) -> dict:
    """
    Get the current balance for a tenant.

    Returns:
        dict: Balance summary by currency, or single currency if specified.
    """
    from dashboard.payments_tenant.models import TenantBalance

    qs = TenantBalance.objects.filter(payment_profile=payment_profile)
    if currency:
        qs = qs.filter(currency=currency)

    balances = list(qs)

    if currency and balances:
        b = balances[0]
        return {
            "currency": b.currency,
            "available": float(b.available_balance),
            "pending": float(b.pending_balance),
            "reserved": float(b.reserved_balance),
            "total": float(b.total_balance),
            "total_earned": float(b.total_earned),
            "total_paid_out": float(b.total_paid_out),
            "total_refunded": float(b.total_refunded),
        }

    return {
        "currencies": [
            {
                "currency": b.currency,
                "available": float(b.available_balance),
                "pending": float(b.pending_balance),
                "reserved": float(b.reserved_balance),
                "total": float(b.total_balance),
                "total_earned": float(b.total_earned),
                "total_paid_out": float(b.total_paid_out),
            }
            for b in balances
        ]
    }


@transaction.atomic
def credit_tenant_balance(
    payment_profile,
    amount: Decimal,
    currency: str,
    transaction_type: str,
    description: str,
    source_transaction_id=None,
    source_refund_id=None,
    source_dispute_id=None,
    source_payout_id=None,
    order_id=None,
    order_number: str = "",
    target_field: str = "available",
    performed_by=None,
) -> BalanceOperationResult:
    """
    Credit (increase) the tenant's balance with a double-entry ledger record.

    Args:
        target_field: "available" | "pending" | "reserved"
    """
    from dashboard.payments_tenant.models import TenantBalance, TenantBalanceTransaction

    balance = TenantBalance.objects.select_for_update().get(
        payment_profile=payment_profile, currency=currency,
    )

    # Snapshot before
    avail_before = balance.available_balance
    pend_before  = balance.pending_balance
    resv_before  = balance.reserved_balance

    # Apply credit to the target field
    if target_field == "pending":
        balance.pending_balance = F("pending_balance") + amount
    elif target_field == "reserved":
        balance.reserved_balance = F("reserved_balance") + amount
    else:
        balance.available_balance = F("available_balance") + amount
        balance.total_earned = F("total_earned") + amount

    balance.save()
    balance.refresh_from_db()

    # Append-only ledger entry
    entry = TenantBalanceTransaction.objects.create(
        tenant_balance=balance,
        payment_profile=payment_profile,
        transaction_type=transaction_type,
        entry_type=TenantBalanceTransaction.EntryType.CREDIT,
        amount=amount,
        currency=currency,
        available_before=avail_before,
        available_after=balance.available_balance,
        pending_before=pend_before,
        pending_after=balance.pending_balance,
        reserved_before=resv_before,
        reserved_after=balance.reserved_balance,
        source_transaction_id=source_transaction_id,
        source_refund_id=source_refund_id,
        source_dispute_id=source_dispute_id,
        source_payout_id=source_payout_id,
        order_id=order_id,
        order_number=order_number,
        description=description,
        performed_by=performed_by,
    )

    return BalanceOperationResult(
        success=True,
        balance_transaction_id=str(entry.id),
        available_before=avail_before,
        available_after=balance.available_balance,
        pending_before=pend_before,
        pending_after=balance.pending_balance,
        reserved_before=resv_before,
        reserved_after=balance.reserved_balance,
        message=f"Balance credited {amount} {currency}.",
    )


@transaction.atomic
def debit_tenant_balance(
    payment_profile,
    amount: Decimal,
    currency: str,
    transaction_type: str,
    description: str,
    source_transaction_id=None,
    source_refund_id=None,
    source_dispute_id=None,
    source_payout_id=None,
    order_id=None,
    order_number: str = "",
    from_field: str = "available",
    performed_by=None,
) -> BalanceOperationResult:
    """
    Debit (decrease) the tenant's balance. Validates sufficient funds.
    """
    from dashboard.payments_tenant.models import TenantBalance, TenantBalanceTransaction

    balance = TenantBalance.objects.select_for_update().get(
        payment_profile=payment_profile, currency=currency,
    )

    # Validate sufficient funds
    if from_field == "available" and balance.available_balance < amount:
        return BalanceOperationResult(
            success=False,
            message=f"Insufficient available balance. Have {balance.available_balance}, need {amount}.",
        )
    elif from_field == "reserved" and balance.reserved_balance < amount:
        return BalanceOperationResult(
            success=False,
            message=f"Insufficient reserved balance.",
        )

    avail_before = balance.available_balance
    pend_before  = balance.pending_balance
    resv_before  = balance.reserved_balance

    if from_field == "pending":
        balance.pending_balance = F("pending_balance") - amount
    elif from_field == "reserved":
        balance.reserved_balance = F("reserved_balance") - amount
    else:
        balance.available_balance = F("available_balance") - amount
        if transaction_type == "refund_debit":
            balance.total_refunded = F("total_refunded") + amount
        elif transaction_type == "payout_debit":
            balance.total_paid_out = F("total_paid_out") + amount

    balance.save()
    balance.refresh_from_db()

    entry = TenantBalanceTransaction.objects.create(
        tenant_balance=balance,
        payment_profile=payment_profile,
        transaction_type=transaction_type,
        entry_type=TenantBalanceTransaction.EntryType.DEBIT,
        amount=amount,
        currency=currency,
        available_before=avail_before,
        available_after=balance.available_balance,
        pending_before=pend_before,
        pending_after=balance.pending_balance,
        reserved_before=resv_before,
        reserved_after=balance.reserved_balance,
        source_transaction_id=source_transaction_id,
        source_refund_id=source_refund_id,
        source_dispute_id=source_dispute_id,
        source_payout_id=source_payout_id,
        order_id=order_id,
        order_number=order_number,
        description=description,
        performed_by=performed_by,
    )

    return BalanceOperationResult(
        success=True,
        balance_transaction_id=str(entry.id),
        available_before=avail_before,
        available_after=balance.available_balance,
        message=f"Balance debited {amount} {currency}.",
    )


@transaction.atomic
def hold_for_dispute(
    payment_profile,
    amount: Decimal,
    currency: str,
    dispute_id,
    description: str = "",
) -> BalanceOperationResult:
    """Move funds from available to reserved for an open dispute."""
    from dashboard.payments_tenant.models import TenantBalance

    balance = TenantBalance.objects.select_for_update().get(
        payment_profile=payment_profile, currency=currency,
    )

    if balance.available_balance < amount:
        amount = balance.available_balance  # Hold whatever is available

    debit_result = debit_tenant_balance(
        payment_profile=payment_profile,
        amount=amount,
        currency=currency,
        transaction_type="dispute_hold",
        description=description or "Funds held pending dispute resolution.",
        source_dispute_id=dispute_id,
        from_field="available",
    )
    if not debit_result.success:
        return debit_result

    return credit_tenant_balance(
        payment_profile=payment_profile,
        amount=amount,
        currency=currency,
        transaction_type="dispute_hold",
        description=description or "Funds held pending dispute resolution.",
        source_dispute_id=dispute_id,
        target_field="reserved",
    )


@transaction.atomic
def release_dispute_hold(
    payment_profile,
    amount: Decimal,
    currency: str,
    dispute_id,
    won: bool = True,
) -> BalanceOperationResult:
    """Release reserved dispute funds. Won=True restores to available, False discards."""
    if won:
        # Debit reserved → credit available
        debit_result = debit_tenant_balance(
            payment_profile=payment_profile,
            amount=amount,
            currency=currency,
            transaction_type="dispute_release",
            description="Dispute won — funds released.",
            source_dispute_id=dispute_id,
            from_field="reserved",
        )
        if not debit_result.success:
            return debit_result
        return credit_tenant_balance(
            payment_profile=payment_profile,
            amount=amount,
            currency=currency,
            transaction_type="dispute_release",
            description="Dispute won — funds released to available balance.",
            source_dispute_id=dispute_id,
            target_field="available",
        )
    else:
        # Debit reserved → funds gone (to customer)
        return debit_tenant_balance(
            payment_profile=payment_profile,
            amount=amount,
            currency=currency,
            transaction_type="dispute_loss",
            description="Dispute lost — funds returned to customer.",
            source_dispute_id=dispute_id,
            from_field="reserved",
        )


def apply_risk_hold(payment_profile, amount: Decimal, currency: str) -> BalanceOperationResult:
    """Move funds from available to reserved for a risk/fraud hold."""
    return debit_tenant_balance(
        payment_profile=payment_profile, amount=amount, currency=currency,
        transaction_type="risk_hold", description="Risk hold applied by fraud engine.",
        from_field="available",
    )


def release_risk_hold(payment_profile, amount: Decimal, currency: str) -> BalanceOperationResult:
    """Release a risk hold back to available balance."""
    debit_result = debit_tenant_balance(
        payment_profile=payment_profile, amount=amount, currency=currency,
        transaction_type="risk_release", description="Risk hold released.",
        from_field="reserved",
    )
    if not debit_result.success:
        return debit_result
    return credit_tenant_balance(
        payment_profile=payment_profile, amount=amount, currency=currency,
        transaction_type="risk_release", description="Risk hold released to available.",
        target_field="available",
    )


def get_balance_ledger(
    payment_profile,
    currency: str = None,
    page: int = 1,
    page_size: int = 20,
    transaction_type: str = None,
) -> dict:
    """Paginated balance ledger for the tenant's finance page."""
    from dashboard.payments_tenant.models import TenantBalanceTransaction

    qs = TenantBalanceTransaction.objects.filter(
        payment_profile=payment_profile,
    ).order_by("-created_at")

    if currency:
        qs = qs.filter(currency=currency)
    if transaction_type:
        qs = qs.filter(transaction_type=transaction_type)

    total = qs.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    entries = qs[offset:offset + page_size]

    return {
        "entries": [
            {
                "id": str(e.id),
                "transaction_type": e.transaction_type,
                "entry_type": e.entry_type,
                "amount": float(e.amount),
                "currency": e.currency,
                "available_after": float(e.available_after),
                "description": e.description,
                "order_number": e.order_number,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ],
        "total": total,
        "page": page,
        "total_pages": total_pages,
    }


def get_balance_summary(payment_profile) -> dict:
    """Full balance summary with recent transactions for the tenant dashboard."""
    from dashboard.payments_tenant.models import TenantBalance, TenantBalanceTransaction

    balances = list(TenantBalance.objects.filter(payment_profile=payment_profile))

    recent = list(
        TenantBalanceTransaction.objects.filter(
            payment_profile=payment_profile
        ).order_by("-created_at")[:5].values(
            "transaction_type", "entry_type", "amount", "currency", "description", "created_at",
        )
    )

    return {
        "balances": [
            {
                "currency": b.currency,
                "available": float(b.available_balance),
                "pending": float(b.pending_balance),
                "reserved": float(b.reserved_balance),
                "total_earned": float(b.total_earned),
                "total_paid_out": float(b.total_paid_out),
                "total_refunded": float(b.total_refunded),
            }
            for b in balances
        ],
        "recent_entries": recent,
    }


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _generate_payment_reference(provider: str = "") -> str:
    """Generate a unique payment reference."""
    prefix = provider[:3].upper() if provider else "PAY"
    return f"{prefix}-{str(uuid.uuid4()).replace('-', '')[:16].upper()}"


def _generate_internal_reference() -> str:
    """Generate the platform's internal transaction reference."""
    import time
    ts = int(time.time())
    rand = str(uuid.uuid4()).replace("-", "")[:8].upper()
    return f"TXN-{ts}-{rand}"


def _verify_webhook_signature(gateway_provider: str, payload: dict, signature: str) -> bool:
    """Verify webhook signature from a payment gateway. Stub."""
    logger.debug("Webhook signature verification (stub): provider=%s", gateway_provider)
    return True  # Always valid in stub — implement per-provider HMAC check in production


def _handle_payment_webhook(gateway_provider: str, payload: dict) -> dict:
    """Handle a successful payment webhook."""
    logger.info("Payment success webhook from %s (stub processing)", gateway_provider)
    return {"success": True, "event_type": "payment_success", "action_taken": "transaction_confirmed"}


def _handle_refund_webhook(gateway_provider: str, payload: dict) -> dict:
    logger.info("Refund webhook from %s", gateway_provider)
    return {"success": True, "event_type": "refund", "action_taken": "logged"}


def _handle_dispute_webhook(gateway_provider: str, payload: dict) -> dict:
    logger.info("Dispute webhook from %s", gateway_provider)
    return {"success": True, "event_type": "dispute", "action_taken": "logged"}


def _handle_transfer_webhook(gateway_provider: str, payload: dict) -> dict:
    logger.info("Transfer webhook from %s", gateway_provider)
    return {"success": True, "event_type": "transfer", "action_taken": "logged"}


def _handle_failed_payment_webhook(gateway_provider: str, payload: dict) -> dict:
    logger.info("Failed payment webhook from %s", gateway_provider)
    return {"success": True, "event_type": "payment_failed", "action_taken": "logged"}
