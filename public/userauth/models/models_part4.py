"""
payments/models_part4.py
========================
APP 8 — Payments Domain  |  Part 4 of 4

  Section 12 — Payment Disputes / Chargebacks   (tenant schema)
  Section 13 — Platform Fee Records             (tenant schema)
  Section 14 — Payment Refunds                  (tenant schema)
  Section 15 — KYC / Compliance                 (tenant schema)
  Section 16 — Gateway Mode Switch Audit Log    (tenant schema)
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models_part1 import UUIDModel, TimestampedModel, TenantBalance, PlatformLedgerEntry


# ─────────────────────────────────────────────────────────────
# SECTION 12 — PAYMENT DISPUTES / CHARGEBACKS  (tenant schema)
# ─────────────────────────────────────────────────────────────

class PaymentDispute(UUIDModel, TimestampedModel):
    """
    A chargeback or dispute initiated by a customer through their bank/card network.

    In MANAGED mode: the platform holds the disputed amount from the tenant's balance
    until the dispute is resolved. If lost, a CHARGEBACK_DEBIT ledger entry is written.
    If won, a CHARGEBACK_WIN entry credits the balance back.

    In DIRECT mode: the dispute is entirely between the tenant and their bank/gateway.
    We only track it for visibility — no ledger entries.
    """

    class DisputeStatus(models.TextChoices):
        OPEN = "OPEN",              _("Open — dispute raised")
        NEEDS_RESPONSE = "NEEDS_RESPONSE",    _(
            "Needs Response — deadline approaching")
        EVIDENCE_SUBMITTED = "EVIDENCE_SUBMITTED", _("Evidence Submitted")
        UNDER_REVIEW = "UNDER_REVIEW",      _("Under Review by card network")
        WON = "WON",               _("Won — in tenant's favour")
        LOST = "LOST",              _("Lost — in customer's favour")
        ACCEPTED = "ACCEPTED",          _("Accepted — merchant conceded")
        EXPIRED = "EXPIRED",           _("Expired — response window missed")

    class DisputeReason(models.TextChoices):
        FRAUDULENT = "fraudulent",          _("Fraudulent")
        DUPLICATE = "duplicate",           _("Duplicate charge")
        PRODUCT_NOT_RECEIVED = "product_not_received", _(
            "Product not received")
        PRODUCT_UNACCEPTABLE = "product_unacceptable", _(
            "Product unacceptable")
        CREDIT_NOT_PROCESSED = "credit_not_processed", _(
            "Credit not processed")
        SUBSCRIPTION_CANCELED = "subscription_canceled", _(
            "Subscription cancelled")
        UNRECOGNIZED = "unrecognized",        _("Unrecognized charge")
        GENERAL = "general",             _("General")

    # ── Relationships ─────────────────────────────────────────
    transaction = models.ForeignKey(
        "Transaction", on_delete=models.PROTECT, related_name="disputes"
    )
    gateway_config = models.ForeignKey(
        "TenantPaymentGateway", on_delete=models.PROTECT, related_name="disputes"
    )

    # ── Classification ────────────────────────────────────────
    status = models.CharField(
        max_length=22, choices=DisputeStatus.choices, default=DisputeStatus.OPEN, db_index=True)
    reason = models.CharField(
        max_length=30, choices=DisputeReason.choices, default=DisputeReason.GENERAL)
    was_managed_mode = models.BooleanField(default=True)

    # ── Amounts ───────────────────────────────────────────────
    disputed_amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency_code = models.CharField(max_length=3)
    chargeback_fee = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"),
                                         help_text="Fee charged by the gateway for the dispute, regardless of outcome")

    # ── Gateway dispute details ───────────────────────────────
    gateway_dispute_id = models.CharField(max_length=200, db_index=True)
    gateway_dispute_code = models.CharField(max_length=50, blank=True)
    gateway_evidence_due = models.DateTimeField(null=True, blank=True,
                                                help_text="Deadline to submit counter-evidence")
    gateway_response_raw = models.JSONField(default=dict, blank=True)

    # ── Evidence / response ───────────────────────────────────
    evidence_submitted_at = models.DateTimeField(null=True, blank=True)
    evidence_files = models.JSONField(default=list, blank=True,
                                      help_text="[{filename, url, type}] — uploaded evidence documents")
    evidence_notes = models.TextField(blank=True)
    merchant_statement = models.TextField(blank=True,
                                          help_text="Merchant's written rebuttal submitted to card network")

    # ── Resolution ────────────────────────────────────────────
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True,
                                       help_text="If merchant accepted the dispute without fighting it")

    # ── Balance hold (MANAGED mode) ───────────────────────────
    balance_held = models.BooleanField(default=False,
                                       help_text="True if we've already deducted the disputed amount from available_balance")
    balance_held_at = models.DateTimeField(null=True, blank=True)
    ledger_hold_entry = models.UUIDField(null=True, blank=True,
                                         help_text="PlatformLedgerEntry.id for the CHARGEBACK_DEBIT hold")
    ledger_win_entry = models.UUIDField(null=True, blank=True,
                                        help_text="PlatformLedgerEntry.id for the CHARGEBACK_WIN credit (if won)")

    class Meta:
        app_label = "payments"
        verbose_name = "Payment Dispute"
        verbose_name_plural = "Payment Disputes"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["gateway_dispute_id"]),
        ]

    def __str__(self) -> str:
        return f"Dispute {self.disputed_amount} {self.currency_code} [{self.status}]"

    @transaction.atomic
    def hold_balance(self) -> None:
        """
        Deduct disputed amount from available_balance into pending_balance hold.
        Called when dispute is first opened in MANAGED mode.
        """
        if not self.was_managed_mode or self.balance_held:
            return
        TenantBalance.objects.filter(currency_code=self.currency_code).update(
            available_balance=models.F(
                "available_balance") - self.disputed_amount,
        )
        entry = PlatformLedgerEntry.objects.create(
            entry_type=PlatformLedgerEntry.EntryType.CHARGEBACK_DEBIT,
            currency_code=self.currency_code,
            amount=-self.disputed_amount,
            running_balance=Decimal("0.00"),
            related_object_type="dispute",
            related_object_id=self.id,
            description=f"Chargeback hold — dispute {self.gateway_dispute_id}",
        )
        self.balance_held = True
        self.balance_held_at = timezone.now()
        self.ledger_hold_entry = entry.id
        self.save(update_fields=[
                  "balance_held", "balance_held_at", "ledger_hold_entry", "updated_at"])

    @transaction.atomic
    def mark_won(self, notes: str = "") -> None:
        """Dispute resolved in merchant's favour — release held funds."""
        self.status = self.DisputeStatus.WON
        self.resolved_at = timezone.now()
        self.resolution_notes = notes
        self.save(update_fields=["status", "resolved_at",
                  "resolution_notes", "updated_at"])
        if self.was_managed_mode and self.balance_held:
            TenantBalance.objects.filter(currency_code=self.currency_code).update(
                available_balance=models.F(
                    "available_balance") + self.disputed_amount,
            )
            entry = PlatformLedgerEntry.objects.create(
                entry_type=PlatformLedgerEntry.EntryType.CHARGEBACK_WIN,
                currency_code=self.currency_code,
                amount=self.disputed_amount,
                running_balance=Decimal("0.00"),
                related_object_type="dispute",
                related_object_id=self.id,
                description=f"Chargeback won — {self.gateway_dispute_id}",
            )
            self.ledger_win_entry = entry.id
            self.save(update_fields=["ledger_win_entry", "updated_at"])

    @transaction.atomic
    def mark_lost(self, notes: str = "") -> None:
        """Dispute lost — held funds are forfeited."""
        self.status = self.DisputeStatus.LOST
        self.resolved_at = timezone.now()
        self.resolution_notes = notes
        self.save(update_fields=["status", "resolved_at",
                  "resolution_notes", "updated_at"])
        # Held funds were already deducted — no further balance change needed.


# ─────────────────────────────────────────────────────────────
# SECTION 13 — PLATFORM FEE RECORDS  (tenant schema)
# ─────────────────────────────────────────────────────────────

class PlatformFeeRecord(UUIDModel, TimestampedModel):
    """
    Granular record of every fee the platform charged a tenant.
    Separate from PlatformLedgerEntry for accounting/invoicing purposes.

    Fees are only charged in MANAGED mode.
    """

    class FeeType(models.TextChoices):
        TRANSACTION_FEE = "TRANSACTION_FEE",   _("Transaction Fee (% of sale)")
        FIXED_CHARGE = "FIXED_CHARGE",      _("Fixed Per-Transaction Charge")
        PAYOUT_FEE = "PAYOUT_FEE",        _("Payout Processing Fee")
        GATEWAY_PASS_THROUGH = "GATEWAY_PASS_THROUGH", _(
            "Gateway Fee Pass-Through")
        CHARGEBACK_FEE = "CHARGEBACK_FEE",    _("Chargeback/Dispute Fee")
        MONTHLY_FEE = "MONTHLY_FEE",       _("Monthly Platform Fee")
        SETUP_FEE = "SETUP_FEE",         _("One-time Setup Fee")
        CUSTOM = "CUSTOM",            _("Custom / Manual Charge")

    # ── Relationships ─────────────────────────────────────────
    transaction_id = models.UUIDField(null=True, blank=True, db_index=True,
                                      help_text="Transaction.id this fee belongs to")
    payout_request_id = models.UUIDField(null=True, blank=True,
                                         help_text="PayoutRequest.id for payout fees")
    dispute_id = models.UUIDField(null=True, blank=True,
                                  help_text="PaymentDispute.id for chargeback fees")
    ledger_entry_id = models.UUIDField(null=True, blank=True,
                                       help_text="PlatformLedgerEntry.id for the debit")

    # ── Fee ───────────────────────────────────────────────────
    fee_type = models.CharField(max_length=24, choices=FeeType.choices)
    currency_code = models.CharField(max_length=3)
    amount = models.DecimalField(max_digits=14, decimal_places=2,
                                 validators=[MinValueValidator(Decimal("0.00"))])
    rate_applied = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True,
                                       help_text="The % rate used, for auditing rate changes over time")
    description = models.TextField(blank=True)

    # ── Billing period (for subscription/monthly fees) ────────
    billing_period_start = models.DateField(null=True, blank=True)
    billing_period_end = models.DateField(null=True, blank=True)
    invoice_id = models.CharField(max_length=100, blank=True,
                                  help_text="Platform invoice reference if fees are invoiced monthly")

    class Meta:
        app_label = "payments"
        verbose_name = "Platform Fee Record"
        verbose_name_plural = "Platform Fee Records"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["fee_type", "created_at"]),
            models.Index(fields=["transaction_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.fee_type} {self.amount} {self.currency_code}"


# ─────────────────────────────────────────────────────────────
# SECTION 14 — PAYMENT-LEVEL REFUNDS  (tenant schema)
# ─────────────────────────────────────────────────────────────

class PaymentRefund(UUIDModel, TimestampedModel):
    """
    Gateway-level refund record.
    Distinct from the order-domain Refund model (which is a business-logic record).
    This is the raw gateway refund execution record.

    A gateway refund can only be issued against a successful CHARGE Transaction.
    In MANAGED mode: updates TenantBalance and writes REFUND_DEBIT ledger entry.
    In DIRECT mode: gateway handles it directly, we only track the outcome.
    """

    class RefundStatus(models.TextChoices):
        PENDING = "PENDING",    _("Pending")
        PROCESSING = "PROCESSING", _("Processing")
        SUCCEEDED = "SUCCEEDED",  _("Succeeded")
        FAILED = "FAILED",     _("Failed")
        CANCELLED = "CANCELLED",  _("Cancelled")

    class RefundReason(models.TextChoices):
        DUPLICATE = "duplicate",     _("Duplicate charge")
        FRAUDULENT = "fraudulent",    _("Fraudulent transaction")
        CUSTOMER_REQUEST = "customer_request", _("Customer requested refund")
        ORDER_CANCELLED = "order_cancelled",  _("Order cancelled")
        RETURN = "return",        _("Product returned")
        PRICE_ADJUSTMENT = "price_adjustment", _("Price adjustment")
        OTHER = "other",         _("Other")

    # ── Relationships ─────────────────────────────────────────
    original_transaction = models.ForeignKey(
        "Transaction", on_delete=models.PROTECT, related_name="payment_refunds",
        help_text="The CHARGE transaction being refunded"
    )
    gateway_config = models.ForeignKey(
        "TenantPaymentGateway", on_delete=models.PROTECT, related_name="payment_refunds"
    )
    # Cross-app reference to order-domain Refund model
    order_refund_id = models.UUIDField(null=True, blank=True, db_index=True,
                                       help_text="orders.Refund.id that triggered this gateway refund")

    # ── Amounts ───────────────────────────────────────────────
    amount = models.DecimalField(max_digits=14, decimal_places=2,
                                 validators=[MinValueValidator(Decimal("0.01"))])
    currency_code = models.CharField(max_length=3)
    is_partial = models.BooleanField(default=False)

    # ── Status ────────────────────────────────────────────────
    status = models.CharField(
        max_length=12, choices=RefundStatus.choices, default=RefundStatus.PENDING)
    reason = models.CharField(
        max_length=20, choices=RefundReason.choices, default=RefundReason.OTHER)
    internal_note = models.TextField(blank=True)

    # ── Mode ──────────────────────────────────────────────────
    was_managed_mode = models.BooleanField(default=True)
    ledger_entry_id = models.UUIDField(null=True, blank=True)

    # ── Gateway ───────────────────────────────────────────────
    gateway_refund_id = models.CharField(
        max_length=200, blank=True, db_index=True)
    gateway_response_raw = models.JSONField(default=dict, blank=True)
    gateway_created_at = models.DateTimeField(null=True, blank=True)

    # ── Timing ────────────────────────────────────────────────
    initiated_by = models.UUIDField(
        null=True, blank=True, help_text="Staff user UUID")
    succeeded_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)

    class Meta:
        app_label = "payments"
        verbose_name = "Payment Refund"
        verbose_name_plural = "Payment Refunds"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Refund {self.amount} {self.currency_code} [{self.status}]"

    @transaction.atomic
    def mark_succeeded(self) -> None:
        self.status = self.RefundStatus.SUCCEEDED
        self.succeeded_at = timezone.now()
        self.save(update_fields=["status", "succeeded_at", "updated_at"])
        if self.was_managed_mode:
            TenantBalance.objects.filter(currency_code=self.currency_code).update(
                available_balance=models.F("available_balance") - self.amount,
                total_refunded=models.F("total_refunded") + self.amount,
            )
            from .models_part1 import TenantBalance as TB, PlatformLedgerEntry as PLE
            balance = TB.objects.get(currency_code=self.currency_code)
            entry = PLE.objects.create(
                entry_type=PLE.EntryType.REFUND_DEBIT,
                currency_code=self.currency_code,
                amount=-self.amount,
                running_balance=balance.available_balance,
                related_object_type="payment_refund",
                related_object_id=self.id,
                description=f"Refund — Order refund via {self.original_transaction.order_number}",
            )
            self.ledger_entry_id = entry.id
            self.save(update_fields=["ledger_entry_id", "updated_at"])


# ─────────────────────────────────────────────────────────────
# SECTION 15 — KYC / COMPLIANCE  (tenant schema)
# ─────────────────────────────────────────────────────────────

class MerchantKYCProfile(UUIDModel, TimestampedModel):
    """
    Tenant's KYC / compliance profile.
    Required before the platform allows payout requests above certain thresholds.
    One per tenant (schema-scoped singleton).
    """

    class VerificationLevel(models.TextChoices):
        NONE = "NONE",       _("Not verified")
        BASIC = "BASIC",      _("Basic — email + phone")
        STANDARD = "STANDARD",   _("Standard — ID document verified")
        ADVANCED = "ADVANCED",   _("Advanced — business documents verified")
        FULL = "FULL",       _("Full — all KYC complete")

    class KYCStatus(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", _("Not started")
        IN_PROGRESS = "IN_PROGRESS", _("Documents submitted, under review")
        APPROVED = "APPROVED",    _("Approved")
        REJECTED = "REJECTED",    _("Rejected — needs resubmission")
        SUSPENDED = "SUSPENDED",   _("Suspended — compliance hold")

    class BusinessType(models.TextChoices):
        INDIVIDUAL = "INDIVIDUAL",   _("Individual / Sole Trader")
        PARTNERSHIP = "PARTNERSHIP",  _("Partnership")
        LLC = "LLC",          _("Limited Liability Company")
        CORPORATION = "CORPORATION",  _("Corporation")
        NGO = "NGO",          _("Non-Profit / NGO")

    # ── Status ────────────────────────────────────────────────
    verification_level = models.CharField(max_length=10, choices=VerificationLevel.choices,
                                          default=VerificationLevel.NONE)
    kyc_status = models.CharField(max_length=12, choices=KYCStatus.choices,
                                  default=KYCStatus.NOT_STARTED)

    # ── Business info ─────────────────────────────────────────
    business_type = models.CharField(
        max_length=15, choices=BusinessType.choices, blank=True)
    business_name = models.CharField(max_length=300, blank=True)
    business_reg_number = models.CharField(max_length=100, blank=True,
                                           help_text="Company registration number / business ID")
    tax_id = models.CharField(
        max_length=50, blank=True, help_text="TIN / VAT ID")
    business_address = models.TextField(blank=True)
    business_country = models.CharField(max_length=2, blank=True)
    business_phone = models.CharField(max_length=20, blank=True)
    business_email = models.EmailField(blank=True)
    website_url = models.URLField(blank=True)
    industry = models.CharField(max_length=100, blank=True)
    mcc_code = models.CharField(max_length=4, blank=True,
                                help_text="Merchant Category Code (4-digit ISO 18245)")

    # ── Individual / director info ────────────────────────────
    director_first_name = models.CharField(max_length=100, blank=True)
    director_last_name = models.CharField(max_length=100, blank=True)
    director_dob = models.DateField(null=True, blank=True)
    director_id_type = models.CharField(max_length=20, blank=True,
                                        help_text="passport, national_id, drivers_license")
    director_id_number_enc = models.BinaryField(blank=True, null=True,
                                                help_text="ID number — encrypted at rest")
    director_id_number_masked = models.CharField(max_length=20, blank=True)
    director_nationality = models.CharField(max_length=2, blank=True)

    # ── Documents ─────────────────────────────────────────────
    documents = models.JSONField(default=list, blank=True,
                                 help_text="[{type, filename, url, uploaded_at, status}]")

    # ── Payout thresholds (set by platform after KYC) ─────────
    single_payout_limit = models.DecimalField(max_digits=18, decimal_places=2,
                                              null=True, blank=True,
                                              help_text="Max single payout allowed for this KYC level")
    daily_payout_limit = models.DecimalField(max_digits=18, decimal_places=2,
                                             null=True, blank=True)
    monthly_payout_limit = models.DecimalField(max_digits=18, decimal_places=2,
                                               null=True, blank=True)

    # ── Review ────────────────────────────────────────────────
    reviewed_by = models.UUIDField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    next_review_date = models.DateField(null=True, blank=True)

    class Meta:
        app_label = "payments"
        verbose_name = "Merchant KYC Profile"
        verbose_name_plural = "Merchant KYC Profiles"

    def __str__(self) -> str:
        return f"KYC {self.business_name or 'Unnamed'} [{self.kyc_status}]"

    @property
    def can_request_payout(self) -> bool:
        return self.kyc_status == self.KYCStatus.APPROVED

    @property
    def is_fully_verified(self) -> bool:
        return self.verification_level == self.VerificationLevel.FULL


# ─────────────────────────────────────────────────────────────
# SECTION 16 — GATEWAY MODE SWITCH AUDIT LOG  (tenant schema)
# ─────────────────────────────────────────────────────────────

class GatewayModeSwitchLog(UUIDModel, TimestampedModel):
    """
    Immutable audit trail of every MANAGED ↔ DIRECT mode switch per gateway config.

    This ensures we can always reconstruct:
      - When the tenant switched
      - Who initiated the switch
      - What keys were active at the time (not the keys themselves — just that they changed)
      - What the balance state was at switch time
    """

    class SwitchDirection(models.TextChoices):
        MANAGED_TO_DIRECT = "MANAGED_TO_DIRECT", _("Managed → Direct")
        DIRECT_TO_MANAGED = "DIRECT_TO_MANAGED", _("Direct → Managed")

    gateway_config = models.ForeignKey(
        "TenantPaymentGateway", on_delete=models.PROTECT, related_name="mode_switch_log"
    )

    direction = models.CharField(
        max_length=18, choices=SwitchDirection.choices)
    switched_by = models.UUIDField(null=True, blank=True,
                                   help_text="User UUID who made the switch (tenant owner or platform admin)")
    reason = models.TextField(blank=True)

    # ── Balance snapshot at time of switch ───────────────────
    balance_at_switch = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"),
                                            help_text="TenantBalance.available_balance at the moment of switch")
    currency_code = models.CharField(max_length=3)
    pending_payout_requests_count = models.PositiveIntegerField(default=0,
                                                                help_text="How many open PayoutRequests existed at switch time")

    # ── Keys verification state at switch time ────────────────
    keys_were_verified = models.BooleanField(default=False,
                                             help_text="Were the tenant's direct-mode keys verified at time of switch?")

    # ── Platform admin action ─────────────────────────────────
    is_platform_action = models.BooleanField(default=False,
                                             help_text="True if a platform admin forced the switch (e.g. compliance action)")
    platform_note = models.TextField(blank=True)

    class Meta:
        app_label = "payments"
        verbose_name = "Gateway Mode Switch Log"
        verbose_name_plural = "Gateway Mode Switch Logs"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValueError("GatewayModeSwitchLog is immutable.")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.direction} at {self.created_at:%Y-%m-%d %H:%M}"

# ─────────────────────────────────────────────────────────────
# SECTION 15 — CUSTOMER GROUPS  (tenant schema)
# ─────────────────────────────────────────────────────────────


class CustomerGroup(AuditModel, MixIdAndTimeModel):
    """
    Tenant-defined customer segments.
    Used to gate: pricing tiers, discount codes, shipping rates,
    wholesale access, VIP benefits.

    Groups can be manually assigned or rule-based (auto-assign).
    """

    class GroupType(models.TextChoices):
        MANUAL = "MANUAL",      _("Manual — staff assigns customers")
        AUTOMATIC = "AUTOMATIC",   _("Automatic — rule-based assignment")
        SYSTEM = "SYSTEM",      _("System — built-in (e.g. All Customers)")

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    group_type = models.CharField(max_length=12, choices=GroupType.choices,
                                  default=GroupType.MANUAL)
    color = models.CharField(max_length=7, default="#4c4c88")

    # Auto-assignment rules (used when group_type=AUTOMATIC)
    # Rules engine: JSON with conditions checked against customer data
    auto_rules = models.JSONField(default=dict, blank=True,
                                  help_text="Rules for automatic membership: "
                                  "{min_order_count, min_total_spend, tags, country, ...}")

    is_system = models.BooleanField(default=False,
                                    help_text="System groups cannot be deleted")
    sort_order = models.PositiveSmallIntegerField(default=100)

    # Stats (updated periodically by background task)
    customer_count = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "accounts"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name

    def delete(self, *args, **kwargs):
        if self.is_system:
            raise ValueError(f"System group '{self.name}' cannot be deleted.")
        super().delete(*args, **kwargs)


# ─────────────────────────────────────────────────────────────
# SECTION 16 — CUSTOMER  (tenant schema)
# ─────────────────────────────────────────────────────────────

class Customer(MixIdAndTimeModel):
    """
    Store-facing buyer profile — lives in the TENANT schema.

    Owns ALL store-specific commerce data: financial stats, segmentation,
    marketing consent, acquisition attribution, and locale overrides.

    Guest customers (checkout without an account) have user=None.
    One platform User can have one Customer record per tenant store.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE",   _("Active")
        INACTIVE = "INACTIVE", _("Inactive — no recent activity")
        BLOCKED = "BLOCKED",  _("Blocked — banned from store")
        ARCHIVED = "ARCHIVED", _("Archived — soft deleted")

    class AcquisitionSource(models.TextChoices):
        ORGANIC = "organic",     _("Organic / Direct")
        REFERRAL = "referral",    _("Referral")
        SOCIAL = "social",      _("Social Media")
        EMAIL = "email",       _("Email Campaign")
        PAID_ADS = "paid_ads",    _("Paid Advertising")
        MARKETPLACE = "marketplace", _("Marketplace")
        MANUAL = "manual",      _("Added manually by staff")
        IMPORT = "import",      _("Imported via CSV")

    class TaxExemptStatus(models.TextChoices):
        NOT_EXEMPT = "NOT_EXEMPT", _("Taxable")
        EXEMPT = "EXEMPT",     _("Tax exempt")
        REVERSE = "REVERSE",    _("Reverse charge (B2B)")

    class CustomerTier(models.TextChoices):
        STANDARD = "standard",  _("Standard")
        SILVER = "silver",    _("Silver")
        GOLD = "gold",      _("Gold")
        PLATINUM = "platinum",  _("Platinum")
        VIP = "vip",       _("VIP")

    # ── Identity ──────────────────────────────────────────────────────
    # Null for guest checkouts.
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="customer_profile",
        help_text=_("Platform user. Null for guest customers."),
    )

    # ── Status ────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )

    # ── Segmentation ──────────────────────────────────────────────────
    groups = models.ManyToManyField(
        "CustomerGroup",
        blank=True,
        related_name="customers",
    )
    tags = models.JSONField(
        default=list,
        help_text=_(
            "Freeform tags for segmentation, e.g. ['vip', 'wholesale']."),
    )
    # Computed tier based on LTV / order count (updated by signal/task).
    tier = models.CharField(
        max_length=20,
        choices=CustomerTier.choices,
        blank=True,
        db_index=True,
        help_text=_("Loyalty tier — recalculated automatically."),
    )
    loyalty_points = models.PositiveIntegerField(default=0)

    # ── Financial stats (updated by order signals / celery tasks) ─────
    total_orders = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(
        max_digits=18, decimal_places=2, default=0)
    average_order_value = models.DecimalField(
        max_digits=14, decimal_places=2, default=0)
    total_refunds = models.DecimalField(
        max_digits=14, decimal_places=2, default=0)
    first_order_at = models.DateTimeField(null=True, blank=True)
    last_order_at = models.DateTimeField(null=True, blank=True)

    # ── Store credit (uncomment when feature is ready) ────────────────
    # store_credit_balance = models.DecimalField(
    #     max_digits=14, decimal_places=2, default=0,
    #     help_text=_("Credit balance redeemable at checkout."),
    # )
    # outstanding_balance = models.DecimalField(
    #     max_digits=14, decimal_places=2, default=0,
    #     help_text=_("Unpaid balance for net-terms / store credit."),
    # )

    # ── Tax ───────────────────────────────────────────────────────────
    tax_exempt_status = models.CharField(
        max_length=12,
        choices=TaxExemptStatus.choices,
        default=TaxExemptStatus.NOT_EXEMPT,
    )
    tax_id = models.CharField(
        max_length=50,
        blank=True,
        help_text=_("VAT / EIN / TIN for B2B customers."),
    )

    # ── B2B / company ─────────────────────────────────────────────────
    company = models.CharField(max_length=200, blank=True)
    is_b2b = models.BooleanField(
        default=False,
        help_text=_("Business customer — show wholesale pricing."),
    )

    # ── Marketing & consent ───────────────────────────────────────────
    email_marketing_consent = models.BooleanField(default=False)
    sms_marketing_consent = models.BooleanField(default=False)
    marketing_consent_at = models.DateTimeField(null=True, blank=True)
    marketing_consent_ip = models.GenericIPAddressField(null=True, blank=True)

    # ── Acquisition ───────────────────────────────────────────────────
    acquisition_source = models.CharField(
        max_length=15,
        choices=AcquisitionSource.choices,
        blank=True,
    )
    referral_code = models.CharField(max_length=50,  blank=True)
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)

    # ── Activity ──────────────────────────────────────────────────────
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_ip = models.GenericIPAddressField(null=True, blank=True)
    login_count = models.PositiveIntegerField(default=0)

    # ── Staff-facing notes ────────────────────────────────────────────
    # One quick note here; full audit trail lives in CustomerNote model.
    staff_note = models.TextField(blank=True)

    class Meta:
        app_label = "accounts"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["total_spent"]),
            models.Index(fields=["last_order_at"]),
        ]

    def __str__(self) -> str:
        return f"{user}"

    @property
    def is_registered(self) -> bool:
        return self.user_id is not None

    @property
    def is_guest(self) -> bool:
        return self.user_id is None

    @property
    def display_name(self) -> str:
        name = self.get_full_name()
        if self.company:
            return f"{name} ({self.company})"
        return name

    def update_order_stats(
        self,
        order_total: "Decimal",
        order_at: "datetime",
        is_new_order: bool = True,
    ) -> None:
        """Called by order signal after order confirmation."""
        from decimal import Decimal
        if is_new_order:
            self.total_orders += 1
            self.total_spent += order_total
            if not self.first_order_at:
                self.first_order_at = order_at
            self.last_order_at = order_at
            if self.total_orders:
                self.average_order_value = self.total_spent / self.total_orders
        self.save(update_fields=[
            "total_orders", "total_spent", "average_order_value",
            "first_order_at", "last_order_at", "updated_at"
        ])


# ─────────────────────────────────────────────────────────────
# SECTION 17 — CUSTOMER ADDRESSES  (tenant schema)
# ─────────────────────────────────────────────────────────────

class CustomerAddress(MixIdAndTimeModel):
    """
    Saved addresses for a customer.
    A customer can have multiple addresses with one default each
    for shipping and billing.
    """

    class AddressType(models.TextChoices):
        SHIPPING = "SHIPPING", _("Shipping")
        BILLING = "BILLING",  _("Billing")
        BOTH = "BOTH",     _("Shipping & Billing")

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE,
                                 related_name="addresses")
    address_type = models.CharField(max_length=10, choices=AddressType.choices,
                                    default=AddressType.BOTH)

    # ── Fields ────────────────────────────────────────────────
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    company = models.CharField(max_length=200, blank=True)
    address1 = models.CharField(max_length=300,
                                help_text="Street address line 1")
    address2 = models.CharField(max_length=300, blank=True,
                                help_text="Apartment, suite, unit, etc.")
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True,
                             help_text="State / Province / Region")
    postal_code = models.CharField(max_length=20, blank=True)
    country_code = models.CharField(max_length=2,
                                    help_text="ISO 3166-1 alpha-2 country code")
    phone = models.CharField(max_length=30, blank=True)

    # Geolocation (optional)
    latitude = models.DecimalField(
        max_digits=10, decimal_places=8, null=True, blank=True)
    longitude = models.DecimalField(
        max_digits=11, decimal_places=8, null=True, blank=True)

    # Preferences
    is_default = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    # ── Defaults ──────────────────────────────────────────────
    is_default_shipping = models.BooleanField(default=False)
    is_default_billing = models.BooleanField(default=False)

    # ── Validation ────────────────────────────────────────────
    is_validated = models.BooleanField(default=False,
                                       help_text="Address confirmed valid by address validation API")
    validated_at = models.DateTimeField(null=True, blank=True)
    validation_raw = models.JSONField(null=True, blank=True,
                                      help_text="Raw response from address validation service")

    class Meta:
        app_label = "accounts"
        ordering = ["-is_default_shipping", "-created_at"]

    def __str__(self) -> str:
        return f"{self.address1}, {self.city}, {self.country_code}"

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def single_line(self) -> str:
        parts = [self.address1]
        if self.address2:
            parts.append(self.address2)
        parts += [self.city, self.state, self.postal_code, self.country_code]
        return ", ".join(p for p in parts if p)

    def save(self, *args, **kwargs):
        # Enforce single default per type per customer
        if self.is_default_shipping:
            CustomerAddress.objects.filter(
                customer=self.customer, is_default_shipping=True
            ).exclude(pk=self.pk).update(is_default_shipping=False)
        if self.is_default_billing:
            CustomerAddress.objects.filter(
                customer=self.customer, is_default_billing=True
            ).exclude(pk=self.pk).update(is_default_billing=False)
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────
# SECTION 18 — CUSTOMER NOTES  (tenant schema)
# ─────────────────────────────────────────────────────────────

class CustomerNote(MixIdAndTimeModel):
    """
    Staff-written notes on a customer record.
    Append-only — staff can add but not edit past notes.
    """

    class NoteType(models.TextChoices):
        GENERAL = "GENERAL",   _("General note")
        COMPLAINT = "COMPLAINT", _("Complaint")
        VIP = "VIP",       _("VIP note")
        FRAUD = "FRAUD",     _("Fraud flag")
        SUPPORT = "SUPPORT",   _("Support interaction")

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE,
                                 related_name="notes")
    written_by = models.UUIDField(help_text="StoreStaff.user_id")
    written_by_name = models.CharField(max_length=200)
    note_type = models.CharField(max_length=12, choices=NoteType.choices,
                                 default=NoteType.GENERAL)
    content = models.TextField()
    is_pinned = models.BooleanField(default=False)

    class Meta:
        app_label = "accounts"
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self) -> str:
        return f"Note on {self.customer.email} by {self.written_by_name}"


# ─────────────────────────────────────────────────────────────
# SECTION 19 — CUSTOMER SESSIONS  (tenant schema)
# ─────────────────────────────────────────────────────────────

class CustomerSession(MixIdAndTimeModel):
    """
    Active storefront session for a logged-in customer.
    Separate from Django's session framework — provides richer
    device tracking and concurrent session management.
    """

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE,
                                 related_name="sessions")
    session_token = models.CharField(
        max_length=128, unique=True, db_index=True)

    # Device / browser fingerprint
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    device_type = models.CharField(max_length=20, blank=True)
    browser = models.CharField(max_length=50, blank=True)
    os = models.CharField(max_length=50, blank=True)
    device_name = models.CharField(max_length=100, blank=True,
                                   help_text="e.g. 'Chrome on macOS', 'iPhone 14'")
    country_code = models.CharField(max_length=2, blank=True)

    # Timing
    last_active_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "accounts"
        ordering = ["-last_active_at"]

    def __str__(self) -> str:
        return f"Session({self.customer.email}, {self.device_name or 'Unknown'})"

    @classmethod
    def create_for_customer(cls, customer: Customer, ip: str = "",
                            user_agent: str = "", ttl_days: int = 30) -> "CustomerSession":
        from datetime import timedelta
        return cls.objects.create(
            customer=customer,
            session_token=secrets.token_urlsafe(64),
            ip_address=ip or None,
            user_agent=user_agent,
            expires_at=timezone.now() + timedelta(days=ttl_days),
        )

    @property
    def is_valid(self) -> bool:
        return self.is_active and timezone.now() < self.expires_at

    def terminate(self) -> None:
        self.is_active = False
        self.save(update_fields=["is_active"])


# ─────────────────────────────────────────────────────────────
# SECTION 20 — GUEST TOKENS  (tenant schema)
# ─────────────────────────────────────────────────────────────

class GuestToken(MixIdAndTimeModel):
    """
    Anonymous session token for guests (non-registered shoppers).
    Used to persist cart, wishlist, and abandoned checkout state
    without requiring account creation.

    When a guest registers or logs in, their GuestToken is merged
    with their Customer account and this record is marked converted.
    """

    token = models.CharField(max_length=128, unique=True, db_index=True)
    email = models.EmailField(blank=True,
                              help_text="Captured at checkout start — enables abandonment emails")

    # Converted to a Customer on registration
    customer = models.ForeignKey(Customer, null=True, blank=True,
                                 on_delete=models.SET_NULL, related_name="guest_tokens")
    converted_at = models.DateTimeField(null=True, blank=True)
    is_converted = models.BooleanField(default=False)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        app_label = "accounts"
        ordering = ["-created_at"]

    @classmethod
    def create(cls, ip: str = "", user_agent: str = "") -> "GuestToken":
        from datetime import timedelta
        return cls.objects.create(
            token=secrets.token_urlsafe(64),
            ip_address=ip or None,
            user_agent=user_agent,
            expires_at=timezone.now() + timedelta(days=90),
        )

    @property
    def is_valid(self) -> bool:
        return not self.is_converted and timezone.now() < self.expires_at

    def convert_to_customer(self, customer: Customer) -> None:
        self.customer = customer
        self.is_converted = True
        self.converted_at = timezone.now()
        self.save(update_fields=["customer", "is_converted", "converted_at"])
