"""
payments/utils/payout_fraud.py
================================
Payout lifecycle, bank account management, fraud risk scoring, blocklist.
"""

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("payments.payout_fraud")
TWO = Decimal("0.01")


@dataclass
class PayoutRequestResult:
    success: bool = False
    payout_request_id: Optional[str] = None
    amount: Optional[Decimal] = None
    currency: str = ""
    status: str = ""
    balance_after: Optional[Decimal] = None
    message: str = ""
    errors: list = field(default_factory=list)


@dataclass
class BankAccountResult:
    success: bool = False
    bank_account_id: Optional[str] = None
    is_verified: bool = False
    masked_number: str = ""
    message: str = ""
    errors: list = field(default_factory=list)


@dataclass
class FraudAssessmentResult:
    risk_score: int = 0
    decision: str = "allow"
    triggered_rules: list = field(default_factory=list)
    signals: dict = field(default_factory=dict)
    should_block: bool = False
    should_flag: bool = False
    requires_3ds: bool = False
    message: str = ""


# ─────────────────────────────────────────────────────────────
# SECTION 1 — PAYOUT LIFECYCLE
# ─────────────────────────────────────────────────────────────

def check_payout_eligibility(payment_profile, amount: Decimal, currency: str) -> dict:
    """
    Check whether a tenant can request a payout.

    Checks:
      1. Payout is enabled on the profile (KYB verified + bank account)
      2. Account is ACTIVE
      3. Has at least one verified primary bank account
      4. Available balance ≥ requested amount
      5. Amount ≥ minimum payout threshold

    Returns:
        dict: {eligible, reason, available_balance}
    """
    from dashboard.payments_tenant.models import TenantBankAccount, TenantBalance

    if not payment_profile.payout_enabled:
        return {
            "eligible": False,
            "reason": (
                "Payouts are not yet enabled for your account. "
                "Please complete your KYB verification and add a verified bank account."
            ),
        }

    if not payment_profile.is_operational:
        return {
            "eligible": False,
            "reason": f"Your payment account is {payment_profile.account_status}. Payouts are unavailable.",
        }

    # Check for verified bank account
    has_bank = TenantBankAccount.objects.filter(
        payment_profile=payment_profile,
        status=TenantBankAccount.AccountStatus.VERIFIED,
    ).exists()
    if not has_bank:
        return {
            "eligible": False,
            "reason": "No verified bank account found. Please add and verify a bank account first.",
        }

    # Check minimum payout amount
    min_payout = payment_profile.minimum_payout_amount
    if amount < min_payout:
        return {
            "eligible": False,
            "reason": f"Minimum payout amount is {min_payout} {currency}. Requested: {amount}.",
        }

    # Check available balance
    try:
        balance = TenantBalance.objects.get(
            payment_profile=payment_profile, currency=currency,
        )
        if balance.available_balance < amount:
            return {
                "eligible": False,
                "reason": (
                    f"Insufficient available balance. "
                    f"Available: {balance.available_balance} {currency}, Requested: {amount}."
                ),
                "available_balance": float(balance.available_balance),
            }
        return {
            "eligible": True,
            "available_balance": float(balance.available_balance),
            "reason": "",
        }
    except TenantBalance.DoesNotExist:
        return {
            "eligible": False,
            "reason": f"No balance record for currency {currency}.",
        }


@transaction.atomic
def request_payout(
    payment_profile,
    amount: Decimal,
    currency: str,
    bank_account_id: str,
    narration: str = "",
    tenant_note: str = "",
    actor=None,
    auto_approve: bool = False,
) -> PayoutRequestResult:
    """
    Submit a payout request.

    In PLATFORM MODE:
      1. Check eligibility
      2. Debit TenantBalance.available_balance immediately
      3. Create PayoutRequest in PENDING status
      4. Auto-approve if amount ≤ threshold

    Args:
        payment_profile: TenantPaymentProfile
        amount:          Amount to pay out
        currency:        ISO 4217 currency
        bank_account_id: TenantBankAccount.id to receive funds
        narration:       Description on bank statement
        tenant_note:     Internal note from tenant
        actor:           Staff or customer initiating
        auto_approve:    Skip manual review (for small amounts)
    """
    from dashboard.payments_tenant.models import TenantBankAccount, PayoutRequest, TenantBalance
    from .intent_transactions import debit_tenant_balance, get_or_create_balance

    # ── Eligibility check ──
    eligibility = check_payout_eligibility(payment_profile, amount, currency)
    if not eligibility["eligible"]:
        return PayoutRequestResult(
            success=False,
            errors=[eligibility["reason"]],
        )

    # ── Validate bank account ──
    try:
        bank_account = TenantBankAccount.objects.get(
            id=bank_account_id,
            payment_profile=payment_profile,
            status=TenantBankAccount.AccountStatus.VERIFIED,
        )
    except TenantBankAccount.DoesNotExist:
        return PayoutRequestResult(
            success=False,
            errors=["Bank account not found or not verified."],
        )

    # ── Get balance snapshot ──
    try:
        balance = TenantBalance.objects.select_for_update().get(
            payment_profile=payment_profile, currency=currency,
        )
    except TenantBalance.DoesNotExist:
        return PayoutRequestResult(success=False, errors=["Balance record not found."])

    balance_before = balance.available_balance

    # ── Create PayoutRequest ──
    payout_request = PayoutRequest.objects.create(
        payment_profile=payment_profile,
        bank_account=bank_account,
        amount=amount,
        currency=currency,
        request_type=PayoutRequest.RequestType.MANUAL,
        status=PayoutRequest.RequestStatus.PENDING,
        narration=narration or f"Payout to {bank_account.bank_name} — {timezone.now().strftime('%b %Y')}",
        tenant_note=tenant_note,
        balance_before=balance_before,
        balance_after=balance_before - amount,
    )

    # ── Debit balance immediately ──
    debit_result = debit_tenant_balance(
        payment_profile=payment_profile,
        amount=amount,
        currency=currency,
        transaction_type=TenantBalanceTransaction_type("payout_debit"),
        description=f"Payout request #{payout_request.id} — {bank_account.bank_name}",
        source_payout_id=payout_request.id,
    )

    if not debit_result.success:
        # Rollback the payout request
        payout_request.delete()
        return PayoutRequestResult(success=False, errors=[debit_result.message])

    payout_request.payout_batch_id = None
    payout_request.save(update_fields=["balance_after", "updated_at"])

    # ── Auto-approve small amounts ──
    AUTO_APPROVE_THRESHOLD = Decimal("500000.00")
    if auto_approve or amount <= AUTO_APPROVE_THRESHOLD:
        payout_request.status = PayoutRequest.RequestStatus.APPROVED
        payout_request.is_auto_approved = True
        payout_request.reviewed_at = timezone.now()
        payout_request.save(update_fields=["status", "is_auto_approved", "reviewed_at", "updated_at"])
        # Trigger async processing
        _schedule_payout_processing(payout_request)

    logger.info(
        "Payout request created: %s — %s %s to %s",
        payout_request.id, amount, currency, bank_account.bank_name,
    )

    return PayoutRequestResult(
        success=True,
        payout_request_id=str(payout_request.id),
        amount=amount,
        currency=currency,
        status=payout_request.status,
        balance_after=balance_before - amount,
        message=(
            f"Payout request submitted for {amount} {currency} to {bank_account.bank_name}. "
            "You will be notified when funds are transferred."
        ),
    )


@transaction.atomic
def approve_payout_request(
    payout_request_id: str,
    actor=None,
    review_note: str = "",
) -> dict:
    """Approve a pending payout request for processing."""
    from dashboard.payments_tenant.models import PayoutRequest

    try:
        req = PayoutRequest.objects.select_for_update().get(id=payout_request_id)
    except PayoutRequest.DoesNotExist:
        return {"success": False, "message": "Payout request not found."}

    if req.status != PayoutRequest.RequestStatus.PENDING:
        return {"success": False, "message": f"Cannot approve request in status '{req.status}'."}

    req.status = PayoutRequest.RequestStatus.APPROVED
    req.reviewed_by = actor
    req.reviewed_at = timezone.now()
    req.review_note = review_note
    req.approved_at = timezone.now()
    req.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note", "approved_at", "updated_at"])

    _schedule_payout_processing(req)
    return {"success": True, "message": f"Payout approved. Transfer will be processed shortly."}


@transaction.atomic
def reject_payout_request(
    payout_request_id: str,
    actor=None,
    rejection_reason: str = "",
) -> dict:
    """Reject a payout request and restore the tenant's balance."""
    from dashboard.payments_tenant.models import PayoutRequest
    from .intent_transactions import credit_tenant_balance

    try:
        req = PayoutRequest.objects.select_for_update().get(id=payout_request_id)
    except PayoutRequest.DoesNotExist:
        return {"success": False, "message": "Payout request not found."}

    if req.status not in (PayoutRequest.RequestStatus.PENDING, PayoutRequest.RequestStatus.APPROVED):
        return {"success": False, "message": f"Cannot reject request in status '{req.status}'."}

    # Restore balance (reversal)
    credit_tenant_balance(
        payment_profile=req.payment_profile,
        amount=req.amount,
        currency=req.currency,
        transaction_type="payout_reversal",
        description=f"Payout request {req.id} rejected — balance restored.",
        source_payout_id=req.id,
    )

    req.status = PayoutRequest.RequestStatus.REJECTED
    req.reviewed_by = actor
    req.reviewed_at = timezone.now()
    req.rejection_reason = rejection_reason
    req.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason", "updated_at"])

    return {"success": True, "message": "Payout rejected. Balance has been restored."}


@transaction.atomic
def process_payout_transfer(
    payout_request_id: str,
    gateway_provider: str = "paystack",
) -> dict:
    """
    Initiate the actual bank transfer for an approved payout request.
    Called by a Celery task after approval.
    """
    from dashboard.payments_tenant.models import PayoutRequest, PayoutTransfer

    try:
        req = PayoutRequest.objects.select_related(
            "bank_account", "payment_profile"
        ).get(
            id=payout_request_id,
            status=PayoutRequest.RequestStatus.APPROVED,
        )
    except PayoutRequest.DoesNotExist:
        return {"success": False, "message": "Approved payout request not found."}

    req.status = PayoutRequest.RequestStatus.PROCESSING
    req.save(update_fields=["status", "updated_at"])

    transfer = PayoutTransfer.objects.create(
        payout_request=req,
        bank_account=req.bank_account,
        gateway_provider=gateway_provider,
        status=PayoutTransfer.TransferStatus.PENDING,
        amount=req.amount,
        currency=req.currency,
        initiated_at=timezone.now(),
    )

    try:
        result = _call_transfer_api(req, transfer, gateway_provider)
        transfer.gateway_transfer_id = result.get("transfer_id", "")
        transfer.gateway_transfer_code = result.get("transfer_code", "")
        transfer.gateway_response = result
        transfer.save(update_fields=[
            "gateway_transfer_id", "gateway_transfer_code", "gateway_response", "updated_at"
        ])
        return {"success": True, "transfer_id": str(transfer.id), "message": "Transfer initiated."}
    except Exception as e:
        transfer.status = PayoutTransfer.TransferStatus.FAILED
        transfer.failure_reason = str(e)
        transfer.save(update_fields=["status", "failure_reason", "updated_at"])
        req.status = PayoutRequest.RequestStatus.FAILED
        req.failure_reason = str(e)
        req.failed_at = timezone.now()
        req.save(update_fields=["status", "failure_reason", "failed_at", "updated_at"])
        # Restore balance on failure
        from .intent_transactions import credit_tenant_balance
        credit_tenant_balance(
            payment_profile=req.payment_profile,
            amount=req.amount,
            currency=req.currency,
            transaction_type="payout_reversal",
            description=f"Payout {req.id} transfer failed — balance restored.",
            source_payout_id=req.id,
        )
        return {"success": False, "message": str(e)}


@transaction.atomic
def mark_payout_success(transfer_id: str, gateway_confirmation_ref: str = "") -> bool:
    """Mark a payout transfer as successful (from gateway webhook)."""
    from dashboard.payments_tenant.models import PayoutTransfer, PayoutRequest

    try:
        transfer = PayoutTransfer.objects.select_related("payout_request").get(id=transfer_id)
    except PayoutTransfer.DoesNotExist:
        return False

    transfer.status = PayoutTransfer.TransferStatus.SUCCESS
    transfer.completed_at = timezone.now()
    transfer.bank_confirmation_ref = gateway_confirmation_ref
    transfer.save(update_fields=["status", "completed_at", "bank_confirmation_ref", "updated_at"])

    req = transfer.payout_request
    req.status = PayoutRequest.RequestStatus.COMPLETED
    req.completed_at = timezone.now()
    req.save(update_fields=["status", "completed_at", "updated_at"])
    return True


@transaction.atomic
def mark_payout_failed(transfer_id: str, reason: str = "") -> bool:
    """Mark a payout transfer as failed and restore the balance."""
    from dashboard.payments_tenant.models import PayoutTransfer, PayoutRequest
    from .intent_transactions import credit_tenant_balance

    try:
        transfer = PayoutTransfer.objects.select_related(
            "payout_request__payment_profile"
        ).get(id=transfer_id)
    except PayoutTransfer.DoesNotExist:
        return False

    transfer.status = PayoutTransfer.TransferStatus.FAILED
    transfer.failure_reason = reason
    transfer.save(update_fields=["status", "failure_reason", "updated_at"])

    req = transfer.payout_request
    req.status = PayoutRequest.RequestStatus.FAILED
    req.failure_reason = reason
    req.failed_at = timezone.now()
    req.save(update_fields=["status", "failure_reason", "failed_at", "updated_at"])

    credit_tenant_balance(
        payment_profile=req.payment_profile,
        amount=req.amount,
        currency=req.currency,
        transaction_type="payout_reversal",
        description=f"Payout transfer failed — balance restored. Reason: {reason}",
        source_payout_id=req.id,
    )
    return True


def get_pending_payouts(payment_profile=None) -> list:
    """Get all pending payout requests (platform-wide or per tenant)."""
    from dashboard.payments_tenant.models import PayoutRequest

    qs = PayoutRequest.objects.filter(
        status__in=[PayoutRequest.RequestStatus.PENDING, PayoutRequest.RequestStatus.APPROVED],
    ).select_related("bank_account", "payment_profile")

    if payment_profile:
        qs = qs.filter(payment_profile=payment_profile)

    return [
        {
            "id": str(r.id),
            "amount": float(r.amount),
            "currency": r.currency,
            "status": r.status,
            "bank_name": r.bank_account.bank_name,
            "account_number": r.bank_account.account_number_masked,
            "narration": r.narration,
            "requested_at": r.requested_at.isoformat(),
            "is_auto_approved": r.is_auto_approved,
        }
        for r in qs.order_by("requested_at")
    ]


def get_payout_history(payment_profile, page: int = 1, page_size: int = 20) -> dict:
    """Paginated payout history for the tenant's finance page."""
    from dashboard.payments_tenant.models import PayoutRequest

    qs = PayoutRequest.objects.filter(
        payment_profile=payment_profile
    ).select_related("bank_account").order_by("-requested_at")

    total = qs.count()
    total_pages = max(1, (total + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    return {
        "payouts": [
            {
                "id": str(r.id),
                "amount": float(r.amount),
                "net_amount": float(r.net_amount),
                "platform_fee": float(r.platform_processing_fee),
                "currency": r.currency,
                "status": r.status,
                "bank_name": r.bank_account.bank_name,
                "account_number": r.bank_account.account_number_masked,
                "narration": r.narration,
                "requested_at": r.requested_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "failure_reason": r.failure_reason,
            }
            for r in qs[offset:offset + page_size]
        ],
        "total": total,
        "page": page,
        "total_pages": total_pages,
    }


# ─────────────────────────────────────────────────────────────
# SECTION 2 — BANK ACCOUNT MANAGEMENT
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def add_bank_account(
    payment_profile,
    account_name: str,
    bank_name: str,
    account_number: str,
    bank_code: str = "",
    currency: str = "NGN",
    country_code: str = "NG",
    account_type: str = "current",
    routing_number: str = "",
    iban: str = "",
    swift_bic: str = "",
    label: str = "",
    is_primary: bool = False,
    actor=None,
) -> BankAccountResult:
    """
    Add a new bank account for payout.
    Auto-triggers verification via bank lookup API.
    """
    from dashboard.payments_tenant.models import TenantBankAccount

    bank_account = TenantBankAccount.objects.create(
        payment_profile=payment_profile,
        account_name=account_name,
        bank_name=bank_name,
        bank_code=bank_code,
        account_number=account_number,  # Encrypt in production
        currency=currency,
        country_code=country_code,
        account_type=account_type,
        routing_number=routing_number,
        iban=iban,
        swift_bic=swift_bic,
        label=label,
        is_primary=is_primary,
        status=TenantBankAccount.AccountStatus.PENDING,
        added_by=actor,
    )

    # Trigger async bank verification
    _schedule_bank_verification(bank_account)

    return BankAccountResult(
        success=True,
        bank_account_id=str(bank_account.id),
        is_verified=False,
        masked_number=bank_account.account_number_masked,
        message=(
            "Bank account added. We're verifying it now — "
            "this usually takes under 2 minutes."
        ),
    )


@transaction.atomic
def verify_bank_account(
    bank_account_id: str,
    verification_method: str = "api_lookup",
    actor=None,
) -> BankAccountResult:
    """
    Verify a tenant's bank account.
    Called by an async task or manually by a platform admin.
    """
    from dashboard.payments_tenant.models import TenantBankAccount

    try:
        account = TenantBankAccount.objects.get(id=bank_account_id)
    except TenantBankAccount.DoesNotExist:
        return BankAccountResult(success=False, errors=["Bank account not found."])

    try:
        # Stub — replace with real bank lookup API (e.g. Paystack /bank/resolve)
        verification_data = _call_bank_verification_api(account)

        account.status = TenantBankAccount.AccountStatus.VERIFIED
        account.verified_at = timezone.now()
        account.verified_by = actor
        account.verification_method = verification_method
        account.verification_data = verification_data
        account.gateway_recipient_code = verification_data.get("recipient_code", "")
        account.gateway_provider = verification_data.get("gateway_provider", "")
        account.save(update_fields=[
            "status", "verified_at", "verified_by", "verification_method",
            "verification_data", "gateway_recipient_code", "gateway_provider", "updated_at",
        ])

        # Enable payouts if this is the first verified account
        if not account.payment_profile.payout_enabled:
            if account.payment_profile.kyb_status == "verified":
                account.payment_profile.payout_enabled = True
                account.payment_profile.save(update_fields=["payout_enabled", "updated_at"])

        return BankAccountResult(
            success=True,
            bank_account_id=str(account.id),
            is_verified=True,
            masked_number=account.account_number_masked,
            message=f"Bank account verified: {account.account_name} at {account.bank_name}.",
        )

    except Exception as e:
        account.status = TenantBankAccount.AccountStatus.FAILED
        account.failure_reason = str(e)
        account.save(update_fields=["status", "failure_reason", "updated_at"])
        return BankAccountResult(
            success=False,
            bank_account_id=str(account.id),
            errors=[f"Verification failed: {e}"],
        )


# ─────────────────────────────────────────────────────────────
# SECTION 3 — FRAUD RISK ENGINE
# ─────────────────────────────────────────────────────────────

def assess_fraud_risk(
    payment_profile,
    amount: Decimal,
    currency: str,
    customer_email: str = "",
    customer_ip: str = "",
    card_bin: str = "",
    customer_id=None,
    device_fingerprint: str = "",
    order_id=None,
) -> FraudAssessmentResult:
    """
    Run all fraud rules against a payment and return a risk score + decision.

    The risk score accumulates contributions from triggered rules.
    Decision thresholds:
      0-25:  ALLOW
      26-50: FLAG for review (allow but notify)
      51-74: REQUIRE_3DS or additional verification
      75+:   BLOCK

    Returns:
        FraudAssessmentResult with score, decision, and triggered rules.
    """
    from dashboard.payments_tenant.models import FraudRule

    result = FraudAssessmentResult()
    signals = {}
    triggered = []
    total_score = 0

    # Get all applicable rules (platform-wide + tenant-specific)
    rules = FraudRule.objects.filter(
        is_active=True,
    ).filter(
        __import__("django.db.models", fromlist=["Q"]).Q(payment_profile__isnull=True) |
        __import__("django.db.models", fromlist=["Q"]).Q(payment_profile=payment_profile)
    ).order_by("-priority")

    for rule in rules:
        triggered_flag, score_contribution, signal = _evaluate_single_rule(
            rule=rule,
            payment_profile=payment_profile,
            amount=amount,
            customer_email=customer_email,
            customer_ip=customer_ip,
            card_bin=card_bin,
            customer_id=customer_id,
        )
        if triggered_flag:
            total_score += score_contribution
            triggered.append({
                "rule_id": str(rule.id),
                "rule_name": rule.name,
                "rule_type": rule.rule_type,
                "action": rule.action,
                "contribution": score_contribution,
            })
            signals.update(signal)

            # Immediately block if rule says BLOCK
            if rule.action == FraudRule.Action.BLOCK:
                result.should_block = True
                result.decision = "block"

    # Determine overall decision from accumulated score
    if not result.should_block:
        if total_score >= 75:
            result.decision = "block"
            result.should_block = True
        elif total_score >= 51:
            result.decision = "require_3ds"
            result.requires_3ds = True
        elif total_score >= 26:
            result.decision = "flag"
            result.should_flag = True
        else:
            result.decision = "allow"

    result.risk_score = min(100, total_score)
    result.triggered_rules = triggered
    result.signals = signals
    result.message = f"Risk score: {result.risk_score}. Decision: {result.decision}."

    return result


def evaluate_fraud_rules(payment_profile, context: dict) -> FraudAssessmentResult:
    """Evaluate fraud rules with a structured context dict."""
    return assess_fraud_risk(
        payment_profile=payment_profile,
        amount=context.get("amount", Decimal("0")),
        currency=context.get("currency", ""),
        customer_email=context.get("customer_email", ""),
        customer_ip=context.get("customer_ip", ""),
        card_bin=context.get("card_bin", ""),
        customer_id=context.get("customer_id"),
        device_fingerprint=context.get("device_fingerprint", ""),
        order_id=context.get("order_id"),
    )


def record_fraud_assessment(
    payment_profile,
    assessment: FraudAssessmentResult,
    payment_intent=None,
    transaction=None,
    customer_ip: str = "",
    device_fingerprint: str = "",
) -> object:
    """Persist a FraudAssessmentResult to the database."""
    from dashboard.payments_tenant.models import FraudAssessment

    return FraudAssessment.objects.create(
        payment_intent=payment_intent,
        transaction=transaction,
        payment_profile=payment_profile,
        risk_score=assessment.risk_score,
        decision=assessment.decision,
        triggered_rules=assessment.triggered_rules,
        signals=assessment.signals,
        customer_ip=customer_ip or None,
        device_fingerprint=device_fingerprint,
    )


def get_fraud_queue(payment_profile=None, limit: int = 50) -> list:
    """Get transactions flagged for fraud review."""
    from dashboard.payments_tenant.models import Transaction

    qs = Transaction.objects.filter(is_flagged=True).select_related(
        "payment_profile", "gateway_mode__gateway"
    ).order_by("-created_at")

    if payment_profile:
        qs = qs.filter(payment_profile=payment_profile)

    return [
        {
            "id": str(t.id),
            "internal_reference": t.internal_reference,
            "amount": float(t.amount),
            "currency": t.currency,
            "customer_email": t.customer_email,
            "customer_ip": str(t.customer_ip) if t.customer_ip else "",
            "gateway_provider": t.gateway_provider,
            "risk_score": t.risk_score,
            "status": t.status,
            "paid_at": t.paid_at.isoformat() if t.paid_at else None,
            "created_at": t.created_at.isoformat(),
        }
        for t in qs[:limit]
    ]


# ─────────────────────────────────────────────────────────────
# SECTION 4 — BLOCKLIST
# ─────────────────────────────────────────────────────────────

def check_blocklist(
    entry_type: str,
    value: str,
    payment_profile=None,
) -> bool:
    """Check if a value is on the platform or tenant blocklist."""
    from dashboard.payments_tenant.models import BlocklistEntry
    return BlocklistEntry.is_blocked(entry_type, value, payment_profile)


@transaction.atomic
def add_to_blocklist(
    entry_type: str,
    value: str,
    reason: str,
    payment_profile=None,
    is_platform_wide: bool = False,
    source: str = "manual_admin",
    expires_at=None,
    actor=None,
    source_transaction_id=None,
) -> dict:
    """Add a value to the fraud blocklist."""
    from dashboard.payments_tenant.models import BlocklistEntry

    value_hash = hashlib.sha256(value.lower().strip().encode()).hexdigest()

    entry, created = BlocklistEntry.objects.get_or_create(
        entry_type=entry_type,
        value_hash=value_hash,
        payment_profile=payment_profile,
        defaults={
            "value": value,
            "reason": reason,
            "is_platform_wide": is_platform_wide,
            "source": source,
            "expires_at": expires_at,
            "added_by": actor,
            "source_transaction_id": source_transaction_id,
        },
    )

    return {
        "success": True,
        "created": created,
        "entry_id": str(entry.id),
        "message": f"{'Added to' if created else 'Already on'} blocklist: {entry_type}",
    }


def remove_from_blocklist(
    entry_type: str,
    value: str,
    payment_profile=None,
) -> bool:
    """Remove a value from the blocklist."""
    from dashboard.payments_tenant.models import BlocklistEntry

    value_hash = hashlib.sha256(value.lower().strip().encode()).hexdigest()
    deleted, _ = BlocklistEntry.objects.filter(
        entry_type=entry_type,
        value_hash=value_hash,
        payment_profile=payment_profile,
    ).delete()
    return bool(deleted)


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _evaluate_single_rule(rule, payment_profile, amount, customer_email,
                           customer_ip, card_bin, customer_id) -> tuple:
    """Evaluate one FraudRule. Returns (triggered, score_contribution, signals)."""
    from dashboard.payments_tenant.models import FraudRule, Transaction
    from django.db.models import Q

    rtype = rule.rule_type

    if rtype == FraudRule.RuleType.MAX_AMOUNT:
        if rule.threshold_amount and amount > rule.threshold_amount:
            return True, rule.risk_score_contribution, {"max_amount_exceeded": float(amount)}

    elif rtype == FraudRule.RuleType.GEO_BLOCK:
        # IP geo-blocking stub — integrate with GeoIP library in production
        pass

    elif rtype == FraudRule.RuleType.BIN_BLOCK:
        if card_bin and rule.blocked_values and card_bin[:6] in rule.blocked_values:
            return True, rule.risk_score_contribution, {"blocked_bin": card_bin[:6]}

    elif rtype == FraudRule.RuleType.VELOCITY_EMAIL:
        if customer_email and rule.count_threshold and rule.time_window_minutes:
            cutoff = timezone.now() - timezone.timedelta(minutes=rule.time_window_minutes)
            count = Transaction.objects.filter(
                customer_email=customer_email,
                created_at__gte=cutoff,
            ).count()
            if count >= rule.count_threshold:
                return True, rule.risk_score_contribution, {"email_velocity": count}

    elif rtype == FraudRule.RuleType.VELOCITY_IP:
        if customer_ip and rule.count_threshold and rule.time_window_minutes:
            cutoff = timezone.now() - timezone.timedelta(minutes=rule.time_window_minutes)
            count = Transaction.objects.filter(
                customer_ip=customer_ip,
                created_at__gte=cutoff,
            ).count()
            if count >= rule.count_threshold:
                return True, rule.risk_score_contribution, {"ip_velocity": count}

    return False, 0, {}


def TenantBalanceTransaction_type(type_str: str) -> str:
    """Helper to return the correct transaction_type string."""
    return type_str


def _schedule_payout_processing(payout_request) -> None:
    """Schedule async payout transfer processing."""
    logger.info("Payout processing scheduled for request %s (stub)", payout_request.id)
    # from payments.tasks import process_payout_transfer
    # process_payout_transfer.apply_async(args=[str(payout_request.id)], countdown=60)


def _schedule_bank_verification(bank_account) -> None:
    """Schedule async bank account verification."""
    logger.info("Bank verification scheduled for account %s (stub)", bank_account.id)
    # from payments.tasks import verify_bank_account_task
    # verify_bank_account_task.apply_async(args=[str(bank_account.id)], countdown=5)


def _call_transfer_api(payout_request, transfer, gateway_provider: str) -> dict:
    """Call gateway transfer API. Stub."""
    logger.info("Transfer API call (stub): %s %s via %s",
                payout_request.amount, payout_request.currency, gateway_provider)
    return {
        "transfer_id": f"trnsf_{str(payout_request.id)[:8]}",
        "transfer_code": f"TRF_{str(payout_request.id)[:8].upper()}",
        "status": "success",
    }


def _call_bank_verification_api(bank_account) -> dict:
    """Call bank verification API. Stub."""
    logger.info("Bank verification API call (stub) for %s", bank_account.id)
    return {
        "account_name": bank_account.account_name,
        "account_number": bank_account.account_number_masked,
        "bank_code": bank_account.bank_code,
        "recipient_code": f"RCP_{str(bank_account.id)[:8].upper()}",
        "gateway_provider": "paystack",
    }
