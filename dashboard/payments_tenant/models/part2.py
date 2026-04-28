"""
payments/models_part2.py — Part 2 of 4
Sections: Commission, Transactions, Saved Methods, Refunds, Disputes
"""
import uuid
from decimal import Decimal
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .core import AppendOnlyModel, TenantGatewayMode, TenantPaymentProfile, TimestampedModel, TransactionStatus


class CommissionRule(TimestampedModel):
    """Platform fee structure for PLATFORM MODE transactions."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Rule Name"), max_length=255)
    gateway = models.ForeignKey(
        "system_pay.PaymentGatewayDefinition", null=True, blank=True,
        on_delete=models.CASCADE, related_name="commission_rules",
        help_text=_("Null = applies to all gateways."),
    )
    subscription_plan = models.CharField(_("Subscription Plan"), max_length=100, blank=True)
    country_code      = models.CharField(_("Country Code (ISO)"), max_length=2, blank=True)
    currency          = models.CharField(_("Currency"), max_length=3, blank=True)
    percentage_rate   = models.DecimalField(
        _("Rate (%)"), max_digits=6, decimal_places=4, default=Decimal("2.5000"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    flat_fee          = models.DecimalField(_("Flat Fee"), max_digits=10, decimal_places=2, default=Decimal("0.00"))
    cap_amount        = models.DecimalField(_("Commission Cap"), max_digits=10, decimal_places=2, null=True, blank=True)
    minimum_fee       = models.DecimalField(_("Minimum Fee"), max_digits=10, decimal_places=2, default=Decimal("0.00"))
    monthly_volume_threshold = models.DecimalField(
        _("Monthly Volume Threshold"), max_digits=18, decimal_places=2, null=True, blank=True,
    )
    gateway_fee_absorbed        = models.BooleanField(_("Platform Absorbs Gateway Fee"), default=False)
    gateway_fee_pass_through_rate = models.DecimalField(
        _("Gateway Fee Pass-Through (%)"), max_digits=6, decimal_places=4, null=True, blank=True,
    )
    is_active   = models.BooleanField(_("Active"), default=True, db_index=True)
    priority    = models.PositiveIntegerField(_("Priority"), default=0)
    description = models.TextField(_("Description"), blank=True)

    class Meta:
        verbose_name = _("Commission Rule")
        ordering = ["-priority", "name"]
        indexes = [
            models.Index(fields=["is_active", "-priority"]),
            models.Index(fields=["gateway", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} — {self.percentage_rate}% + {self.flat_fee}"

    def calculate_commission(self, amount: Decimal) -> Decimal:
        TWO = Decimal("0.01")
        commission = max(
            self.minimum_fee,
            (amount * self.percentage_rate / Decimal("100")).quantize(TWO) + self.flat_fee,
        )
        if self.cap_amount:
            commission = min(commission, self.cap_amount)
        return commission.quantize(TWO)


class CommissionEntry(AppendOnlyModel):
    """Immutable per-transaction commission record. APPEND-ONLY."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id   = models.UUIDField(_("Transaction ID"), unique=True, db_index=True)
    payment_profile  = models.ForeignKey(TenantPaymentProfile, on_delete=models.CASCADE, related_name="commission_entries")
    gateway_mode     = models.ForeignKey(TenantGatewayMode, null=True, blank=True, on_delete=models.SET_NULL, related_name="commission_entries")
    commission_rule  = models.ForeignKey(CommissionRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="commission_entries")
    gross_amount     = models.DecimalField(_("Gross Amount"), max_digits=14, decimal_places=2)
    gateway_fee      = models.DecimalField(_("Gateway Fee"), max_digits=10, decimal_places=2, default=Decimal("0.00"))
    platform_commission = models.DecimalField(_("Platform Commission"), max_digits=10, decimal_places=2, default=Decimal("0.00"))
    tenant_net       = models.DecimalField(_("Tenant Net"), max_digits=14, decimal_places=2)
    currency         = models.CharField(_("Currency"), max_length=3)
    payment_mode     = models.CharField(_("Payment Mode"), max_length=10)
    commission_rate  = models.DecimalField(_("Rate Applied (%)"), max_digits=6, decimal_places=4, default=Decimal("0.0000"))
    commission_flat_fee = models.DecimalField(_("Flat Fee Applied"), max_digits=10, decimal_places=2, default=Decimal("0.00"))
    gateway_provider = models.CharField(_("Gateway Provider"), max_length=20, blank=True)
    order_id         = models.UUIDField(_("Order ID"), null=True, blank=True, db_index=True)
    order_number     = models.CharField(_("Order Number"), max_length=50, blank=True)

    class Meta:
        verbose_name = _("Commission Entry")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["payment_profile", "-created_at"]),
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["order_id"]),
        ]

    def __str__(self):
        return f"Commission {self.transaction_id} — Platform: {self.platform_commission}, Tenant: {self.tenant_net} {self.currency}"

    @property
    def transaction(self):
        return Transaction.objects.filter(id=self.transaction_id).first()


class PaymentIntent(TimestampedModel):
    """Payment session created at checkout before any payment is made."""

    class IntentStatus(models.TextChoices):
        REQUIRES_PAYMENT_METHOD = "requires_payment_method", _("Awaiting Payment Method")
        REQUIRES_CONFIRMATION   = "requires_confirmation",   _("Awaiting Confirmation")
        REQUIRES_ACTION         = "requires_action",         _("Requires 3DS Action")
        PROCESSING              = "processing",              _("Processing")
        SUCCEEDED               = "succeeded",               _("Succeeded")
        CANCELLED               = "cancelled",               _("Cancelled")
        ABANDONED               = "abandoned",               _("Abandoned")
        EXPIRED                 = "expired",                 _("Expired")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_profile = models.ForeignKey(TenantPaymentProfile, on_delete=models.CASCADE, related_name="payment_intents")
    gateway_mode    = models.ForeignKey(TenantGatewayMode, null=True, blank=True, on_delete=models.SET_NULL, related_name="payment_intents")
    order_id        = models.UUIDField(_("Order ID"), db_index=True, null=True, blank=True)
    order_number    = models.CharField(_("Order Number"), max_length=100, blank=True, db_index=True)
    amount          = models.DecimalField(_("Amount"), max_digits=14, decimal_places=2)
    currency        = models.CharField(_("Currency"), max_length=3)
    status          = models.CharField(
        _("Status"), max_length=30, choices=IntentStatus.choices,
        default=IntentStatus.REQUIRES_PAYMENT_METHOD, db_index=True,
    )
    failure_code        = models.CharField(_("Failure Code"), max_length=100, blank=True)
    failure_message     = models.TextField(_("Failure Message"), blank=True)
    cancellation_reason = models.CharField(_("Cancellation Reason"), max_length=255, blank=True)

    # ── Customer ──
    customer_id         = models.UUIDField(_("Customer ID"), null=True, blank=True, db_index=True)
    customer_email      = models.EmailField(_("Customer Email"), blank=True)
    customer_name       = models.CharField(_("Customer Name"), max_length=255, blank=True)
    customer_phone      = models.CharField(_("Customer Phone"), max_length=30, blank=True)
    customer_ip         = models.GenericIPAddressField(_("Customer IP"), null=True, blank=True)
    customer_user_agent = models.TextField(_("User Agent"), blank=True)

    # ── Gateway ──
    gateway_intent_id        = models.CharField(_("Gateway Reference"), max_length=500, blank=True, db_index=True)
    gateway_authorization_url = models.URLField(_("Gateway Auth URL"), blank=True)
    gateway_access_code      = models.CharField(_("Access Code"), max_length=500, blank=True)
    client_secret            = models.CharField(_("Client Secret"), max_length=500, blank=True)

    # ── Context ──
    payment_mode        = models.CharField(_("Payment Mode"), max_length=10, blank=True)
    payment_method_type = models.CharField(_("Payment Method Type"), max_length=30, blank=True)
    metadata            = models.JSONField(_("Metadata"), default=dict, blank=True)
    success_url         = models.URLField(_("Success URL"), blank=True)
    failure_url         = models.URLField(_("Failure URL"), blank=True)
    cancel_url          = models.URLField(_("Cancel URL"), blank=True)
    callback_url        = models.URLField(_("Callback URL"), blank=True)

    # ── Split payment params ──
    subaccount_code    = models.CharField(_("Subaccount Code"), max_length=255, blank=True)
    transaction_charge = models.DecimalField(_("Platform Charge"), max_digits=10, decimal_places=2, null=True, blank=True)
    bearer             = models.CharField(_("Fee Bearer"), max_length=20, blank=True, choices=[("account", "Platform"), ("subaccount", "Tenant")])

    # ── Timing ──
    expires_at   = models.DateTimeField(_("Expires At"), null=True, blank=True, db_index=True)
    succeeded_at = models.DateTimeField(_("Succeeded At"), null=True, blank=True)
    abandoned_at = models.DateTimeField(_("Abandoned At"), null=True, blank=True)

    class Meta:
        verbose_name = _("Payment Intent")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["order_id"]),
            models.Index(fields=["order_number"]),
            models.Index(fields=["gateway_intent_id"]),
            models.Index(fields=["customer_id"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Intent {self.id} — {self.amount} {self.currency} [{self.status}]"


class Transaction(TimestampedModel):
    """Confirmed payment record. Created on gateway acceptance."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_intent  = models.ForeignKey(PaymentIntent, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")
    payment_profile = models.ForeignKey(TenantPaymentProfile, on_delete=models.CASCADE, related_name="transactions")
    gateway_mode    = models.ForeignKey(TenantGatewayMode, null=True, blank=True, on_delete=models.SET_NULL, related_name="transactions")

    # ── References ──
    order_id               = models.UUIDField(_("Order ID"), null=True, blank=True, db_index=True)
    order_number           = models.CharField(_("Order Number"), max_length=100, blank=True, db_index=True)
    gateway_transaction_id = models.CharField(_("Gateway Transaction ID"), max_length=500, blank=True, db_index=True)
    gateway_reference      = models.CharField(_("Gateway Reference"), max_length=500, blank=True, db_index=True)
    internal_reference     = models.CharField(_("Internal Reference"), max_length=100, unique=True, db_index=True)

    # ── Status ──
    status        = models.CharField(_("Status"), max_length=15, choices=TransactionStatus.choices, default=TransactionStatus.INITIATED, db_index=True)
    status_reason = models.CharField(_("Status Reason"), max_length=500, blank=True)

    # ── Amounts ──
    amount              = models.DecimalField(_("Amount"), max_digits=14, decimal_places=2)
    currency            = models.CharField(_("Currency"), max_length=3)
    gateway_fee         = models.DecimalField(_("Gateway Fee"), max_digits=10, decimal_places=2, default=Decimal("0.00"))
    platform_commission = models.DecimalField(_("Platform Commission"), max_digits=10, decimal_places=2, default=Decimal("0.00"))
    tenant_net          = models.DecimalField(_("Tenant Net"), max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_refunded     = models.DecimalField(_("Amount Refunded"), max_digits=14, decimal_places=2, default=Decimal("0.00"))

    # ── Mode snapshot (immutable audit) ──
    payment_mode     = models.CharField(_("Payment Mode"), max_length=10)
    gateway_provider = models.CharField(_("Gateway Provider"), max_length=20, blank=True)
    mode_snapshot    = models.JSONField(_("Mode Snapshot"), default=dict)

    # ── Customer ──
    customer_id    = models.UUIDField(_("Customer ID"), null=True, blank=True, db_index=True)
    customer_email = models.EmailField(_("Customer Email"), blank=True)
    customer_name  = models.CharField(_("Customer Name"), max_length=255, blank=True)
    customer_phone = models.CharField(_("Customer Phone"), max_length=30, blank=True)
    customer_ip    = models.GenericIPAddressField(_("Customer IP"), null=True, blank=True)

    # ── Payment method ──
    payment_method_type = models.CharField(_("Method Type"), max_length=30, blank=True)
    payment_channel     = models.CharField(_("Channel"), max_length=50, blank=True)
    saved_method_id     = models.UUIDField(_("Saved Method ID"), null=True, blank=True)

    # ── Raw gateway data ──
    raw_gateway_response = models.JSONField(_("Raw Gateway Response"), default=dict)
    gateway_message      = models.CharField(_("Gateway Message"), max_length=500, blank=True)
    gateway_ip_address   = models.GenericIPAddressField(_("Gateway IP"), null=True, blank=True)

    # ── Timing ──
    initiated_at = models.DateTimeField(_("Initiated At"), null=True, blank=True)
    paid_at      = models.DateTimeField(_("Paid At"), null=True, blank=True, db_index=True)
    settled_at   = models.DateTimeField(_("Settled At"), null=True, blank=True)
    reversed_at  = models.DateTimeField(_("Reversed At"), null=True, blank=True)

    # ── Flags ──
    is_test                 = models.BooleanField(_("Test"), default=False, db_index=True)
    is_disputed             = models.BooleanField(_("Disputed"), default=False)
    is_refunded             = models.BooleanField(_("Fully Refunded"), default=False)
    is_partially_refunded   = models.BooleanField(_("Partially Refunded"), default=False)
    risk_score              = models.PositiveSmallIntegerField(_("Risk Score 0-100"), null=True, blank=True)
    is_flagged              = models.BooleanField(_("Fraud Flagged"), default=False, db_index=True)

    # ── Purpose ── (e.g. "addon_purchase", "storefront_order", "subscription")
    purpose = models.CharField(
        _("Purpose"),
        max_length=50,
        blank=True,
        db_index=True,
        help_text=_("Business context for this payment, e.g. addon_purchase, storefront_order, subscription."),
    )

    class Meta:
        verbose_name = _("Transaction")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-paid_at"]),
            models.Index(fields=["order_id"]),
            models.Index(fields=["order_number"]),
            models.Index(fields=["gateway_transaction_id"]),
            models.Index(fields=["gateway_reference"]),
            models.Index(fields=["customer_id", "-created_at"]),
            models.Index(fields=["payment_profile", "status"]),
            models.Index(fields=["payment_mode", "status"]),
        ]

    def __str__(self):
        return f"Transaction {self.internal_reference} — {self.amount} {self.currency} [{self.status}]"

    # ── Forward-only status guard ────────────────────────────────────────────
    # Status transitions are strictly additive: once a terminal state is
    # reached it cannot be reversed.  Any attempt is silently ignored here
    # and should be prevented at the service layer before save() is called.
    _TERMINAL_STATUSES = frozenset({
        TransactionStatus.SUCCESS,
        TransactionStatus.FAILED,
        TransactionStatus.REVERSED,
        TransactionStatus.ABANDONED,
        TransactionStatus.CANCELLED,
    })

    def save(self, *args, **kwargs):
        if self.pk:
            # Only enforce on existing records; new records have no prior status.
            try:
                previous = Transaction.objects.only("status").get(pk=self.pk)
                if previous.status in self._TERMINAL_STATUSES and previous.status != self.status:
                    import logging
                    logging.getLogger("payments").warning(
                        "Forward-only guard: attempt to move transaction %s from '%s' -> '%s' blocked.",
                        self.pk, previous.status, self.status,
                    )
                    self.status = previous.status  # restore
            except Transaction.DoesNotExist:
                pass
        super().save(*args, **kwargs)

    @property
    def is_successful(self) -> bool:
        return self.status == TransactionStatus.SUCCESS

    @property
    def refundable_amount(self) -> Decimal:
        return max(Decimal("0.00"), self.amount - self.amount_refunded)

    @property
    def net_amount(self):
        return self.tenant_net

    @property
    def commission_amount(self):
        return self.platform_commission

    @property
    def customer_ip_address(self):
        return self.customer_ip

    @property
    def customer_country(self):
        return self.mode_snapshot.get("customer_country", "")

    @property
    def channel(self):
        return self.payment_channel

    @property
    def success_at(self):
        return self.paid_at

    @property
    def failure_reason(self):
        return self.status_reason or self.gateway_message


class TransactionEvent(AppendOnlyModel):
    """Append-only status timeline per Transaction. NEVER update or delete."""

    class EventType(models.TextChoices):
        INITIATED         = "initiated",         _("Initiated")
        PENDING           = "pending",           _("Pending")
        PROCESSING        = "processing",        _("Processing")
        SUCCEEDED         = "succeeded",         _("Succeeded")
        FAILED            = "failed",            _("Failed")
        ABANDONED         = "abandoned",         _("Abandoned")
        CANCELLED         = "cancelled",         _("Cancelled")
        REVERSED          = "reversed",          _("Reversed")
        AUTHORIZED        = "authorized",        _("Authorized")
        CAPTURED          = "captured",          _("Captured")
        REFUND_INITIATED  = "refund_initiated",  _("Refund Initiated")
        REFUND_PROCESSED  = "refund_processed",  _("Refund Processed")
        DISPUTE_OPENED    = "dispute_opened",    _("Dispute Opened")
        DISPUTE_WON       = "dispute_won",       _("Dispute Won")
        DISPUTE_LOST      = "dispute_lost",      _("Dispute Lost")
        FRAUD_FLAGGED     = "fraud_flagged",     _("Fraud Flagged")
        FRAUD_CLEARED     = "fraud_cleared",     _("Fraud Cleared")
        WEBHOOK_RECEIVED  = "webhook_received",  _("Webhook Received")
        MANUAL_OVERRIDE   = "manual_override",   _("Manual Override")

    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction  = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="events")
    event_type   = models.CharField(_("Event Type"), max_length=25, choices=EventType.choices, db_index=True)
    from_status  = models.CharField(_("From Status"), max_length=15, blank=True)
    to_status    = models.CharField(_("To Status"), max_length=15, blank=True)
    detail       = models.TextField(_("Detail"), blank=True)
    metadata     = models.JSONField(_("Metadata"), default=dict, blank=True)
    source       = models.CharField(_("Source"), max_length=50, blank=True)
    performed_by = models.ForeignKey("userauth.TenantUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="payment_transaction_events")
    ip_address   = models.GenericIPAddressField(_("IP"), null=True, blank=True)

    class Meta:
        verbose_name = _("Transaction Event")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["transaction", "event_type"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]

    def __str__(self):
        return f"[{self.event_type}] on {self.transaction.internal_reference}"

    @property
    def message(self):
        return self.detail


class TransactionMetadata(TimestampedModel):
    """Flexible key-value store for gateway-specific data on a Transaction."""
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="metadata_entries")
    key         = models.CharField(_("Key"), max_length=100, db_index=True)
    value       = models.TextField(_("Value"), blank=True)
    value_json  = models.JSONField(_("Value JSON"), null=True, blank=True)

    class Meta:
        verbose_name = _("Transaction Metadata")
        unique_together = [("transaction", "key")]


class CardDetail(TimestampedModel):
    """Masked card snapshot from a successful card transaction. No raw card data stored."""
    id              = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction     = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name="card_detail")
    last4           = models.CharField(_("Last 4"), max_length=4, blank=True)
    first6          = models.CharField(_("BIN (First 6)"), max_length=6, blank=True)
    card_type       = models.CharField(_("Card Type"), max_length=20, blank=True)
    card_brand      = models.CharField(_("Brand"), max_length=30, blank=True)
    expiry_month    = models.CharField(_("Exp Month"), max_length=2, blank=True)
    expiry_year     = models.CharField(_("Exp Year"), max_length=4, blank=True)
    cardholder_name = models.CharField(_("Cardholder"), max_length=255, blank=True)
    bank_name       = models.CharField(_("Issuing Bank"), max_length=255, blank=True)
    country_code    = models.CharField(_("Country"), max_length=2, blank=True)
    is_3ds_authenticated    = models.BooleanField(_("3DS Authenticated"), default=False)
    authentication_response = models.CharField(_("Auth Response Code"), max_length=20, blank=True)

    class Meta:
        verbose_name = _("Card Detail")

    def __str__(self):
        return f"{self.card_type} ****{self.last4}"


class SavedPaymentMethod(TimestampedModel):
    """Tokenized payment method saved by a customer for future / recurring use."""

    class MethodType(models.TextChoices):
        CARD         = "card",         _("Card")
        BANK_ACCOUNT = "bank_account", _("Bank Account")
        MOBILE_MONEY = "mobile_money", _("Mobile Money")
        WALLET       = "wallet",       _("Digital Wallet")

    class MethodStatus(models.TextChoices):
        ACTIVE  = "active",  _("Active")
        EXPIRED = "expired", _("Expired")
        REVOKED = "revoked", _("Revoked")
        INVALID = "invalid", _("Invalid")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_profile = models.ForeignKey(TenantPaymentProfile, on_delete=models.CASCADE, related_name="saved_methods")
    customer_id     = models.UUIDField(_("Customer ID"), db_index=True)
    method_type     = models.CharField(_("Type"), max_length=15, choices=MethodType.choices)
    status          = models.CharField(_("Status"), max_length=10, choices=MethodStatus.choices, default=MethodStatus.ACTIVE, db_index=True)
    is_default      = models.BooleanField(_("Default"), default=False)
    display_name    = models.CharField(_("Display Name"), max_length=100, blank=True)
    last4           = models.CharField(_("Last 4"), max_length=4, blank=True)
    expiry_month    = models.CharField(_("Exp Month"), max_length=2, blank=True)
    expiry_year     = models.CharField(_("Exp Year"), max_length=4, blank=True)
    card_brand      = models.CharField(_("Brand"), max_length=30, blank=True)
    bank_name       = models.CharField(_("Bank"), max_length=255, blank=True)
    country_code    = models.CharField(_("Country"), max_length=2, blank=True)
    gateway_provider    = models.CharField(_("Gateway Provider"), max_length=20, blank=True)
    gateway_customer_id = models.CharField(_("Gateway Customer ID"), max_length=500, blank=True, db_index=True)
    last_used_at        = models.DateTimeField(_("Last Used"), null=True, blank=True)
    total_uses          = models.PositiveIntegerField(_("Total Uses"), default=0)
    failed_attempts     = models.PositiveSmallIntegerField(_("Failed Attempts"), default=0)
    expires_at          = models.DateTimeField(_("Expires At"), null=True, blank=True)
    revoked_at          = models.DateTimeField(_("Revoked At"), null=True, blank=True)
    revoke_reason       = models.CharField(_("Revoke Reason"), max_length=255, blank=True)
    billing_address     = models.JSONField(_("Billing Address"), default=dict, blank=True)

    class Meta:
        verbose_name = _("Saved Payment Method")
        ordering = ["-is_default", "-last_used_at"]
        indexes = [
            models.Index(fields=["customer_id", "status"]),
            models.Index(fields=["payment_profile", "customer_id"]),
        ]

    def __str__(self):
        return f"{self.display_name or self.method_type} (customer {self.customer_id})"

    @property
    def customer_email(self):
        return ""

    @property
    def is_active(self):
        return self.status == self.MethodStatus.ACTIVE


class PaymentMethodVaultToken(TimestampedModel):
    """Provider-specific token per SavedPaymentMethod × gateway."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    saved_method        = models.ForeignKey(SavedPaymentMethod, on_delete=models.CASCADE, related_name="vault_tokens")
    gateway             = models.ForeignKey("system_pay.PaymentGatewayDefinition", on_delete=models.CASCADE, related_name="vault_tokens")
    gateway_provider    = models.CharField(_("Provider"), max_length=20)
    token               = models.TextField(_("Vault Token (encrypted)"))
    token_type          = models.CharField(_("Token Type"), max_length=30, blank=True)
    gateway_customer_id = models.CharField(_("Gateway Customer ID"), max_length=500, blank=True)
    is_active           = models.BooleanField(_("Active"), default=True)
    last_used_at        = models.DateTimeField(_("Last Used"), null=True, blank=True)
    failed_count        = models.PositiveSmallIntegerField(_("Failed Count"), default=0)
    invalidated_at      = models.DateTimeField(_("Invalidated At"), null=True, blank=True)
    invalidation_reason = models.CharField(_("Invalidation Reason"), max_length=255, blank=True)

    class Meta:
        verbose_name = _("Vault Token")
        unique_together = [("saved_method", "gateway_provider")]


class Refund(TimestampedModel):
    """Refund issued against a Transaction. Can be full or partial."""

    class RefundStatus(models.TextChoices):
        PENDING    = "pending",    _("Pending")
        PROCESSING = "processing", _("Processing")
        SUCCESS    = "success",    _("Success")
        FAILED     = "failed",     _("Failed")
        CANCELLED  = "cancelled",  _("Cancelled")

    class RefundReason(models.TextChoices):
        CUSTOMER_REQUEST   = "customer_request",   _("Customer Request")
        ITEM_NOT_RECEIVED  = "item_not_received",  _("Item Not Received")
        ITEM_DEFECTIVE     = "item_defective",     _("Item Defective")
        DUPLICATE_CHARGE   = "duplicate_charge",   _("Duplicate Charge")
        FRAUD              = "fraud",              _("Fraud")
        ORDER_CANCELLED    = "order_cancelled",    _("Order Cancelled")
        GOODWILL           = "goodwill",           _("Goodwill")
        OTHER              = "other",              _("Other")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction     = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="refunds")
    payment_profile = models.ForeignKey(TenantPaymentProfile, on_delete=models.CASCADE, related_name="refunds")
    amount              = models.DecimalField(_("Refund Amount"), max_digits=14, decimal_places=2)
    currency            = models.CharField(_("Currency"), max_length=3)
    commission_reversed = models.DecimalField(_("Commission Reversed"), max_digits=10, decimal_places=2, default=Decimal("0.00"))
    tenant_net_refunded = models.DecimalField(_("Tenant Net Refunded"), max_digits=14, decimal_places=2, default=Decimal("0.00"))
    status              = models.CharField(_("Status"), max_length=15, choices=RefundStatus.choices, default=RefundStatus.PENDING, db_index=True)
    reason              = models.CharField(_("Reason"), max_length=20, choices=RefundReason.choices, default=RefundReason.OTHER)
    reason_detail       = models.TextField(_("Detail"), blank=True)
    customer_note       = models.TextField(_("Customer Note"), blank=True)
    internal_note       = models.TextField(_("Internal Note"), blank=True)
    gateway_refund_id   = models.CharField(_("Gateway Refund ID"), max_length=500, blank=True, db_index=True)
    gateway_response    = models.JSONField(_("Gateway Response"), default=dict, blank=True)
    processed_at        = models.DateTimeField(_("Processed At"), null=True, blank=True)
    failure_reason      = models.TextField(_("Failure Reason"), blank=True)
    initiated_by        = models.ForeignKey("userauth.TenantUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="initiated_payment_refunds")
    initiated_by_type   = models.CharField(_("Initiated By"), max_length=20, choices=[("customer","Customer"),("staff","Staff"),("system","System"),("dispute","Dispute")], default="staff")

    class Meta:
        verbose_name = _("Refund")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["transaction", "status"]),
            models.Index(fields=["payment_profile", "status"]),
            models.Index(fields=["gateway_refund_id"]),
        ]

    def __str__(self):
        return f"Refund {self.id} — {self.amount} {self.currency} [{self.status}]"

    @property
    def refund_reference(self):
        return self.gateway_refund_id or f"RFD-{str(self.id).replace('-', '')[:10].upper()}"

    @property
    def gateway_reference(self):
        return self.gateway_refund_id

    @property
    def completed_at(self):
        return self.processed_at


class RefundLineItem(TimestampedModel):
    """Per-order-item breakdown for partial refunds."""
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    refund        = models.ForeignKey(Refund, on_delete=models.CASCADE, related_name="line_items")
    order_item_id = models.UUIDField(_("Order Item ID"))
    product_title = models.CharField(_("Product"), max_length=500, blank=True)
    sku           = models.CharField(_("SKU"), max_length=100, blank=True)
    quantity      = models.PositiveSmallIntegerField(_("Qty"), default=1)
    unit_price    = models.DecimalField(_("Unit Price"), max_digits=14, decimal_places=2)
    amount        = models.DecimalField(_("Amount"), max_digits=14, decimal_places=2)
    restock       = models.BooleanField(_("Restock"), default=True)

    class Meta:
        verbose_name = _("Refund Line Item")


class Dispute(TimestampedModel):
    """Chargeback / dispute opened against a Transaction by card network."""

    class DisputeStatus(models.TextChoices):
        OPEN         = "open",         _("Open")
        UNDER_REVIEW = "under_review", _("Under Review")
        WON          = "won",          _("Won")
        LOST         = "lost",         _("Lost")
        EXPIRED      = "expired",      _("Expired")
        ACCEPTED     = "accepted",     _("Accepted")

    class DisputeReason(models.TextChoices):
        FRAUD                  = "fraud",                  _("Fraud")
        NOT_RECOGNIZED         = "not_recognized",         _("Not Recognized")
        PRODUCT_NOT_RECEIVED   = "product_not_received",   _("Product Not Received")
        PRODUCT_UNACCEPTABLE   = "product_unacceptable",   _("Product Unacceptable")
        CREDIT_NOT_PROCESSED   = "credit_not_processed",   _("Credit Not Processed")
        DUPLICATE              = "duplicate",              _("Duplicate")
        SUBSCRIPTION_CANCELLED = "subscription_cancelled", _("Subscription Cancelled")
        OTHER                  = "other",                  _("Other")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction     = models.ForeignKey(Transaction, on_delete=models.CASCADE, related_name="disputes")
    payment_profile = models.ForeignKey(TenantPaymentProfile, on_delete=models.CASCADE, related_name="disputes")
    status          = models.CharField(_("Status"), max_length=20, choices=DisputeStatus.choices, default=DisputeStatus.OPEN, db_index=True)
    reason          = models.CharField(_("Reason"), max_length=30, choices=DisputeReason.choices, default=DisputeReason.OTHER)
    dispute_amount  = models.DecimalField(_("Dispute Amount"), max_digits=14, decimal_places=2)
    currency        = models.CharField(_("Currency"), max_length=3)
    gateway_dispute_id    = models.CharField(_("Gateway Dispute ID"), max_length=500, blank=True, db_index=True)
    raw_gateway_payload   = models.JSONField(_("Raw Payload"), default=dict, blank=True)
    opened_at             = models.DateTimeField(_("Opened At"), null=True, blank=True)
    evidence_deadline     = models.DateTimeField(_("Evidence Deadline"), null=True, blank=True)
    resolved_at           = models.DateTimeField(_("Resolved At"), null=True, blank=True)
    outcome_reason        = models.TextField(_("Outcome Reason"), blank=True)
    platform_notes        = models.TextField(_("Platform Notes"), blank=True)
    balance_debited       = models.DecimalField(_("Balance Debited"), max_digits=14, decimal_places=2, default=Decimal("0.00"))
    balance_restored      = models.DecimalField(_("Balance Restored"), max_digits=14, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        verbose_name = _("Dispute")
        ordering = ["-opened_at"]
        indexes = [
            models.Index(fields=["status", "evidence_deadline"]),
            models.Index(fields=["payment_profile", "status"]),
            models.Index(fields=["gateway_dispute_id"]),
        ]

    def __str__(self):
        return f"Dispute {self.id} — {self.dispute_amount} {self.currency} [{self.status}]"

    @property
    def dispute_reference(self):
        return self.gateway_dispute_id or f"DSP-{str(self.id).replace('-', '')[:10].upper()}"

    @property
    def evidence(self):
        return self.evidence_items

    @property
    def reason_detail(self):
        return self.raw_gateway_payload.get("reason_detail", "") or self.outcome_reason


class DisputeEvidence(TimestampedModel):
    """Evidence submitted to counter a chargeback."""
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dispute       = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name="evidence_items")
    evidence_type = models.CharField(
        _("Type"), max_length=30,
        choices=[
            ("shipping_documentation","Shipping Documentation"),("receipt","Receipt"),
            ("customer_communication","Customer Communication"),("refund_policy","Refund Policy"),
            ("service_documentation","Service Documentation"),("other","Other"),
        ],
    )
    description   = models.TextField(_("Description"), blank=True)
    file_url      = models.URLField(_("File URL"), blank=True)
    file_type     = models.CharField(_("File Type"), max_length=20, blank=True)
    text_content  = models.TextField(_("Text Content"), blank=True)
    submitted_at  = models.DateTimeField(_("Submitted At"), null=True, blank=True)
    submitted_by  = models.ForeignKey("userauth.TenantUser", null=True, blank=True, on_delete=models.SET_NULL, related_name="submitted_payment_dispute_evidence")

    class Meta:
        verbose_name = _("Dispute Evidence")

    def __str__(self) -> str:
        return f"{self.evidence_type} for Dispute {self.dispute_id}"


# ─────────────────────────────────────────────────────────────
# WEBHOOK IDEMPOTENCY
# ─────────────────────────────────────────────────────────────

class ProcessedWebhookEvent(AppendOnlyModel):
    """
    Immutable record of every gateway webhook event that has been processed.

    Used as a deduplication (idempotency) guard: before processing any incoming
    webhook, the handler checks for an existing record matching
    (gateway_provider, gateway_event_id).  If one exists the request is ACKed
    and discarded without duplicate processing.

    Inherits AppendOnlyModel — rows are NEVER updated or deleted, which makes
    this an authoritative audit log of all processed gateway events.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Identity ─────────────────────────────────────────────────────────────
    gateway_provider  = models.CharField(_("Gateway Provider"), max_length=50, db_index=True)
    gateway_event_id  = models.CharField(
        _("Gateway Event ID"),
        max_length=500,
        db_index=True,
        help_text=_("The unique event identifier supplied by the gateway, e.g. Paystack event ID."),
    )
    event_type = models.CharField(_("Event Type"), max_length=100, blank=True)

    # ── Linked Objects ────────────────────────────────────────────────────────
    transaction   = models.ForeignKey(
        Transaction, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="webhook_events",
    )
    order_number  = models.CharField(_("Order / Purchase Reference"), max_length=100, blank=True, db_index=True)

    # ── Outcome ───────────────────────────────────────────────────────────────
    action_taken  = models.CharField(_("Action Taken"), max_length=100, blank=True)
    raw_payload   = models.JSONField(_("Raw Payload"), default=dict, blank=True)
    processing_ms = models.PositiveIntegerField(_("Processing Time (ms)"), null=True, blank=True)

    class Meta:
        verbose_name = _("Processed Webhook Event")
        verbose_name_plural = _("Processed Webhook Events")
        ordering = ["-created_at"]
        # Core idempotency constraint: one processing record per gateway event.
        unique_together = [("gateway_provider", "gateway_event_id")]
        indexes = [
            models.Index(fields=["gateway_provider", "gateway_event_id"]),
            models.Index(fields=["gateway_provider", "-created_at"]),
            models.Index(fields=["order_number"]),
        ]

    def __str__(self) -> str:
        return f"{self.gateway_provider}:{self.gateway_event_id} [{self.event_type}]"

    @classmethod
    def is_duplicate(cls, *, gateway_provider: str, gateway_event_id: str) -> bool:
        """
        Return True if this event has already been processed.

        Usage (inside webhook handler, before doing any work)::

            if ProcessedWebhookEvent.is_duplicate(
                gateway_provider=provider,
                gateway_event_id=event_id,
            ):
                return {"success": True, "action": "duplicate_skipped"}
        """
        return cls.objects.filter(
            gateway_provider=gateway_provider,
            gateway_event_id=gateway_event_id,
        ).exists()

    @classmethod
    def record(
        cls,
        *,
        gateway_provider: str,
        gateway_event_id: str,
        event_type: str = "",
        transaction=None,
        order_number: str = "",
        action_taken: str = "",
        raw_payload: dict | None = None,
        processing_ms: int | None = None,
    ) -> "ProcessedWebhookEvent":
        """
        Create an immutable record for a processed webhook event.

        Uses get_or_create to be safe against race conditions — if two
        concurrent workers try to record the same event, only one record
        is created.  The second worker should check is_duplicate() first.
        """
        obj, _ = cls.objects.get_or_create(
            gateway_provider=gateway_provider,
            gateway_event_id=gateway_event_id,
            defaults={
                "event_type":    event_type,
                "transaction":   transaction,
                "order_number":  order_number,
                "action_taken":  action_taken,
                "raw_payload":   raw_payload or {},
                "processing_ms": processing_ms,
            },
        )
        return obj
