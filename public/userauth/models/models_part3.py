"""
accounts/models_part3.py
=========================
APP 2 — Accounts Domain | Part 3 of 3

PART 3 — Customers (TENANT schema)
  Section 15 — Customer Groups
  Section 16 — Customer (tenant-scoped buyer profile)
  Section 17 — Customer Addresses
  Section 18 — Customer Notes
  Section 19 — Customer Sessions (storefront)
  Section 20 — Guest Tokens
"""

from __future__ import annotations

import secrets
import uuid

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dashboard.settings.models import MixIdAndTimeModel, IduuidModel, AuditModel
from .tenant_user import TenantUser

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
        app_label = "userauth"
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
    Customer profile — commerce-specific data only.

    This model ONLY contains fields directly related to commerce:
    - Order statistics (total spent, order count, AOV)
    - Segmentation (groups, tags, tier, loyalty points)
    - Tax information (B2B, VAT/EIN)
    - Acquisition attribution (UTM, referral)

    Fields that are NOT here (they're in TenantUser):
    - Identity: email, name, phone — use user.email, user.first_name, etc.
    - Authentication: password, 2FA, login history — in TenantUser
    - Marketing consent — in TenantUser
    - Preferences: locale, currency, timezone — in TenantUser

    Guest customers (checkout without account) have user=None.
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

    # ── Identity (link to TenantUser for identity/auth) ─────────────
    # Null for guest checkouts.
    user = models.OneToOneField(
        TenantUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="customer_profile",
        help_text=_(
            "Tenant user account. Null for guest customers. "
            "Identity (name, email, phone) is stored in TenantUser."
        ),
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
        CustomerGroup,
        blank=True,
        related_name="customers",
    )
    tags = models.JSONField(
        default=list,
        help_text=_(
            "Freeform tags for segmentation, e.g. ['vip', 'wholesale']."),
    )
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

    # ── Acquisition ───────────────────────────────────────────────────
    acquisition_source = models.CharField(
        max_length=15,
        choices=AcquisitionSource.choices,
        blank=True,
    )
    referral_code = models.CharField(max_length=50, blank=True)
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)

    # ── Staff-facing notes ────────────────────────────────────────────
    staff_note = models.TextField(blank=True)

    class Meta:
        app_label = "userauth"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user_id"]),
            models.Index(fields=["status"]),
            models.Index(fields=["total_spent"]),
            models.Index(fields=["last_order_at"]),
        ]

    def __str__(self) -> str:
        if self.user:
            return f"{self.user.email}"
        return f"Guest Customer {self.id}"

    @property
    def is_registered(self) -> bool:
        return self.user_id is not None

    @property
    def is_guest(self) -> bool:
        return self.user_id is None

    @property
    def display_name(self) -> str:
        if self.user:
            name = self.user.get_full_name()
            if self.company:
                return f"{name} ({self.company})"
            return name
        return f"Guest {self.id}"

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
        app_label = "userauth"
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
        app_label = "userauth"
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
        app_label = "userauth"
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
        app_label = "userauth"
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
