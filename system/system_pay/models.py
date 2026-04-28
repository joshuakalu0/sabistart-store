from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator
import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True


class AppendOnlyModel(models.Model):
    """Immutable ledger base. Raises ValueError on any update."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        abstract = True
    
    def save(self, *args, **kwargs):
        if self.pk:
            raise ValueError(f"{self.__class__.__name__} is append-only. Create a new record instead of updating.")
        super().save(*args, **kwargs)


class GatewayProvider(models.TextChoices):
    PAYSTACK    = "paystack",    _("Paystack")
    FLUTTERWAVE = "flutterwave", _("Flutterwave")
    STRIPE      = "stripe",      _("Stripe")
    PAYPAL      = "paypal",      _("PayPal")
    SQUARE      = "square",      _("Square")
    BRAINTREE   = "braintree",   _("Braintree")
    RAZORPAY    = "razorpay",    _("Razorpay")
    MONNIFY     = "monnify",     _("Monnify")
    INTERSWITCH = "interswitch", _("Interswitch")
    OPAY        = "opay",        _("OPay")
    MONIEPOINT  = "moniepoint",  _("Moniepoint")
    MANUAL      = "manual",      _("Manual / Bank Transfer")
    COD         = "cod",         _("Cash on Delivery")
    CRYPTO      = "crypto",      _("Cryptocurrency")


class PaymentMode(models.TextChoices):
    PLATFORM = "platform", _("Platform Mode — Use Platform Gateway Account")
    DIRECT   = "direct",   _("Direct Mode — Use Tenant Own Gateway Credentials")


class TransactionStatus(models.TextChoices):
    INITIATED  = "initiated",  _("Initiated")
    PENDING    = "pending",    _("Pending")
    PROCESSING = "processing", _("Processing")
    SUCCESS    = "success",    _("Success")
    FAILED     = "failed",     _("Failed")
    ABANDONED  = "abandoned",  _("Abandoned")
    CANCELLED  = "cancelled",  _("Cancelled")
    REVERSED   = "reversed",   _("Reversed")
    FLAGGED    = "flagged",    _("Flagged — Fraud Review")
    EXPIRED    = "expired",    _("Expired")


class PaymentGatewayDefinition(TimestampedModel):
    """Platform-level registry of every supported payment gateway. Public schema."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider          = models.CharField(_("Provider"), max_length=20, choices=GatewayProvider.choices, unique=True, db_index=True)
    name              = models.CharField(_("Display Name"), max_length=100)
    description       = models.TextField(_("Description"), blank=True)
    logo_url          = models.URLField(_("Logo URL"), blank=True)
    website_url       = models.URLField(_("Website"), blank=True)
    documentation_url = models.URLField(_("API Docs"), blank=True)
    dashboard_url     = models.URLField(_("Provider Dashboard URL"), blank=True)
    is_enabled        = models.BooleanField(_("Enabled on Platform"), default=False, db_index=True)
    is_available_for_direct_mode      = models.BooleanField(_("Available for Direct Mode"), default=True)
    requires_business_verification    = models.BooleanField(_("Requires KYB for Direct Mode"), default=False)
    supported_countries  = models.JSONField(_("Supported Countries"),  default=list)
    supported_currencies = models.JSONField(_("Supported Currencies"), default=list)
    supports_recurring        = models.BooleanField(_("Recurring"),           default=False)
    supports_refunds          = models.BooleanField(_("Refunds"),             default=True)
    supports_partial_refunds  = models.BooleanField(_("Partial Refunds"),     default=False)
    supports_tokenization     = models.BooleanField(_("Tokenization"),        default=False)
    supports_3ds              = models.BooleanField(_("3D Secure"),           default=False)
    supports_split_payment    = models.BooleanField(
        _("Native Split Payment"), default=False,
        help_text=_("Paystack/Flutterwave subaccount-based revenue splitting."),
    )
    supports_virtual_accounts = models.BooleanField(_("Virtual Accounts"),   default=False)
    supports_authorization    = models.BooleanField(_("Authorize & Capture"), default=False)
    min_transaction_amount = models.DecimalField(_("Min Transaction"), max_digits=14, decimal_places=2, null=True, blank=True)
    max_transaction_amount = models.DecimalField(_("Max Transaction"), max_digits=14, decimal_places=2, null=True, blank=True)
    settlement_days   = models.PositiveSmallIntegerField(_("Settlement Days T+N"), default=1)
    settlement_note   = models.CharField(_("Settlement Note"), max_length=255, blank=True)
    credential_schema = models.JSONField(_("Credential Schema"), default=dict)
    webhook_events    = models.JSONField(_("Webhook Events"), default=list)
    display_order     = models.PositiveSmallIntegerField(_("Display Order"), default=0)
    badge_label       = models.CharField(_("Badge Label"), max_length=50, blank=True)

    class Meta:
        verbose_name = _("Payment Gateway Definition")
        ordering = ["display_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.provider})"


class PlatformGatewayCredential(TimestampedModel):
    """
    The PLATFORM's own API keys for each gateway. Public schema.
    All tenants in PLATFORM MODE share these credentials.
    ALL keys ENCRYPTED in production.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway     = models.ForeignKey(PaymentGatewayDefinition, on_delete=models.CASCADE, related_name="platform_credentials")
    name        = models.CharField(_("Name"), max_length=100)
    environment = models.CharField(_("Environment"), max_length=5, choices=[("test","Test"),("live","Live")], default="test", db_index=True)
    is_active   = models.BooleanField(_("Active"), default=False, db_index=True)
    priority    = models.PositiveIntegerField(_("Priority"), default=0)
    public_key        = models.TextField(_("Public Key (encrypted)"),        blank=True)
    secret_key        = models.TextField(_("Secret Key (encrypted)"))
    encryption_key    = models.TextField(_("Encryption Key (encrypted)"),    blank=True)
    webhook_secret    = models.TextField(_("Webhook Secret (encrypted)"),    blank=True)
    extra_credentials = models.JSONField(_("Extra Credentials (encrypted)"), default=dict, blank=True)
    account_id       = models.CharField(_("Platform Account ID"), max_length=255, blank=True)
    subaccount_code  = models.CharField(
        _("Platform Master Subaccount Code"), max_length=255, blank=True,
        help_text=_("For revenue splitting: platform receives commission here."),
    )
    daily_transaction_limit = models.PositiveIntegerField(_("Daily Limit"), null=True, blank=True)
    monthly_volume_limit    = models.DecimalField(_("Monthly Volume Limit"), max_digits=18, decimal_places=2, null=True, blank=True)
    supported_countries = models.JSONField(_("Countries"), default=list, blank=True)
    default_currency    = models.CharField(_("Default Currency"), max_length=3, default="NGN")
    last_used_at         = models.DateTimeField(_("Last Used"), null=True, blank=True)
    last_health_check_at = models.DateTimeField(_("Last Health Check"), null=True, blank=True)
    is_healthy           = models.BooleanField(_("Healthy"), default=True)
    health_note          = models.CharField(_("Health Note"), max_length=500, blank=True)

    class Meta:
        verbose_name = _("Platform Gateway Credential")
        ordering = ["-priority", "gateway__name"]
        indexes = [models.Index(fields=["gateway", "environment", "is_active"])]

    def __str__(self):
        return f"[Platform] {self.gateway.name} — {self.name} ({self.environment})"


class GatewayWebhookConfig(TimestampedModel):
    """Platform webhook endpoint config per gateway. One URL per gateway for all events."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway             = models.OneToOneField(PaymentGatewayDefinition, on_delete=models.CASCADE, related_name="webhook_config")
    webhook_url         = models.URLField(_("Platform Webhook URL"))
    signature_header    = models.CharField(_("Signature Header"), max_length=100, blank=True)
    signature_algorithm = models.CharField(_("Algorithm"), max_length=20, choices=[("hmac_sha256","HMAC-SHA256"),("hmac_sha512","HMAC-SHA512")], default="hmac_sha256")
    ip_whitelist        = models.JSONField(_("Allowed IPs"), default=list, blank=True)
    is_active           = models.BooleanField(_("Active"), default=True)
    last_received_at    = models.DateTimeField(_("Last Event At"), null=True, blank=True)
    total_events_received = models.PositiveIntegerField(_("Total Events"), default=0)

    class Meta:
        verbose_name = _("Gateway Webhook Config")

    def __str__(self):
        return f"Webhook: {self.gateway.name}"


class PlatformPaymentSetting(TimestampedModel):
    """Singleton-style global payment configuration for the platform console."""

    name = models.CharField(max_length=50, unique=True, default="default")
    default_currency = models.CharField(max_length=3, default="NGN")
    supported_currencies = models.JSONField(default=list, blank=True)
    allow_multi_currency = models.BooleanField(default=True)
    automatic_payout_review = models.BooleanField(default=True)
    default_payout_schedule = models.CharField(
        max_length=15,
        choices=[("manual", "Manual"), ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")],
        default="manual",
    )
    default_payout_hold_days = models.PositiveSmallIntegerField(default=1)
    default_minimum_payout_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("1000.00"))
    default_gateway_timeout_minutes = models.PositiveSmallIntegerField(default=30)
    enable_direct_mode_reviews = models.BooleanField(default=True)
    enable_platform_refund_tools = models.BooleanField(default=True)
    enable_platform_dispute_tools = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = _("Platform Payment Setting")
        verbose_name_plural = _("Platform Payment Settings")

    def __str__(self):
        return self.name


class PlatformCommissionRule(TimestampedModel):
    """Public, staff-managed commission policy for platform-owned gateway processing."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    gateway = models.ForeignKey(
        PaymentGatewayDefinition,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="platform_commission_rules",
    )
    subscription_plan = models.CharField(max_length=100, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    percentage_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal("2.5000"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    flat_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    cap_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    minimum_fee = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    priority = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-priority", "name"]
        indexes = [
            models.Index(fields=["is_active", "priority"]),
            models.Index(fields=["gateway", "is_active"]),
        ]

    def __str__(self):
        return self.name

    def preview_fee(self, amount: Decimal) -> Decimal:
        base = (amount * self.percentage_rate / Decimal("100")) + self.flat_fee
        fee = max(self.minimum_fee, base.quantize(Decimal("0.01")))
        if self.cap_amount:
            fee = min(fee, self.cap_amount)
        return fee.quantize(Decimal("0.01"))


class TenantPaymentSnapshot(TimestampedModel):
    """Public summary of a tenant's payment profile for fast platform visibility."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="payment_snapshots")
    schema_name = models.CharField(max_length=63, unique=True, db_index=True)
    business_name = models.CharField(max_length=500, blank=True)
    account_status = models.CharField(max_length=20, blank=True, db_index=True)
    kyb_status = models.CharField(max_length=20, blank=True, db_index=True)
    payout_enabled = models.BooleanField(default=False)
    default_currency = models.CharField(max_length=3, default="NGN")
    available_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    pending_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    reserved_balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_transaction_count = models.PositiveIntegerField(default=0)
    total_transaction_volume = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    gateway_count = models.PositiveIntegerField(default=0)
    active_gateway_count = models.PositiveIntegerField(default=0)
    direct_gateway_count = models.PositiveIntegerField(default=0)
    platform_gateway_count = models.PositiveIntegerField(default=0)
    last_transaction_at = models.DateTimeField(null=True, blank=True)
    health_status = models.CharField(max_length=20, default="unknown")
    notes = models.TextField(blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["business_name", "schema_name"]

    def __str__(self):
        return self.business_name or self.schema_name

    @property
    def currency(self):
        return self.default_currency


class TenantGatewaySnapshot(TimestampedModel):
    """Public gateway summary for a tenant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="gateway_snapshots")
    schema_name = models.CharField(max_length=63, db_index=True)
    gateway = models.ForeignKey(
        PaymentGatewayDefinition,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tenant_gateway_snapshots",
    )
    gateway_provider = models.CharField(max_length=20, db_index=True)
    gateway_name = models.CharField(max_length=100)
    mode = models.CharField(max_length=20, blank=True, db_index=True)
    status = models.CharField(max_length=20, blank=True, db_index=True)
    currency = models.CharField(max_length=3, default="NGN")
    is_default = models.BooleanField(default=False)
    is_healthy = models.BooleanField(default=True)
    transaction_count = models.PositiveIntegerField(default=0)
    transaction_volume = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    last_transaction_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["gateway_name"]
        unique_together = [("schema_name", "gateway_provider")]

    def __str__(self):
        return f"{self.schema_name} - {self.gateway_name}"


class PlatformTransactionIndex(TimestampedModel):
    """Public projection of tenant transactions for fast platform search/filtering."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="transaction_indices")
    schema_name = models.CharField(max_length=63, db_index=True)
    transaction_id = models.UUIDField(unique=True, db_index=True)
    internal_reference = models.CharField(max_length=100, blank=True, db_index=True)
    order_id = models.UUIDField(null=True, blank=True, db_index=True)
    order_number = models.CharField(max_length=100, blank=True, db_index=True)
    gateway_transaction_id = models.CharField(max_length=500, blank=True, db_index=True)
    gateway_reference = models.CharField(max_length=500, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="NGN")
    status = models.CharField(max_length=20, blank=True, db_index=True)
    payment_mode = models.CharField(max_length=20, blank=True, db_index=True)
    gateway_provider = models.CharField(max_length=20, blank=True, db_index=True)
    customer_email = models.EmailField(blank=True, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True)
    payment_method_type = models.CharField(max_length=30, blank=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at_source = models.DateTimeField(null=True, blank=True, db_index=True)
    is_flagged = models.BooleanField(default=False, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-paid_at", "-created_at_source", "-created_at"]
        indexes = [
            models.Index(fields=["schema_name", "status"]),
            models.Index(fields=["schema_name", "gateway_provider"]),
        ]

    def __str__(self):
        return self.internal_reference or str(self.transaction_id)


class PlatformPayoutIndex(TimestampedModel):
    """Public projection of tenant payout requests."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="payout_indices")
    schema_name = models.CharField(max_length=63, db_index=True)
    payout_request_id = models.UUIDField(unique=True, db_index=True)
    payout_reference = models.CharField(max_length=100, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="NGN")
    status = models.CharField(max_length=20, blank=True, db_index=True)
    bank_name = models.CharField(max_length=255, blank=True)
    bank_account_masked = models.CharField(max_length=30, blank=True)
    gateway_provider = models.CharField(max_length=20, blank=True, db_index=True)
    gateway_transfer_reference = models.CharField(max_length=500, blank=True, db_index=True)
    requested_at = models.DateTimeField(null=True, blank=True, db_index=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-requested_at", "-created_at"]
        indexes = [models.Index(fields=["schema_name", "status"])]

    def __str__(self):
        return self.payout_reference or str(self.payout_request_id)


class PlatformRefundIndex(TimestampedModel):
    """Public projection of tenant refunds."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="refund_indices")
    schema_name = models.CharField(max_length=63, db_index=True)
    refund_id = models.UUIDField(unique=True, db_index=True)
    refund_reference = models.CharField(max_length=100, blank=True, db_index=True)
    transaction_reference = models.CharField(max_length=100, blank=True, db_index=True)
    order_number = models.CharField(max_length=100, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="NGN")
    status = models.CharField(max_length=20, blank=True, db_index=True)
    reason = models.CharField(max_length=50, blank=True)
    requested_at = models.DateTimeField(null=True, blank=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-requested_at", "-created_at"]
        indexes = [models.Index(fields=["schema_name", "status"])]

    def __str__(self):
        return self.refund_reference or str(self.refund_id)


class PlatformDisputeIndex(TimestampedModel):
    """Public projection of tenant disputes."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="dispute_indices")
    schema_name = models.CharField(max_length=63, db_index=True)
    dispute_id = models.UUIDField(unique=True, db_index=True)
    dispute_reference = models.CharField(max_length=100, blank=True, db_index=True)
    transaction_reference = models.CharField(max_length=100, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="NGN")
    status = models.CharField(max_length=20, blank=True, db_index=True)
    reason = models.CharField(max_length=50, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True, db_index=True)
    evidence_deadline = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-opened_at", "-created_at"]
        indexes = [models.Index(fields=["schema_name", "status"])]

    def __str__(self):
        return self.dispute_reference or str(self.dispute_id)
