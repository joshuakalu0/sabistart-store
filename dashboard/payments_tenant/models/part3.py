"""
payments/models_part3.py — Part 3 of 4
=========================================
SECTION 8  — TENANT BALANCE LEDGER
SECTION 9  — PAYOUT SYSTEM
SECTION 10 — FRAUD & RISK
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .core import AppendOnlyModel, TenantPaymentProfile, TimestampedModel


def generate_idempotency_key():
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────
# SECTION 8 — TENANT BALANCE LEDGER (TENANT SCHEMA)
# ─────────────────────────────────────────────────────────────

class TenantBalance(TimestampedModel):
    """
    The live balance owed to a tenant in PLATFORM MODE.

    ONE record per (tenant × currency).
    This is the "running total" — the net amount the platform owes
    the tenant from all their PLATFORM MODE transactions.

    TenantBalance is the summary view.
    TenantBalanceTransaction is the append-only double-entry ledger.

    The balance is always:
        sum of all CREDIT entries − sum of all DEBIT entries

    Credits:
      + Successful payment (tenant net after commission)
      + Dispute won (balance restored)
      + Commission reversal (on refund)
      + Manual adjustment (platform admin)

    Debits:
      − Refund issued (tenant net portion)
      − Dispute opened (pending resolution hold)
      − Payout processed (tenant requested their money)
      − Fee deduction
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_profile = models.ForeignKey(
        TenantPaymentProfile,
        on_delete=models.CASCADE,
        related_name="balances",
        verbose_name=_("Payment Profile"),
    )
    currency = models.CharField(_("Currency"), max_length=3, db_index=True)

    # ── Live balance fields ──
    available_balance = models.DecimalField(
        _("Available Balance"),
        max_digits=18, decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Balance available for payout right now."),
    )
    pending_balance = models.DecimalField(
        _("Pending Balance"),
        max_digits=18, decimal_places=2,
        default=Decimal("0.00"),
        help_text=_(
            "Balance from transactions not yet settled by the gateway. "
            "Moves to available_balance after settlement period."
        ),
    )
    reserved_balance = models.DecimalField(
        _("Reserved Balance"),
        max_digits=18, decimal_places=2,
        default=Decimal("0.00"),
        help_text=_(
            "Balance held for open disputes or risk reserves. "
            "Released when disputes are resolved or reserve period ends."
        ),
    )
    total_earned = models.DecimalField(
        _("Total Ever Earned"),
        max_digits=18, decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Cumulative lifetime earnings (sum of all credit entries)."),
    )
    total_paid_out = models.DecimalField(
        _("Total Ever Paid Out"),
        max_digits=18, decimal_places=2,
        default=Decimal("0.00"),
        help_text=_("Cumulative lifetime payout amount."),
    )
    total_refunded = models.DecimalField(
        _("Total Refunded"),
        max_digits=18, decimal_places=2,
        default=Decimal("0.00"),
    )

    # ── Computed property for convenience ──
    @property
    def total_balance(self) -> Decimal:
        return self.available_balance + self.pending_balance + self.reserved_balance

    @property
    def is_primary(self) -> bool:
        return self.currency == self.payment_profile.default_currency

    @property
    def total_volume(self):
        return self.total_earned

    class Meta:
        verbose_name = _("Tenant Balance")
        verbose_name_plural = _("Tenant Balances")
        unique_together = [("payment_profile", "currency")]
        indexes = [
            models.Index(fields=["payment_profile", "currency"]),
        ]

    def __str__(self):
        return (
            f"Balance [{self.currency}] — "
            f"Available: {self.available_balance}, "
            f"Pending: {self.pending_balance}, "
            f"Reserved: {self.reserved_balance}"
        )


class TenantBalanceTransaction(AppendOnlyModel):
    """
    Immutable double-entry ledger for the tenant's balance.
    APPEND-ONLY — NEVER UPDATE OR DELETE.

    Every change to TenantBalance.available_balance, .pending_balance,
    or .reserved_balance MUST be recorded here first.

    Transaction types and their effect on balance fields:
    ────────────────────────────────────────────────────────
    PAYMENT_CREDIT:      +available (tenant earns from successful payment)
    PAYMENT_PENDING:     +pending   (payment received, not yet settled)
    SETTLEMENT:          −pending, +available (gateway settlement)
    REFUND_DEBIT:        −available (tenant pays back refunded amount)
    COMMISSION_REVERSAL: +available (commission returned on refund)
    DISPUTE_HOLD:        −available, +reserved (chargeback hold)
    DISPUTE_RELEASE:     −reserved, +available (dispute won)
    DISPUTE_LOSS:        −reserved  (dispute lost, money returned to customer)
    PAYOUT_DEBIT:        −available (payout requested)
    PAYOUT_REVERSAL:     +available (failed payout credited back)
    RISK_HOLD:           −available, +reserved
    RISK_RELEASE:        −reserved, +available
    FEE_DEDUCTION:       −available (platform subscription fee)
    MANUAL_CREDIT:       +available (platform admin adjustment)
    MANUAL_DEBIT:        −available (platform admin adjustment)
    ────────────────────────────────────────────────────────
    """

    class TransactionType(models.TextChoices):
        PAYMENT_CREDIT      = "payment_credit",      _("Payment Credit")
        PAYMENT_PENDING     = "payment_pending",      _("Payment Pending")
        SETTLEMENT          = "settlement",           _("Gateway Settlement")
        REFUND_DEBIT        = "refund_debit",         _("Refund Debit")
        COMMISSION_REVERSAL = "commission_reversal",  _("Commission Reversal on Refund")
        DISPUTE_HOLD        = "dispute_hold",         _("Dispute Hold")
        DISPUTE_RELEASE     = "dispute_release",      _("Dispute Release — Won")
        DISPUTE_LOSS        = "dispute_loss",         _("Dispute Loss")
        PAYOUT_DEBIT        = "payout_debit",         _("Payout Debit")
        PAYOUT_REVERSAL     = "payout_reversal",      _("Payout Failure Reversal")
        RISK_HOLD           = "risk_hold",            _("Risk / Fraud Hold")
        RISK_RELEASE        = "risk_release",         _("Risk Hold Released")
        FEE_DEDUCTION       = "fee_deduction",        _("Platform Fee Deduction")
        MANUAL_CREDIT       = "manual_credit",        _("Manual Credit (Admin)")
        MANUAL_DEBIT        = "manual_debit",         _("Manual Debit (Admin)")

    class EntryType(models.TextChoices):
        CREDIT = "credit", _("Credit — Increases Balance")
        DEBIT  = "debit",  _("Debit — Decreases Balance")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant_balance  = models.ForeignKey(
        TenantBalance, on_delete=models.CASCADE, related_name="transactions",
    )
    payment_profile = models.ForeignKey(
        TenantPaymentProfile, on_delete=models.CASCADE, related_name="balance_transactions",
    )

    # ── Double-entry fields ──
    transaction_type = models.CharField(
        _("Transaction Type"), max_length=25,
        choices=TransactionType.choices, db_index=True,
    )
    entry_type = models.CharField(
        _("Entry Type"), max_length=6,
        choices=EntryType.choices, db_index=True,
    )
    amount   = models.DecimalField(_("Amount"), max_digits=14, decimal_places=2)
    currency = models.CharField(_("Currency"), max_length=3)

    # ── Balance snapshot (before and after) ──
    available_before   = models.DecimalField(_("Available Before"), max_digits=18, decimal_places=2)
    available_after    = models.DecimalField(_("Available After"),  max_digits=18, decimal_places=2)
    pending_before     = models.DecimalField(_("Pending Before"),   max_digits=18, decimal_places=2)
    pending_after      = models.DecimalField(_("Pending After"),    max_digits=18, decimal_places=2)
    reserved_before    = models.DecimalField(_("Reserved Before"),  max_digits=18, decimal_places=2)
    reserved_after     = models.DecimalField(_("Reserved After"),   max_digits=18, decimal_places=2)

    # ── Source references (all FK-less to avoid cross-model deps) ──
    source_transaction_id = models.UUIDField(
        _("Source Transaction ID"),
        null=True, blank=True, db_index=True,
        help_text=_("The payment Transaction that triggered this entry."),
    )
    source_refund_id     = models.UUIDField(_("Source Refund ID"), null=True, blank=True)
    source_dispute_id    = models.UUIDField(_("Source Dispute ID"), null=True, blank=True)
    source_payout_id     = models.UUIDField(_("Source Payout ID"), null=True, blank=True)
    order_id             = models.UUIDField(_("Order ID"), null=True, blank=True, db_index=True)
    order_number         = models.CharField(_("Order Number"), max_length=100, blank=True)

    # ── Description ──
    description     = models.CharField(_("Description"), max_length=500)
    internal_note   = models.TextField(_("Internal Note"), blank=True)

    # ── Performed by ──
    performed_by   = models.ForeignKey(
        "userauth.TenantUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="balance_entries",
    )

    # ── Settlement tracking ──
    settlement_date = models.DateField(_("Settlement Date"), null=True, blank=True)
    is_reconciled   = models.BooleanField(_("Reconciled"), default=False, db_index=True)

    class Meta:
        verbose_name = _("Tenant Balance Transaction")
        verbose_name_plural = _("Tenant Balance Transactions")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant_balance", "-created_at"]),
            models.Index(fields=["transaction_type", "-created_at"]),
            models.Index(fields=["payment_profile", "entry_type", "-created_at"]),
            models.Index(fields=["source_transaction_id"]),
            models.Index(fields=["order_id"]),
            models.Index(fields=["is_reconciled"]),
        ]

    def __str__(self):
        sign = "+" if self.entry_type == self.EntryType.CREDIT else "−"
        return (
            f"[{self.transaction_type}] {sign}{self.amount} {self.currency} "
            f"→ available: {self.available_after}"
        )


# ─────────────────────────────────────────────────────────────
# SECTION 9 — PAYOUT SYSTEM (TENANT SCHEMA)
# ─────────────────────────────────────────────────────────────

class TenantBankAccount(TimestampedModel):
    """
    A tenant's bank account registered for payout receipt.

    Tenants in PLATFORM MODE need at least one verified bank account
    to request payouts. The platform validates the account details
    before enabling payouts.

    Multiple accounts can be registered:
      - One can be the primary/default for automatic payouts
      - Others as alternatives for specific currencies

    Account verification:
      For Nigerian banks, we use BVN / account number validation
      via a banking API (e.g. Paystack Bank API, Flutterwave /banks).
      The `verification_data` field stores the API response.

    Security:
      - account_number is stored encrypted in production
      - Full account details are NEVER returned in API responses
        — only masked version (e.g. ****7890) is shown
    """

    class AccountStatus(models.TextChoices):
        PENDING    = "pending",    _("Pending Verification")
        VERIFIED   = "verified",   _("Verified")
        FAILED     = "failed",     _("Verification Failed")
        INACTIVE   = "inactive",   _("Inactive — Removed by Tenant")
        BLOCKED    = "blocked",    _("Blocked by Platform")

    class AccountType(models.TextChoices):
        CURRENT  = "current",   _("Current Account")
        SAVINGS  = "savings",   _("Savings Account")
        CHECKING = "checking",  _("Checking Account")
        DOMICILIARY = "domiciliary", _("Domiciliary Account (Foreign Currency)")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_profile = models.ForeignKey(
        TenantPaymentProfile, on_delete=models.CASCADE, related_name="bank_accounts",
    )

    # ── Account identity ──
    account_name = models.CharField(
        _("Account Name"),
        max_length=255,
        help_text=_("Name on the bank account. Must match business/owner name."),
    )
    bank_name    = models.CharField(_("Bank Name"), max_length=255)
    bank_code    = models.CharField(
        _("Bank Code"),
        max_length=20,
        blank=True,
        help_text=_("CBN sort code or gateway bank code. e.g. '058' for GTBank."),
    )
    account_number = models.TextField(
        _("Account Number (encrypted)"),
        help_text=_("ENCRYPTED. The full account number. Never expose in logs or API."),
    )
    account_number_masked = models.CharField(
        _("Masked Account Number"),
        max_length=30,
        blank=True,
        help_text=_("e.g. '****7890' — safe for display in UI."),
    )
    account_type = models.CharField(
        _("Account Type"), max_length=15,
        choices=AccountType.choices, default=AccountType.CURRENT,
    )
    currency     = models.CharField(_("Currency"), max_length=3, default="NGN")
    country_code = models.CharField(_("Country"), max_length=2, default="NG")

    # ── Routing ──
    routing_number  = models.CharField(_("Routing / Sort Number"), max_length=50, blank=True)
    iban            = models.CharField(_("IBAN"), max_length=50, blank=True)
    swift_bic       = models.CharField(_("SWIFT / BIC"), max_length=20, blank=True)
    branch_code     = models.CharField(_("Branch Code"), max_length=20, blank=True)
    branch_address  = models.TextField(_("Branch Address"), blank=True)

    # ── Gateway recipient reference ──
    gateway_recipient_code = models.CharField(
        _("Gateway Recipient Code"),
        max_length=500,
        blank=True,
        db_index=True,
        help_text=_(
            "For gateways that support programmatic transfers (e.g. Paystack Transfer API): "
            "the recipient code created after account verification. "
            "Used to initiate payout transfers."
        ),
    )
    gateway_provider = models.CharField(_("Gateway Provider"), max_length=20, blank=True)

    # ── Verification ──
    status              = models.CharField(
        _("Status"), max_length=15,
        choices=AccountStatus.choices, default=AccountStatus.PENDING, db_index=True,
    )
    verified_at         = models.DateTimeField(_("Verified At"), null=True, blank=True)
    verified_by         = models.ForeignKey(
        "userauth.TenantUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="verified_bank_accounts",
    )
    verification_method = models.CharField(
        _("Verification Method"),
        max_length=30,
        blank=True,
        choices=[
            ("api_lookup",    _("API Bank Lookup")),
            ("micro_deposit", _("Micro-Deposit")),
            ("manual",        _("Manual Admin Verification")),
            ("document",      _("Document Verification")),
        ],
    )
    verification_data   = models.JSONField(
        _("Verification Data"),
        default=dict,
        blank=True,
        help_text=_("Full response from bank verification API."),
    )
    verification_note   = models.TextField(_("Verification Note"), blank=True)
    failure_reason      = models.TextField(_("Failure Reason"), blank=True)

    # ── Priority / default ──
    is_primary     = models.BooleanField(
        _("Primary Account"),
        default=False,
        help_text=_("Default account used for automatic payouts."),
    )
    display_order  = models.PositiveSmallIntegerField(_("Display Order"), default=0)

    # ── Limits ──
    max_payout_per_day = models.DecimalField(
        _("Max Payout Per Day"),
        max_digits=18, decimal_places=2,
        null=True, blank=True,
    )

    # ── Metadata ──
    label = models.CharField(
        _("Label"),
        max_length=100,
        blank=True,
        help_text=_("e.g. 'Operations Account', 'Dollar Account'"),
    )
    notes = models.TextField(_("Notes"), blank=True)
    added_by = models.ForeignKey(
        "userauth.TenantUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="added_bank_accounts",
    )
    deactivated_at = models.DateTimeField(_("Deactivated At"), null=True, blank=True)

    class Meta:
        verbose_name = _("Tenant Bank Account")
        verbose_name_plural = _("Tenant Bank Accounts")
        ordering = ["-is_primary", "display_order"]
        indexes = [
            models.Index(fields=["payment_profile", "status"]),
            models.Index(fields=["gateway_recipient_code"]),
        ]

    def __str__(self):
        return f"{self.account_name} — {self.bank_name} {self.account_number_masked} ({self.currency})"

    @property
    def is_verified(self) -> bool:
        return self.status == self.AccountStatus.VERIFIED

    def save(self, *args, **kwargs):
        if self.account_number and not self.account_number_masked:
            # Auto-generate masked version (store last 4 digits safely)
            raw = str(self.account_number)
            self.account_number_masked = "****" + raw[-4:] if len(raw) >= 4 else "****"
        if self.is_primary:
            TenantBankAccount.objects.filter(
                payment_profile=self.payment_profile, is_primary=True,
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class PayoutRequest(TimestampedModel):
    """
    A tenant's request to withdraw their available balance.

    Created by the tenant (manual) or automatically (scheduled payout).
    Platform reviews and approves/rejects before processing.

    For auto-approved requests (under a threshold), the platform
    immediately creates a PayoutBatch and PayoutTransfer.

    For large amounts, manual review may be required.

    Balance accounting:
      On creation:  available_balance → −amount (creates PAYOUT_DEBIT ledger entry)
      On failure:   available_balance ← +amount (creates PAYOUT_REVERSAL entry)
      On success:   no further balance change (already debited on creation)
    """

    class RequestStatus(models.TextChoices):
        PENDING   = "pending",   _("Pending — Awaiting Platform Review")
        APPROVED  = "approved",  _("Approved — Scheduled for Processing")
        REJECTED  = "rejected",  _("Rejected")
        PROCESSING = "processing", _("Processing — Transfer in Progress")
        COMPLETED = "completed", _("Completed — Funds Sent")
        FAILED    = "failed",    _("Failed — Transfer Error")
        CANCELLED = "cancelled", _("Cancelled")

    class RequestType(models.TextChoices):
        MANUAL    = "manual",    _("Manual — Requested by Tenant")
        SCHEDULED = "scheduled", _("Scheduled — Automatic Payout")
        SYSTEM    = "system",    _("System — Triggered by Platform")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_profile = models.ForeignKey(
        TenantPaymentProfile, on_delete=models.CASCADE, related_name="payout_requests",
    )
    bank_account = models.ForeignKey(
        TenantBankAccount, on_delete=models.PROTECT, related_name="payout_requests",
        help_text=_("The bank account to receive this payout."),
    )

    # ── Request details ──
    amount       = models.DecimalField(_("Requested Amount"), max_digits=18, decimal_places=2)
    currency     = models.CharField(_("Currency"), max_length=3)
    request_type = models.CharField(
        _("Request Type"), max_length=15,
        choices=RequestType.choices, default=RequestType.MANUAL,
    )

    # ── Status ──
    status = models.CharField(
        _("Status"), max_length=15,
        choices=RequestStatus.choices, default=RequestStatus.PENDING, db_index=True,
    )

    # ── Platform fees ──
    platform_processing_fee = models.DecimalField(
        _("Platform Processing Fee"),
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Fee charged by the platform for processing this payout."),
    )
    gateway_transfer_fee = models.DecimalField(
        _("Gateway Transfer Fee"),
        max_digits=10, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Fee charged by the gateway/bank for the transfer."),
    )
    net_amount = models.DecimalField(
        _("Net Amount Received by Tenant"),
        max_digits=18, decimal_places=2, default=Decimal("0.00"),
        help_text=_("Amount actually received: requested − all fees."),
    )

    # ── Tenant-facing ──
    narration    = models.CharField(
        _("Narration"),
        max_length=255,
        blank=True,
        help_text=_("Description on the bank statement. e.g. 'SabiStart payout — Jan 2025'"),
    )
    tenant_note  = models.TextField(_("Tenant Note"), blank=True)

    # ── Platform review ──
    reviewed_by   = models.ForeignKey(
        "userauth.TenantUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="reviewed_payouts",
    )
    reviewed_at   = models.DateTimeField(_("Reviewed At"), null=True, blank=True)
    review_note   = models.TextField(_("Review Note"), blank=True)
    rejection_reason = models.TextField(_("Rejection Reason"), blank=True)
    is_auto_approved = models.BooleanField(
        _("Auto-Approved"),
        default=False,
        help_text=_("True if approved automatically without manual review."),
    )

    # ── Timing ──
    requested_at  = models.DateTimeField(_("Requested At"), default=timezone.now, db_index=True)
    approved_at   = models.DateTimeField(_("Approved At"), null=True, blank=True)
    completed_at  = models.DateTimeField(_("Completed At"), null=True, blank=True)
    failed_at     = models.DateTimeField(_("Failed At"), null=True, blank=True)
    failure_reason = models.TextField(_("Failure Reason"), blank=True)

    # ── Balance snapshot at request time ──
    balance_before = models.DecimalField(
        _("Balance Before Request"),
        max_digits=18, decimal_places=2,
        help_text=_("Tenant's available balance immediately before this payout was deducted."),
    )
    balance_after = models.DecimalField(
        _("Balance After Request"),
        max_digits=18, decimal_places=2, default=Decimal("0.00"),
    )

    # ── Payout batch reference ──
    payout_batch_id = models.UUIDField(
        _("Payout Batch ID"), null=True, blank=True, db_index=True,
        help_text=_("FK-less ref to PayoutBatch this was included in."),
    )

    # ── Idempotency ──
    idempotency_key = models.CharField(
        _("Idempotency Key"),
        max_length=255,
        unique=True,
        db_index=True,
        default=generate_idempotency_key,
        help_text=_("Prevents duplicate payout requests from retries."),
    )

    class Meta:
        verbose_name = _("Payout Request")
        verbose_name_plural = _("Payout Requests")
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["payment_profile", "status"]),
            models.Index(fields=["status", "requested_at"]),
            models.Index(fields=["payout_batch_id"]),
        ]

    def __str__(self):
        return (
            f"Payout {self.id} — {self.amount} {self.currency} "
            f"to {self.bank_account.bank_name} [{self.status}]"
        )

    @property
    def payout_reference(self):
        return f"PAY-{str(self.id).replace('-', '')[:10].upper()}"

    @property
    def gateway_transfer_reference(self):
        latest_transfer = self.transfers.order_by("-created_at").first()
        if latest_transfer is None:
            return ""
        return (
            latest_transfer.bank_confirmation_ref
            or latest_transfer.gateway_reference
            or latest_transfer.gateway_transfer_code
            or latest_transfer.gateway_transfer_id
        )


class PayoutBatch(TimestampedModel):
    """
    A platform-level batch of payout requests processed together.

    The platform groups approved PayoutRequests into batches and
    sends them via gateway bulk transfer APIs (e.g. Paystack /transfer/bulk)
    for efficiency and fee optimization.

    One batch per (gateway × currency × processing_date).
    """

    class BatchStatus(models.TextChoices):
        PENDING    = "pending",    _("Pending — Building")
        PROCESSING = "processing", _("Processing — Transfers Initiated")
        COMPLETED  = "completed",  _("Completed — All Transfers Sent")
        PARTIAL    = "partial",    _("Partial — Some Transfers Failed")
        FAILED     = "failed",     _("Failed — All Transfers Failed")
        CANCELLED  = "cancelled",  _("Cancelled")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch_reference  = models.CharField(_("Batch Reference"), max_length=100, unique=True, db_index=True)
    gateway_provider = models.CharField(_("Gateway Provider"), max_length=20)
    currency         = models.CharField(_("Currency"), max_length=3)
    status           = models.CharField(
        _("Status"), max_length=15,
        choices=BatchStatus.choices, default=BatchStatus.PENDING, db_index=True,
    )
    total_amount      = models.DecimalField(_("Total Amount"), max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_items       = models.PositiveIntegerField(_("Total Items"), default=0)
    completed_items   = models.PositiveIntegerField(_("Completed"), default=0)
    failed_items      = models.PositiveIntegerField(_("Failed"), default=0)
    gateway_batch_id  = models.CharField(_("Gateway Batch ID"), max_length=500, blank=True)
    gateway_response  = models.JSONField(_("Gateway Response"), default=dict, blank=True)
    initiated_by      = models.ForeignKey(
        "userauth.TenantUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="payout_batches",
    )
    processing_started_at  = models.DateTimeField(_("Processing Started"), null=True, blank=True)
    completed_at           = models.DateTimeField(_("Completed At"), null=True, blank=True)
    notes                  = models.TextField(_("Notes"), blank=True)

    class Meta:
        verbose_name = _("Payout Batch")
        verbose_name_plural = _("Payout Batches")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Batch {self.batch_reference} — {self.total_items} items, {self.total_amount} {self.currency} [{self.status}]"


class PayoutItem(TimestampedModel):
    """Links a PayoutRequest to a PayoutBatch. One item per payout in a batch."""

    class ItemStatus(models.TextChoices):
        QUEUED     = "queued",     _("Queued")
        PROCESSING = "processing", _("Processing")
        SUCCESS    = "success",    _("Success")
        FAILED     = "failed",     _("Failed")

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    batch          = models.ForeignKey(PayoutBatch, on_delete=models.CASCADE, related_name="items")
    payout_request = models.ForeignKey(PayoutRequest, on_delete=models.CASCADE, related_name="batch_items")
    status         = models.CharField(_("Status"), max_length=15, choices=ItemStatus.choices, default=ItemStatus.QUEUED, db_index=True)
    gateway_transfer_code = models.CharField(_("Gateway Transfer Code"), max_length=500, blank=True)
    failure_reason = models.TextField(_("Failure Reason"), blank=True)
    processed_at   = models.DateTimeField(_("Processed At"), null=True, blank=True)

    class Meta:
        verbose_name = _("Payout Item")
        unique_together = [("batch", "payout_request")]

    def __str__(self):
        return f"PayoutItem — {self.payout_request.amount} {self.payout_request.currency} [{self.status}]"


class PayoutTransfer(TimestampedModel):
    """
    The actual bank transfer record executed for a PayoutRequest.
    Contains the provider-level transfer details and confirmation.
    """

    class TransferStatus(models.TextChoices):
        PENDING   = "pending",   _("Pending")
        SUCCESS   = "success",   _("Success — Funds Transferred")
        FAILED    = "failed",    _("Failed")
        REVERSED  = "reversed",  _("Reversed by Bank")
        ABANDONED = "abandoned", _("Abandoned")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payout_request   = models.ForeignKey(PayoutRequest, on_delete=models.CASCADE, related_name="transfers")
    bank_account     = models.ForeignKey(TenantBankAccount, on_delete=models.PROTECT, related_name="transfers")
    gateway_provider = models.CharField(_("Gateway Provider"), max_length=20)
    status           = models.CharField(
        _("Status"), max_length=15,
        choices=TransferStatus.choices, default=TransferStatus.PENDING, db_index=True,
    )
    amount           = models.DecimalField(_("Transfer Amount"), max_digits=18, decimal_places=2)
    currency         = models.CharField(_("Currency"), max_length=3)
    gateway_transfer_id   = models.CharField(_("Gateway Transfer ID"), max_length=500, blank=True, db_index=True)
    gateway_transfer_code = models.CharField(_("Gateway Transfer Code"), max_length=500, blank=True)
    gateway_reference     = models.CharField(_("Gateway Reference"), max_length=500, blank=True)
    gateway_response      = models.JSONField(_("Gateway Response"), default=dict, blank=True)
    bank_confirmation_ref = models.CharField(
        _("Bank Confirmation Reference"),
        max_length=500, blank=True,
        help_text=_("Bank's own reference number for the transfer (if provided by gateway)."),
    )
    failure_reason   = models.TextField(_("Failure Reason"), blank=True)
    initiated_at     = models.DateTimeField(_("Initiated At"), null=True, blank=True)
    completed_at     = models.DateTimeField(_("Completed At"), null=True, blank=True)
    reversed_at      = models.DateTimeField(_("Reversed At"), null=True, blank=True)

    class Meta:
        verbose_name = _("Payout Transfer")
        verbose_name_plural = _("Payout Transfers")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["payout_request", "status"]),
            models.Index(fields=["gateway_transfer_id"]),
        ]

    def __str__(self):
        return f"Transfer {self.id} — {self.amount} {self.currency} via {self.gateway_provider} [{self.status}]"


# ─────────────────────────────────────────────────────────────
# SECTION 10 — FRAUD & RISK (TENANT SCHEMA)
# ─────────────────────────────────────────────────────────────

class FraudRule(TimestampedModel):
    """
    Configurable fraud detection rule.

    Rules are evaluated per-transaction via the fraud engine.
    Each rule has a weight — matching rules add to the total risk score.
    If total score exceeds the threshold, the transaction is flagged or blocked.

    Rule types cover velocity checks, amount limits, geographic restrictions,
    device fingerprinting, and known fraud indicators.
    """

    class RuleType(models.TextChoices):
        MAX_AMOUNT           = "max_amount",           _("Maximum Transaction Amount")
        MAX_DAILY_VOLUME     = "max_daily_volume",     _("Maximum Daily Volume per Customer")
        MAX_ATTEMPTS         = "max_attempts",         _("Maximum Failed Attempts per Card/Email")
        VELOCITY_CARD        = "velocity_card",        _("Card Velocity — Too Many Txns in Window")
        VELOCITY_EMAIL       = "velocity_email",       _("Email Velocity")
        VELOCITY_IP          = "velocity_ip",          _("IP Address Velocity")
        GEO_BLOCK            = "geo_block",            _("Block Transactions from Country")
        GEO_MISMATCH         = "geo_mismatch",         _("Card Country Mismatch")
        BIN_BLOCK            = "bin_block",            _("Block Specific Card BINs")
        IP_PROXY_BLOCK       = "ip_proxy_block",       _("Block VPN / Proxy IPs")
        NEW_CARD_LARGE_ORDER = "new_card_large_order", _("New Card + Large Order")
        DUPLICATE_ORDER      = "duplicate_order",      _("Duplicate Order in Short Window")
        UNUSUAL_HOUR         = "unusual_hour",         _("Transaction at Unusual Hour")

    class Action(models.TextChoices):
        FLAG          = "flag",          _("Flag for Review — Allow but Notify")
        BLOCK         = "block",         _("Block — Reject Transaction")
        REQUIRE_3DS   = "require_3ds",   _("Require Additional 3DS Authentication")
        REQUIRE_OTP   = "require_otp",   _("Require OTP Verification")
        ALERT_STAFF   = "alert_staff",   _("Alert Staff — Allow Transaction")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_profile = models.ForeignKey(
        TenantPaymentProfile, null=True, blank=True,
        on_delete=models.CASCADE, related_name="fraud_rules",
        help_text=_("Null = platform-level rule applied to all tenants."),
    )
    name       = models.CharField(_("Rule Name"), max_length=255)
    rule_type  = models.CharField(_("Rule Type"), max_length=25, choices=RuleType.choices)
    action     = models.CharField(_("Action"), max_length=15, choices=Action.choices, default=Action.FLAG)
    risk_score_contribution = models.PositiveSmallIntegerField(
        _("Risk Score Contribution"),
        default=25,
        validators=[MaxValueValidator(100)],
        help_text=_("How many points this rule adds to the transaction's risk score (0-100)."),
    )
    is_active  = models.BooleanField(_("Active"), default=True, db_index=True)
    priority   = models.PositiveIntegerField(_("Priority"), default=0)

    # ── Rule parameters ──
    threshold_amount = models.DecimalField(
        _("Amount Threshold"), max_digits=14, decimal_places=2,
        null=True, blank=True,
        help_text=_("For MAX_AMOUNT: block if amount > this. For velocity: block if daily volume > this."),
    )
    count_threshold  = models.PositiveIntegerField(
        _("Count Threshold"), null=True, blank=True,
        help_text=_("For velocity rules: max allowed transactions in the time window."),
    )
    time_window_minutes = models.PositiveIntegerField(
        _("Time Window (minutes)"), null=True, blank=True,
        help_text=_("For velocity rules: the rolling window to count transactions in."),
    )
    blocked_values  = models.JSONField(
        _("Blocked Values"),
        default=list, blank=True,
        help_text=_("For GEO_BLOCK: list of country codes. For BIN_BLOCK: list of BINs."),
    )
    description = models.TextField(_("Description"), blank=True)

    class Meta:
        verbose_name = _("Fraud Rule")
        verbose_name_plural = _("Fraud Rules")
        ordering = ["-priority", "name"]

    def __str__(self):
        return f"{self.name} [{self.rule_type}] → {self.action}"


class FraudAssessment(TimestampedModel):
    """
    Per-transaction fraud risk assessment result.
    Created by the fraud engine before a payment is confirmed.
    """

    class Decision(models.TextChoices):
        ALLOW         = "allow",         _("Allowed")
        FLAG          = "flag",          _("Flagged — Manual Review")
        BLOCK         = "block",         _("Blocked")
        REQUIRE_3DS   = "require_3ds",   _("Require 3DS")
        REQUIRE_OTP   = "require_otp",   _("Require OTP")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_intent = models.ForeignKey(
        "PaymentIntent", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="fraud_assessments",
    )
    transaction = models.ForeignKey(
        "Transaction", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="fraud_assessments",
    )
    payment_profile = models.ForeignKey(
        TenantPaymentProfile, on_delete=models.CASCADE, related_name="fraud_assessments",
    )
    risk_score       = models.PositiveSmallIntegerField(_("Risk Score 0-100"), default=0)
    decision         = models.CharField(
        _("Decision"), max_length=15, choices=Decision.choices, default=Decision.ALLOW, db_index=True,
    )
    triggered_rules  = models.JSONField(
        _("Triggered Rules"),
        default=list,
        help_text=_("List of FraudRule IDs and names that matched this transaction."),
    )
    signals          = models.JSONField(
        _("Fraud Signals"),
        default=dict,
        help_text=_(
            "Detailed signals: {ip_country, card_country, email_velocity, "
            "card_velocity, is_proxy, geolocation, ...}"
        ),
    )
    customer_ip       = models.GenericIPAddressField(_("Customer IP"), null=True, blank=True)
    ip_country        = models.CharField(_("IP Country"), max_length=2, blank=True)
    card_country      = models.CharField(_("Card Country"), max_length=2, blank=True)
    is_proxy_ip       = models.BooleanField(_("Is Proxy IP"), default=False)
    device_fingerprint = models.CharField(_("Device Fingerprint"), max_length=500, blank=True)
    reviewed_by       = models.ForeignKey(
        "userauth.TenantUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="reviewed_fraud_assessments",
    )
    reviewed_at       = models.DateTimeField(_("Reviewed At"), null=True, blank=True)
    reviewer_decision = models.CharField(
        _("Reviewer Decision"), max_length=15,
        choices=[("approved", "Approved"), ("rejected", "Rejected"), ("pending", "Pending")],
        default="pending",
    )
    reviewer_note     = models.TextField(_("Reviewer Note"), blank=True)

    class Meta:
        verbose_name = _("Fraud Assessment")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["decision", "-created_at"]),
            models.Index(fields=["risk_score"]),
            models.Index(fields=["payment_profile", "decision"]),
        ]

    def __str__(self):
        return f"Fraud Assessment — Score: {self.risk_score} → {self.decision}"


class BlocklistEntry(TimestampedModel):
    """
    Blocked cards, emails, IPs, devices, or phone numbers.
    A tenant can maintain their own blocklist, and the platform
    maintains a shared blocklist for known fraudsters.
    """

    class EntryType(models.TextChoices):
        EMAIL           = "email",           _("Email Address")
        CARD_BIN        = "card_bin",        _("Card BIN (First 6 Digits)")
        CARD_HASH       = "card_hash",       _("Card Fingerprint Hash")
        IP_ADDRESS      = "ip_address",      _("IP Address")
        IP_CIDR         = "ip_cidr",         _("IP Range (CIDR)")
        PHONE           = "phone",           _("Phone Number")
        DEVICE          = "device",          _("Device Fingerprint")
        CUSTOMER_ID     = "customer_id",     _("Customer ID")
        BANK_ACCOUNT    = "bank_account",    _("Bank Account Number")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_profile = models.ForeignKey(
        TenantPaymentProfile, null=True, blank=True,
        on_delete=models.CASCADE, related_name="blocklist_entries",
        help_text=_("Null = platform-level blocklist shared across all tenants."),
    )
    entry_type   = models.CharField(_("Entry Type"), max_length=20, choices=EntryType.choices, db_index=True)
    value        = models.CharField(
        _("Value"),
        max_length=500,
        db_index=True,
        help_text=_("The email, BIN, IP, phone, etc. to block."),
    )
    value_hash   = models.CharField(
        _("Value Hash"),
        max_length=64,
        db_index=True,
        help_text=_("SHA-256 of value for fast lookups without exposing PII."),
    )
    reason       = models.TextField(_("Reason"))
    source       = models.CharField(
        _("Source"), max_length=30,
        choices=[
            ("fraud_case",    _("Fraud Case")),
            ("chargeback",    _("Chargeback")),
            ("manual_admin",  _("Manual — Admin")),
            ("manual_tenant", _("Manual — Merchant")),
            ("automated",     _("Automated Rule")),
            ("shared_list",   _("Platform Shared Blocklist")),
        ],
        default="manual_admin",
    )
    is_platform_wide = models.BooleanField(
        _("Platform-Wide"),
        default=False,
        help_text=_("If True, blocks across ALL tenants."),
    )
    expires_at   = models.DateTimeField(_("Expires At"), null=True, blank=True)
    added_by     = models.ForeignKey(
        "userauth.TenantUser", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="blocklist_entries",
    )
    source_transaction_id = models.UUIDField(_("Source Transaction ID"), null=True, blank=True)

    class Meta:
        verbose_name = _("Blocklist Entry")
        verbose_name_plural = _("Blocklist Entries")
        unique_together = [("entry_type", "value_hash", "payment_profile")]
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entry_type", "value_hash"]),
            models.Index(fields=["is_platform_wide"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"[{self.entry_type}] {self.value[:30]}... — {self.reason[:50]}"

    def save(self, *args, **kwargs):
        if self.value and not self.value_hash:
            self.value_hash = hashlib.sha256(self.value.lower().strip().encode()).hexdigest()
        super().save(*args, **kwargs)

    @classmethod
    def is_blocked(cls, entry_type: str, value: str, payment_profile=None) -> bool:
        """Fast check: is this value blocked?"""
        value_hash = hashlib.sha256(value.lower().strip().encode()).hexdigest()
        now = timezone.now()
        qs = cls.objects.filter(
            entry_type=entry_type,
            value_hash=value_hash,
        ).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        )
        if payment_profile:
            qs = qs.filter(
                models.Q(is_platform_wide=True) | models.Q(payment_profile=payment_profile)
            )
        else:
            qs = qs.filter(is_platform_wide=True)
        return qs.exists()


import hashlib  # noqa: E402 — needs to be available for BlocklistEntry.save()
