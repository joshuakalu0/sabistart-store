"""
Core tenant payment models copied into the live dashboard app.
"""

import uuid
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from system.system_pay.models import PaymentGatewayDefinition, PlatformGatewayCredential


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
            raise ValueError(
                f"{self.__class__.__name__} is append-only. Create a new record instead of updating."
            )
        super().save(*args, **kwargs)


class GatewayProvider(models.TextChoices):
    PAYSTACK = "paystack", _("Paystack")
    FLUTTERWAVE = "flutterwave", _("Flutterwave")
    STRIPE = "stripe", _("Stripe")
    PAYPAL = "paypal", _("PayPal")
    SQUARE = "square", _("Square")
    BRAINTREE = "braintree", _("Braintree")
    RAZORPAY = "razorpay", _("Razorpay")
    MONNIFY = "monnify", _("Monnify")
    INTERSWITCH = "interswitch", _("Interswitch")
    OPAY = "opay", _("OPay")
    MONIEPOINT = "moniepoint", _("Moniepoint")
    MANUAL = "manual", _("Manual / Bank Transfer")
    COD = "cod", _("Cash on Delivery")
    CRYPTO = "crypto", _("Cryptocurrency")


class PaymentMode(models.TextChoices):
    PLATFORM = "platform", _("Platform Mode - Use Platform Gateway Account")
    DIRECT = "direct", _("Direct Mode - Use Tenant Own Gateway Credentials")


class TransactionStatus(models.TextChoices):
    INITIATED = "initiated", _("Initiated")
    PENDING = "pending", _("Pending")
    PROCESSING = "processing", _("Processing")
    SUCCESS = "success", _("Success")
    FAILED = "failed", _("Failed")
    ABANDONED = "abandoned", _("Abandoned")
    CANCELLED = "cancelled", _("Cancelled")
    REVERSED = "reversed", _("Reversed")
    FLAGGED = "flagged", _("Flagged - Fraud Review")
    EXPIRED = "expired", _("Expired")


class TenantPaymentProfile(TimestampedModel):
    """Master payment configuration for a tenant."""

    class AccountStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        PENDING = "pending", _("Pending Verification")
        RESTRICTED = "restricted", _("Restricted")
        SUSPENDED = "suspended", _("Suspended")
        CLOSED = "closed", _("Closed")

    class KYBStatus(models.TextChoices):
        NOT_STARTED = "not_started", _("Not Started")
        SUBMITTED = "submitted", _("Submitted")
        UNDER_REVIEW = "under_review", _("Under Review")
        VERIFIED = "verified", _("Verified")
        REJECTED = "rejected", _("Rejected")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account_status = models.CharField(
        _("Account Status"),
        max_length=15,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING,
        db_index=True,
    )
    kyb_status = models.CharField(
        _("KYB Status"),
        max_length=15,
        choices=KYBStatus.choices,
        default=KYBStatus.NOT_STARTED,
    )
    kyb_verified_at = models.DateTimeField(_("KYB Verified At"), null=True, blank=True)
    kyb_documents = models.JSONField(_("KYB Documents"), default=list, blank=True)
    business_name = models.CharField(_("Business Name"), max_length=500, blank=True)
    business_type = models.CharField(
        _("Business Type"),
        max_length=30,
        choices=[
            ("individual", "Individual"),
            ("limited_liability", "LLC"),
            ("partnership", "Partnership"),
            ("corporation", "Corporation"),
            ("ngo", "NGO"),
        ],
        blank=True,
    )
    business_registration_number = models.CharField(_("Registration Number"), max_length=100, blank=True)
    tax_identification_number = models.CharField(_("TIN"), max_length=100, blank=True)
    business_address = models.TextField(_("Business Address"), blank=True)
    business_country = models.CharField(_("Country"), max_length=2, blank=True)
    business_phone = models.CharField(_("Phone"), max_length=30, blank=True)
    support_email = models.EmailField(_("Support Email"), blank=True)
    business_website = models.URLField(_("Website"), blank=True)
    default_currency = models.CharField(_("Default Currency"), max_length=3, default="NGN")
    transaction_description_template = models.CharField(
        _("Txn Description"),
        max_length=255,
        default="{{ store_name }} - Order #{{ order_number }}",
    )
    send_customer_receipt = models.BooleanField(_("Send Customer Receipt"), default=True)
    auto_capture = models.BooleanField(_("Auto-Capture Auth"), default=True)
    payment_timeout_minutes = models.PositiveSmallIntegerField(_("Payment Timeout (min)"), default=30)
    payout_enabled = models.BooleanField(
        _("Payout Enabled"),
        default=False,
        help_text=_("Enabled after KYB + verified bank account."),
    )
    minimum_payout_amount = models.DecimalField(
        _("Min Payout"),
        max_digits=14,
        decimal_places=2,
        default=Decimal("1000.00"),
    )
    payout_currency = models.CharField(_("Payout Currency"), max_length=3, default="NGN")
    payout_schedule = models.CharField(
        _("Payout Schedule"),
        max_length=15,
        choices=[("manual", "Manual"), ("daily", "Daily"), ("weekly", "Weekly"), ("monthly", "Monthly")],
        default="manual",
    )
    has_custom_commission = models.BooleanField(_("Custom Commission"), default=False)
    custom_commission_rate = models.DecimalField(
        _("Custom Rate (%)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    custom_commission_flat_fee = models.DecimalField(
        _("Custom Flat Fee"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    custom_commission_cap = models.DecimalField(
        _("Commission Cap"),
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    notify_on_payment = models.BooleanField(_("Notify on Payment"), default=True)
    notify_on_failed_payment = models.BooleanField(_("Notify on Failure"), default=True)
    notify_on_dispute = models.BooleanField(_("Notify on Dispute"), default=True)
    notify_on_payout = models.BooleanField(_("Notify on Payout"), default=True)
    payment_notification_email = models.EmailField(_("Notification Email"), blank=True)
    notes = models.TextField(_("Internal Notes"), blank=True)
    onboarded_at = models.DateTimeField(_("Onboarded At"), null=True, blank=True)
    restriction_reason = models.TextField(_("Restriction Reason"), blank=True)

    class Meta:
        verbose_name = _("Tenant Payment Profile")

    def __str__(self):
        return f"PaymentProfile [{self.account_status}] - {self.business_name or 'Unnamed'}"

    @property
    def is_operational(self) -> bool:
        return self.account_status == self.AccountStatus.ACTIVE


class TenantGatewayMode(TimestampedModel):
    """Tenant gateway configuration for platform/direct processing."""

    class ActivationStatus(models.TextChoices):
        INACTIVE = "inactive", _("Inactive")
        PENDING_REVIEW = "pending_review", _("Pending Review")
        ACTIVE = "active", _("Active")
        SUSPENDED = "suspended", _("Suspended")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_profile = models.ForeignKey(TenantPaymentProfile, on_delete=models.CASCADE, related_name="gateway_modes")
    gateway = models.ForeignKey(PaymentGatewayDefinition, on_delete=models.PROTECT, related_name="tenant_modes")
    mode = models.CharField(_("Payment Mode"), max_length=10, choices=PaymentMode.choices, default=PaymentMode.PLATFORM, db_index=True)
    status = models.CharField(_("Status"), max_length=20, choices=ActivationStatus.choices, default=ActivationStatus.INACTIVE, db_index=True)
    is_default = models.BooleanField(_("Default Gateway"), default=False)
    platform_credential = models.ForeignKey(
        PlatformGatewayCredential,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tenant_gateway_modes",
    )
    platform_subaccount_code = models.CharField(_("Tenant Subaccount Code on Platform Account"), max_length=255, blank=True)
    platform_subaccount_id = models.CharField(_("Subaccount ID"), max_length=255, blank=True)
    split_percentage = models.DecimalField(_("Tenant Split %"), max_digits=5, decimal_places=2, null=True, blank=True)
    direct_credential = models.ForeignKey(
        "payments_tenant.TenantGatewayCredential",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_gateway_modes",
    )
    mode_switched_at = models.DateTimeField(_("Mode Switched At"), null=True, blank=True)
    mode_switched_by = models.ForeignKey(
        "userauth.TenantUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="payment_gateway_mode_switches",
    )
    mode_switch_reason = models.TextField(_("Switch Reason"), blank=True)
    previous_mode = models.CharField(_("Previous Mode"), max_length=10, blank=True)
    review_requested_at = models.DateTimeField(_("Review Requested"), null=True, blank=True)
    review_approved_at = models.DateTimeField(_("Review Approved"), null=True, blank=True)
    review_approved_by = models.ForeignKey(
        "userauth.TenantUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_payment_gateway_modes",
    )
    review_notes = models.TextField(_("Review Notes"), blank=True)
    accepted_currencies = models.JSONField(_("Accepted Currencies"), default=list, blank=True)
    enabled_payment_methods = models.JSONField(_("Enabled Methods"), default=list, blank=True)
    checkout_label = models.CharField(_("Checkout Label"), max_length=100, blank=True)
    checkout_display_order = models.PositiveSmallIntegerField(_("Checkout Order"), default=0)
    total_transactions = models.PositiveIntegerField(_("Total Transactions"), default=0)
    total_volume = models.DecimalField(_("Total Volume"), max_digits=18, decimal_places=2, default=Decimal("0.00"))
    last_transaction_at = models.DateTimeField(_("Last Transaction"), null=True, blank=True)

    class Meta:
        verbose_name = _("Tenant Gateway Mode")
        unique_together = [("payment_profile", "gateway")]
        ordering = ["-is_default", "gateway__display_order"]
        indexes = [
            models.Index(fields=["mode", "status"]),
            models.Index(fields=["payment_profile", "status"]),
        ]

    def __str__(self):
        mode = "DIRECT" if self.mode == PaymentMode.DIRECT else "PLATFORM"
        return f"{self.gateway.name} - {mode} [{self.status}]"

    @property
    def is_platform_mode(self) -> bool:
        return self.mode == PaymentMode.PLATFORM

    @property
    def is_direct_mode(self) -> bool:
        return self.mode == PaymentMode.DIRECT

    @property
    def is_active(self) -> bool:
        return self.status == self.ActivationStatus.ACTIVE

    def get_effective_secret_key(self) -> str:
        if self.is_direct_mode and self.direct_credential:
            return self.direct_credential.secret_key
        cred = self.platform_credential or PlatformGatewayCredential.objects.filter(
            gateway=self.gateway,
            is_active=True,
        ).order_by("-priority").first()
        return cred.secret_key if cred else ""

    def get_effective_public_key(self) -> str:
        if self.is_direct_mode and self.direct_credential:
            return self.direct_credential.public_key
        cred = self.platform_credential or PlatformGatewayCredential.objects.filter(
            gateway=self.gateway,
            is_active=True,
        ).order_by("-priority").first()
        return cred.public_key if cred else ""

    @transaction.atomic
    def switch_to_direct(self, credential, actor=None, reason: str = "") -> None:
        self.previous_mode = self.mode
        self.mode = PaymentMode.DIRECT
        self.direct_credential = credential
        self.mode_switched_at = timezone.now()
        self.mode_switched_by = actor
        self.mode_switch_reason = reason
        self.save(
            update_fields=[
                "mode",
                "direct_credential",
                "previous_mode",
                "mode_switched_at",
                "mode_switched_by",
                "mode_switch_reason",
                "updated_at",
            ]
        )

    @transaction.atomic
    def switch_to_platform(self, actor=None, reason: str = "") -> None:
        self.previous_mode = self.mode
        self.mode = PaymentMode.PLATFORM
        self.mode_switched_at = timezone.now()
        self.mode_switched_by = actor
        self.mode_switch_reason = reason
        self.save(
            update_fields=[
                "mode",
                "previous_mode",
                "mode_switched_at",
                "mode_switched_by",
                "mode_switch_reason",
                "updated_at",
            ]
        )


class TenantGatewayCredential(TimestampedModel):
    """Tenant credentials used for direct mode."""

    class CredentialStatus(models.TextChoices):
        PENDING = "pending", _("Pending Validation")
        TESTING = "testing", _("Being Validated")
        ACTIVE = "active", _("Active - In Use")
        REVOKED = "revoked", _("Revoked")
        EXPIRED = "expired", _("Expired")
        INVALID = "invalid", _("Invalid - Validation Failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_profile = models.ForeignKey(TenantPaymentProfile, on_delete=models.CASCADE, related_name="own_credentials")
    gateway = models.ForeignKey(PaymentGatewayDefinition, on_delete=models.PROTECT, related_name="tenant_credentials")
    label = models.CharField(_("Label"), max_length=100, blank=True)
    status = models.CharField(_("Status"), max_length=10, choices=CredentialStatus.choices, default=CredentialStatus.PENDING, db_index=True)
    environment = models.CharField(_("Environment"), max_length=5, choices=[("test", "Test"), ("live", "Live")], default="test", db_index=True)
    public_key = models.TextField(_("Public Key (encrypted)"), blank=True)
    secret_key = models.TextField(_("Secret Key (encrypted)"))
    encryption_key = models.TextField(_("Encryption Key (encrypted)"), blank=True)
    webhook_secret = models.TextField(_("Webhook Secret (encrypted)"), blank=True)
    extra_credentials = models.JSONField(_("Extra Credentials (encrypted)"), default=dict, blank=True)
    gateway_account_id = models.CharField(_("Gateway Account ID"), max_length=255, blank=True)
    gateway_business_name = models.CharField(_("Business Name on Gateway"), max_length=255, blank=True)
    gateway_email = models.EmailField(_("Email on Gateway"), blank=True)
    validated_at = models.DateTimeField(_("Validated At"), null=True, blank=True)
    validation_note = models.TextField(_("Validation Note"), blank=True)
    invalid_reason = models.TextField(_("Invalid Reason"), blank=True)
    revoked_at = models.DateTimeField(_("Revoked At"), null=True, blank=True)
    revoked_by = models.ForeignKey(
        "userauth.TenantUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revoked_payment_credentials",
    )
    revoke_reason = models.TextField(_("Revoke Reason"), blank=True)
    submitted_by = models.ForeignKey(
        "userauth.TenantUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="submitted_payment_credentials",
    )

    class Meta:
        verbose_name = _("Tenant Gateway Credential")
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["payment_profile", "gateway", "status"])]

    def __str__(self):
        return f"[{self.environment.upper()}] {self.gateway.name} - {self.status}"


class SupportedCurrency(TimestampedModel):
    """Currencies the tenant accepts for payment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment_profile = models.ForeignKey(TenantPaymentProfile, on_delete=models.CASCADE, related_name="supported_currencies")
    currency_code = models.CharField(_("Currency"), max_length=3)
    is_default = models.BooleanField(_("Default"), default=False)
    is_enabled = models.BooleanField(_("Enabled"), default=True)
    preferred_gateway = models.ForeignKey(
        TenantGatewayMode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="currency_preferences",
    )
    exchange_rate_to_default = models.DecimalField(_("Exchange Rate"), max_digits=18, decimal_places=6, null=True, blank=True)

    class Meta:
        verbose_name = _("Supported Currency")
        unique_together = [("payment_profile", "currency_code")]

    def __str__(self):
        return f"{self.currency_code} {'(default)' if self.is_default else ''}"
