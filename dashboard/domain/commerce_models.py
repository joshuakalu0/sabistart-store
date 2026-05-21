from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class DomainCommerceTimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DomainProvider(DomainCommerceTimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True, db_index=True)
    is_default = models.BooleanField(default=False)
    supports_availability = models.BooleanField(default=True)
    supports_registration = models.BooleanField(default=True)
    supports_renewal = models.BooleanField(default=True)
    supports_dns = models.BooleanField(default=False)
    supports_nameserver_update = models.BooleanField(default=False)
    supports_contact_management = models.BooleanField(default=False)
    supports_privacy = models.BooleanField(default=False)
    docs_url = models.URLField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name


class DomainProviderCredential(DomainCommerceTimestampedModel):
    class Environment(models.TextChoices):
        SANDBOX = "sandbox", "Sandbox"
        LIVE = "live", "Live"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(DomainProvider, on_delete=models.CASCADE, related_name="credentials")
    name = models.CharField(max_length=120)
    api_user = models.CharField(max_length=255, blank=True)
    username = models.CharField(max_length=255, blank=True)
    api_key = models.CharField(max_length=255, blank=True)
    client_ip = models.CharField(max_length=100, blank=True)
    environment = models.CharField(max_length=20, choices=Environment.choices, default=Environment.SANDBOX)
    request_timeout_seconds = models.PositiveIntegerField(default=20)
    is_active = models.BooleanField(default=True, db_index=True)
    is_default = models.BooleanField(default=False)
    last_healthcheck_at = models.DateTimeField(null=True, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["provider__display_order", "name"]

    def __str__(self) -> str:
        return f"{self.provider.name} · {self.name}"

    @property
    def endpoint(self) -> str:
        if self.provider.code == "namecheap":
            if self.environment == self.Environment.SANDBOX:
                return "https://api.sandbox.namecheap.com/xml.response"
            return "https://api.namecheap.com/xml.response"
        return self.metadata.get("endpoint", "")


class TldCatalogEntry(DomainCommerceTimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(DomainProvider, on_delete=models.CASCADE, related_name="tlds")
    tld = models.CharField(max_length=50, db_index=True)
    currency = models.CharField(max_length=3, default="USD")
    registration_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    renewal_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    transfer_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    platform_markup_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    platform_markup_percent = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    minimum_years = models.PositiveIntegerField(default=1)
    maximum_years = models.PositiveIntegerField(default=10)
    is_enabled = models.BooleanField(default=True, db_index=True)
    supports_registration = models.BooleanField(default=True)
    supports_renewal = models.BooleanField(default=True)
    supports_dns = models.BooleanField(default=False)
    is_premium_tld = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["sort_order", "tld"]
        unique_together = ("provider", "tld")

    def __str__(self) -> str:
        return f"{self.tld} ({self.provider.code})"

    @property
    def selling_registration_price(self) -> Decimal:
        base = self.registration_price + self.platform_markup_amount
        if self.platform_markup_percent:
            base += (self.registration_price * self.platform_markup_percent / Decimal("100"))
        return base.quantize(Decimal("0.01"))

    @property
    def selling_renewal_price(self) -> Decimal:
        base = self.renewal_price + self.platform_markup_amount
        if self.platform_markup_percent:
            base += (self.renewal_price * self.platform_markup_percent / Decimal("100"))
        return base.quantize(Decimal("0.01"))


class TenantDomainContact(DomainCommerceTimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="domain_contacts")
    label = models.CharField(max_length=120, blank=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    organization = models.CharField(max_length=150, blank=True)
    job_title = models.CharField(max_length=120, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=40)
    address1 = models.CharField(max_length=255)
    address2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120)
    state_province = models.CharField(max_length=120)
    postal_code = models.CharField(max_length=40)
    country_code = models.CharField(max_length=2)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "first_name", "last_name", "email"]

    def __str__(self) -> str:
        return f"{self.full_name} · {self.email}"

    @property
    def full_name(self) -> str:
        return " ".join(part for part in [self.first_name, self.last_name] if part).strip()


class DomainAvailabilityCache(DomainCommerceTimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(DomainProvider, on_delete=models.CASCADE, related_name="availability_cache")
    domain_name = models.CharField(max_length=253, db_index=True)
    currency = models.CharField(max_length=3, default="USD")
    is_available = models.BooleanField(default=False, db_index=True)
    is_premium = models.BooleanField(default=False)
    is_supported = models.BooleanField(default=True)
    registration_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    renewal_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    suggestion_score = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal("0.00"))
    status_reason = models.CharField(max_length=120, blank=True)
    source_payload = models.JSONField(default=dict, blank=True)
    checked_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-checked_at"]
        unique_together = ("provider", "domain_name")

    def __str__(self) -> str:
        return self.domain_name

    @property
    def is_fresh(self) -> bool:
        return bool(self.expires_at and self.expires_at > timezone.now())


class DomainPurchaseOrder(DomainCommerceTimestampedModel):
    class OrderType(models.TextChoices):
        REGISTER = "register", "Register"
        RENEW = "renew", "Renew"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting Payment"
        PAID = "paid", "Paid"
        PROVISIONING = "provisioning", "Provisioning"
        ACTIVE = "active", "Active"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    class NameserverMode(models.TextChoices):
        PROVIDER_DEFAULT = "provider_default", "Provider Default"
        CUSTOM = "custom", "Custom Nameservers"
        EXTERNAL = "external", "External DNS"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="domain_orders")
    provider = models.ForeignKey(DomainProvider, on_delete=models.PROTECT, related_name="domain_orders")
    provider_credential = models.ForeignKey(
        DomainProviderCredential,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="domain_orders",
    )
    contact = models.ForeignKey(
        TenantDomainContact,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="domain_orders",
    )
    managed_domain = models.ForeignKey(
        "ManagedDomain",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orders",
    )
    purchase_reference = models.CharField(max_length=64, unique=True, db_index=True)
    order_type = models.CharField(max_length=20, choices=OrderType.choices, default=OrderType.REGISTER)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    domain_name = models.CharField(max_length=253, db_index=True)
    years = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    currency = models.CharField(max_length=3, default="USD")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    privacy_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    auto_renew = models.BooleanField(default=True)
    privacy_enabled = models.BooleanField(default=False)
    nameserver_mode = models.CharField(max_length=30, choices=NameserverMode.choices, default=NameserverMode.PROVIDER_DEFAULT)
    custom_nameservers = models.JSONField(default=list, blank=True)
    payment_schema_name = models.CharField(max_length=63, blank=True, db_index=True)
    gateway_provider = models.CharField(max_length=50, blank=True, db_index=True)
    gateway_name = models.CharField(max_length=120, blank=True)
    gateway_reference = models.CharField(max_length=255, blank=True, db_index=True)
    gateway_transaction_id = models.CharField(max_length=255, blank=True, db_index=True)
    provider_order_id = models.CharField(max_length=255, blank=True, db_index=True)
    provider_transaction_id = models.CharField(max_length=255, blank=True, db_index=True)
    success_redirect_url = models.URLField(blank=True)
    cancel_redirect_url = models.URLField(blank=True)
    payment_metadata = models.JSONField(default=dict, blank=True)
    initiated_by_email = models.EmailField(blank=True)
    initiated_by_name = models.CharField(max_length=150, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["domain_name", "status"]),
        ]

    def __str__(self) -> str:
        return self.purchase_reference


class ManagedDomain(DomainCommerceTimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROVISIONING = "provisioning", "Provisioning"
        ACTIVE = "active", "Active"
        EXPIRING = "expiring", "Expiring Soon"
        RENEWAL_DUE = "renewal_due", "Renewal Due"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        SUSPENDED = "suspended", "Suspended"

    class NameserverMode(models.TextChoices):
        PROVIDER_DEFAULT = "provider_default", "Provider Default"
        CUSTOM = "custom", "Custom Nameservers"
        EXTERNAL = "external", "External DNS"

    class ConnectionStatus(models.TextChoices):
        DETACHED = "detached", "Not Connected"
        PENDING = "pending", "Pending Connection"
        CONNECTED = "connected", "Connected"
        FAILED = "failed", "Connection Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="managed_domains")
    provider = models.ForeignKey(DomainProvider, on_delete=models.PROTECT, related_name="managed_domains")
    provider_credential = models.ForeignKey(
        DomainProviderCredential,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_domains",
    )
    contact = models.ForeignKey(
        TenantDomainContact,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="managed_domains",
    )
    source_order = models.ForeignKey(
        DomainPurchaseOrder,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="provisioned_domains",
    )
    domain_name = models.CharField(max_length=253, unique=True, db_index=True)
    sld = models.CharField(max_length=190, blank=True)
    tld = models.CharField(max_length=50, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    connection_status = models.CharField(
        max_length=20,
        choices=ConnectionStatus.choices,
        default=ConnectionStatus.DETACHED,
        db_index=True,
    )
    nameserver_mode = models.CharField(max_length=30, choices=NameserverMode.choices, default=NameserverMode.PROVIDER_DEFAULT)
    current_nameservers = models.JSONField(default=list, blank=True)
    desired_nameservers = models.JSONField(default=list, blank=True)
    provider_domain_id = models.CharField(max_length=255, blank=True, db_index=True)
    provider_order_id = models.CharField(max_length=255, blank=True, db_index=True)
    provider_status = models.CharField(max_length=120, blank=True)
    auto_renew = models.BooleanField(default=True)
    privacy_enabled = models.BooleanField(default=False)
    registration_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    renewal_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    is_premium = models.BooleanField(default=False)
    registered_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "connection_status"]),
            models.Index(fields=["status", "expires_at"]),
        ]

    def __str__(self) -> str:
        return self.domain_name

    def save(self, *args, **kwargs):
        if self.domain_name:
            parts = self.domain_name.lower().split(".")
            if len(parts) >= 2:
                self.sld = ".".join(parts[:-1])
                self.tld = f".{parts[-1]}"
        super().save(*args, **kwargs)

    @property
    def is_expiring_soon(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now() + timezone.timedelta(days=30))


class ManagedDomainDNSRecord(DomainCommerceTimestampedModel):
    class RecordType(models.TextChoices):
        A = "A", "A"
        AAAA = "AAAA", "AAAA"
        CNAME = "CNAME", "CNAME"
        TXT = "TXT", "TXT"
        MX = "MX", "MX"
        CAA = "CAA", "CAA"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    managed_domain = models.ForeignKey(ManagedDomain, on_delete=models.CASCADE, related_name="dns_records")
    host = models.CharField(max_length=253)
    record_type = models.CharField(max_length=10, choices=RecordType.choices)
    value = models.CharField(max_length=512)
    ttl = models.PositiveIntegerField(default=1800)
    priority = models.PositiveIntegerField(default=10)
    provider_record_id = models.CharField(max_length=255, blank=True)
    is_generated = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["host", "record_type", "value"]

    def __str__(self) -> str:
        return f"{self.host} {self.record_type} {self.value}"


class DomainProvisioningAttempt(DomainCommerceTimestampedModel):
    class Action(models.TextChoices):
        AVAILABILITY = "availability", "Availability Check"
        REGISTER = "register", "Registration"
        RENEW = "renew", "Renewal"
        SYNC = "sync", "Sync"
        DNS_PULL = "dns_pull", "DNS Pull"
        DNS_PUSH = "dns_push", "DNS Push"
        NAMESERVERS = "nameservers", "Nameserver Update"
        CONNECT = "connect", "Connect to Storefront"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(DomainProvider, on_delete=models.PROTECT, related_name="provisioning_attempts")
    order = models.ForeignKey(
        DomainPurchaseOrder,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="provisioning_attempts",
    )
    managed_domain = models.ForeignKey(
        ManagedDomain,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="provisioning_attempts",
    )
    action = models.CharField(max_length=30, choices=Action.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    message = models.TextField(blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} · {self.status}"


class ManagedDomainRenewal(DomainCommerceTimestampedModel):
    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    managed_domain = models.ForeignKey(ManagedDomain, on_delete=models.CASCADE, related_name="renewal_events")
    order = models.ForeignKey(
        DomainPurchaseOrder,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="renewal_events",
    )
    scheduled_for = models.DateTimeField(db_index=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    years = models.PositiveIntegerField(default=1)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SCHEDULED, db_index=True)
    message = models.TextField(blank=True)

    class Meta:
        ordering = ["-scheduled_for"]

    def __str__(self) -> str:
        return f"{self.managed_domain.domain_name} renewal"


class DomainActivityLog(DomainCommerceTimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="domain_activity")
    managed_domain = models.ForeignKey(
        ManagedDomain,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity",
    )
    custom_domain = models.ForeignKey(
        "CustomDomain",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commerce_activity",
    )
    purchase_order = models.ForeignKey(
        DomainPurchaseOrder,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity",
    )
    event_type = models.CharField(max_length=80, db_index=True)
    actor = models.CharField(max_length=80, blank=True)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "event_type", "-created_at"])]

    def __str__(self) -> str:
        return self.event_type


class DomainNotification(DomainCommerceTimestampedModel):
    class Level(models.TextChoices):
        INFO = "info", "Info"
        SUCCESS = "success", "Success"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="domain_notifications")
    managed_domain = models.ForeignKey(
        ManagedDomain,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
    )
    purchase_order = models.ForeignKey(
        DomainPurchaseOrder,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notifications",
    )
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    title = models.CharField(max_length=255)
    message = models.TextField()
    action_url = models.URLField(blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "is_read", "-created_at"])]

    def __str__(self) -> str:
        return self.title
