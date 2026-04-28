from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class MarketplaceTimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class FeatureType(models.TextChoices):
    BOOLEAN = "boolean", _("Boolean")
    LIMIT = "limit", _("Limit")
    USAGE = "usage", _("Usage")


class BillingCycle(models.TextChoices):
    ONE_TIME = "one_time", _("One-Time")
    MONTHLY = "monthly", _("Monthly")
    ANNUAL = "annual", _("Annual")
    PERPETUAL = "perpetual", _("Perpetual")


class DiscountType(models.TextChoices):
    PERCENTAGE = "percentage", _("Percentage")
    FIXED = "fixed", _("Fixed Amount")


class FeatureCategory(MarketplaceTimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class FeatureDefinition(MarketplaceTimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(
        FeatureCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="features",
    )
    name = models.CharField(max_length=120, unique=True)
    code = models.SlugField(max_length=100, unique=True, db_index=True)
    short_description = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    feature_type = models.CharField(max_length=20, choices=FeatureType.choices, db_index=True)
    default_boolean_value = models.BooleanField(default=False)
    default_limit_value = models.PositiveIntegerField(default=0)
    default_usage_value = models.PositiveIntegerField(default=0)
    unit_label = models.CharField(max_length=50, blank=True)
    badge_label = models.CharField(max_length=50, blank=True)
    icon = models.CharField(max_length=50, blank=True)
    store_setting_key = models.CharField(max_length=100, blank=True)
    sidebar_key = models.CharField(max_length=100, blank=True)
    storefront_flag = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_purchasable = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_globally_enabled = models.BooleanField(default=False, db_index=True)
    is_globally_disabled = models.BooleanField(default=False, db_index=True)
    display_order = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["display_order", "name"]
        indexes = [
            models.Index(fields=["feature_type", "is_active"]),
            models.Index(fields=["code", "is_active"]),
            models.Index(fields=["is_purchasable", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} [{self.code}]"

    @property
    def default_value(self):
        if self.feature_type == FeatureType.BOOLEAN:
            return self.default_boolean_value
        if self.feature_type == FeatureType.LIMIT:
            return self.default_limit_value
        return self.default_usage_value

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = slugify(self.name)
        super().save(*args, **kwargs)


class FeaturePrice(MarketplaceTimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feature = models.ForeignKey(FeatureDefinition, on_delete=models.CASCADE, related_name="prices")
    currency = models.CharField(max_length=3, default="NGN", db_index=True)
    billing_cycle = models.CharField(max_length=20, choices=BillingCycle.choices, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    credits_included = models.PositiveIntegerField(default=0)
    limit_increment = models.PositiveIntegerField(default=0)
    display_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["feature__display_order", "currency", "billing_cycle"]
        unique_together = [("feature", "currency", "billing_cycle")]
        indexes = [models.Index(fields=["feature", "currency", "is_active"])]

    def __str__(self) -> str:
        return f"{self.feature.code} {self.currency} {self.amount}/{self.billing_cycle}"

    @property
    def is_current(self) -> bool:
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True


class FeatureBundle(MarketplaceTimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    tagline = models.CharField(max_length=200, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    currency = models.CharField(max_length=3, default="NGN")
    billing_cycle = models.CharField(max_length=20, choices=BillingCycle.choices, default=BillingCycle.MONTHLY)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    icon = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    display_order = models.PositiveIntegerField(default=0)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class BundleItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bundle = models.ForeignKey(FeatureBundle, on_delete=models.CASCADE, related_name="items")
    feature = models.ForeignKey(FeatureDefinition, on_delete=models.PROTECT, related_name="bundle_items")
    quantity_override = models.PositiveIntegerField(null=True, blank=True)
    boolean_override = models.BooleanField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "feature__display_order", "feature__name"]
        unique_together = [("bundle", "feature")]

    def __str__(self) -> str:
        return f"{self.bundle.name} -> {self.feature.code}"


class DiscountCampaign(MarketplaceTimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    applicable_features = models.ManyToManyField(FeatureDefinition, blank=True, related_name="campaigns")
    applicable_bundles = models.ManyToManyField(FeatureBundle, blank=True, related_name="campaigns")
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    current_uses = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def is_valid(self) -> bool:
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        if self.max_uses and self.current_uses >= self.max_uses:
            return False
        return True


class Coupon(MarketplaceTimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    description = models.TextField(blank=True)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0"))])
    applicable_features = models.ManyToManyField(FeatureDefinition, blank=True, related_name="coupons")
    applicable_bundles = models.ManyToManyField(FeatureBundle, blank=True, related_name="coupons")
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    max_uses_per_tenant = models.PositiveIntegerField(default=1)
    current_uses = models.PositiveIntegerField(default=0)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code

    @property
    def is_valid(self) -> bool:
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        if self.max_uses and self.current_uses >= self.max_uses:
            return False
        return True


class FeaturePurchaseIndex(MarketplaceTimestampedModel):
    class PurchaseStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROCESSING = "processing", _("Processing")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")
        CANCELLED = "cancelled", _("Cancelled")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_id = models.UUIDField(unique=True, db_index=True)
    purchase_reference = models.CharField(max_length=64, unique=True, db_index=True)
    schema_name = models.CharField(max_length=63, db_index=True)
    gateway_provider = models.CharField(max_length=50, blank=True, db_index=True)
    gateway_reference = models.CharField(max_length=255, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=PurchaseStatus.choices, default=PurchaseStatus.PENDING, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["schema_name", "status"])]

    def __str__(self) -> str:
        return f"{self.purchase_reference} @ {self.schema_name}"


class TenantFeatureOverride(MarketplaceTimestampedModel):
    class OverrideMode(models.TextChoices):
        FORCE_ENABLED = "force_enabled", _("Force Enabled")
        FORCE_DISABLED = "force_disabled", _("Force Disabled")
        FREE = "free", _("Free")
        CUSTOM_PRICE = "custom_price", _("Custom Price")
        CUSTOM_DISCOUNT_PERCENT = "custom_discount_percent", _("Custom Discount (%)")
        CUSTOM_DISCOUNT_AMOUNT = "custom_discount_amount", _("Custom Discount Amount")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="feature_overrides")
    schema_name = models.CharField(max_length=63, db_index=True)
    feature = models.ForeignKey(FeatureDefinition, on_delete=models.CASCADE, related_name="tenant_overrides")
    mode = models.CharField(max_length=30, choices=OverrideMode.choices, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    currency = models.CharField(max_length=3, blank=True)
    billing_cycle = models.CharField(max_length=20, choices=BillingCycle.choices, blank=True)
    custom_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    custom_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    custom_discount_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    effective_from = models.DateTimeField(default=timezone.now)
    effective_until = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["schema_name", "is_active"]),
            models.Index(fields=["feature", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.schema_name} - {self.feature.code} - {self.mode}"

    @property
    def is_current(self) -> bool:
        now = timezone.now()
        if not self.is_active:
            return False
        if self.effective_from and now < self.effective_from:
            return False
        if self.effective_until and now > self.effective_until:
            return False
        return True


class FeatureEntitlementIndex(MarketplaceTimestampedModel):
    """Public projection of tenant feature entitlements for fast platform reporting."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="feature_entitlement_indices")
    schema_name = models.CharField(max_length=63, db_index=True)
    entitlement_id = models.UUIDField(unique=True, db_index=True)
    feature_id = models.UUIDField(db_index=True)
    feature_code = models.CharField(max_length=100, db_index=True)
    feature_name = models.CharField(max_length=150, blank=True)
    feature_type = models.CharField(max_length=20, db_index=True)
    status = models.CharField(max_length=20, blank=True, db_index=True)
    source = models.CharField(max_length=20, blank=True)
    purchase_reference = models.CharField(max_length=64, blank=True, db_index=True)
    quantity_granted = models.PositiveIntegerField(default=0)
    quantity_used = models.PositiveIntegerField(default=0)
    boolean_value = models.BooleanField(default=False)
    limit_value = models.PositiveIntegerField(default=0)
    billing_cycle = models.CharField(max_length=20, blank=True)
    currency = models.CharField(max_length=3, default="NGN")
    activated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    usage_summary = models.CharField(max_length=255, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["feature_name", "schema_name", "-created_at"]
        indexes = [
            models.Index(fields=["feature_code", "schema_name"]),
            models.Index(fields=["schema_name", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.schema_name} - {self.feature_code}"
