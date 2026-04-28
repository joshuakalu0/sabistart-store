from __future__ import annotations

import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class MarketplaceTimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class TenantEntitlement(MarketplaceTimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"
        EXHAUSTED = "exhausted", "Exhausted"
        CANCELLED = "cancelled", "Cancelled"

    class Source(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        MANUAL = "manual", "Manual"
        GRANDFATHER = "grandfather", "Grandfathered"
        GLOBAL = "global", "Global Override"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    feature_id = models.UUIDField(db_index=True)
    feature_code = models.CharField(max_length=100, db_index=True)
    feature_name = models.CharField(max_length=150, blank=True)
    feature_type = models.CharField(max_length=20, db_index=True)
    purchase_id = models.UUIDField(null=True, blank=True, db_index=True)
    purchase_reference = models.CharField(max_length=64, blank=True, db_index=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.PURCHASE, db_index=True)
    source_note = models.TextField(blank=True)
    quantity_granted = models.PositiveIntegerField(default=0)
    quantity_used = models.PositiveIntegerField(default=0)
    boolean_value = models.BooleanField(default=True)
    limit_value = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    auto_renew = models.BooleanField(default=False)
    renewal_price_id = models.UUIDField(null=True, blank=True)
    last_renewed_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    billing_cycle = models.CharField(max_length=20, blank=True)
    currency = models.CharField(max_length=3, default="NGN")
    price_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    compatibility_setting_key = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-activated_at", "-created_at"]
        indexes = [
            models.Index(fields=["feature_code", "status"]),
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["feature_type", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.feature_code} ({self.status})"

    @property
    def quantity_remaining(self) -> int:
        return max(0, self.quantity_granted - self.quantity_used)

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and timezone.now() > self.expires_at)

    @property
    def is_valid(self) -> bool:
        if self.status != self.Status.ACTIVE:
            return False
        if self.is_expired:
            return False
        if self.feature_type == "usage" and self.quantity_remaining <= 0:
            return False
        return True


class FeaturePurchase(MarketplaceTimestampedModel):
    class PurchaseType(models.TextChoices):
        FEATURE = "feature", "Feature"
        BUNDLE = "bundle", "Bundle"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"
        REFUNDED = "refunded", "Refunded"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_reference = models.CharField(max_length=64, unique=True, db_index=True)
    purchase_type = models.CharField(max_length=20, choices=PurchaseType.choices)
    feature_id = models.UUIDField(null=True, blank=True, db_index=True)
    feature_code = models.CharField(max_length=100, blank=True, db_index=True)
    feature_name = models.CharField(max_length=150, blank=True)
    bundle_id = models.UUIDField(null=True, blank=True, db_index=True)
    bundle_slug = models.CharField(max_length=100, blank=True, db_index=True)
    bundle_name = models.CharField(max_length=150, blank=True)
    price_id = models.UUIDField(null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    billing_cycle = models.CharField(max_length=20, blank=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")
    coupon_code = models.CharField(max_length=50, blank=True, db_index=True)
    campaign_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    gateway_definition_id = models.UUIDField(null=True, blank=True)
    gateway_provider = models.CharField(max_length=50, blank=True, db_index=True)
    gateway_name = models.CharField(max_length=100, blank=True)
    gateway_reference = models.CharField(max_length=255, blank=True, db_index=True)
    gateway_transaction_id = models.CharField(max_length=255, blank=True, db_index=True)
    success_redirect_url = models.URLField(blank=True)
    cancel_redirect_url = models.URLField(blank=True)
    payment_metadata = models.JSONField(default=dict, blank=True)
    initiated_by_email = models.EmailField(blank=True)
    initiated_by_name = models.CharField(max_length=150, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["feature_code", "status"]),
        ]

    def __str__(self) -> str:
        return self.purchase_reference


class FeaturePurchaseItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase = models.ForeignKey(FeaturePurchase, on_delete=models.CASCADE, related_name="items")
    feature_id = models.UUIDField(db_index=True)
    feature_code = models.CharField(max_length=100, db_index=True)
    feature_name = models.CharField(max_length=150, blank=True)
    feature_type = models.CharField(max_length=20)
    quantity_granted = models.PositiveIntegerField(default=0)
    limit_value = models.PositiveIntegerField(default=0)
    boolean_value = models.BooleanField(default=True)
    unit_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["feature_code"]

    def __str__(self) -> str:
        return f"{self.purchase.purchase_reference} -> {self.feature_code}"


class ResourceQuota(MarketplaceTimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    resource_type = models.CharField(max_length=100, unique=True, db_index=True)
    total_quota = models.PositiveIntegerField(default=0)
    used_quota = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["resource_type"]

    def __str__(self) -> str:
        return f"{self.resource_type}: {self.used_quota}/{self.total_quota}"

    @property
    def available_quota(self) -> int:
        return max(0, self.total_quota - self.used_quota)


class UsageRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entitlement = models.ForeignKey(TenantEntitlement, on_delete=models.PROTECT, related_name="usage_records")
    feature_code = models.CharField(max_length=100, db_index=True)
    quantity_used = models.PositiveIntegerField(default=1)
    description = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    used_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-used_at"]
        indexes = [models.Index(fields=["feature_code", "-used_at"])]

    def __str__(self) -> str:
        return f"{self.feature_code} {self.quantity_used}"


class CouponRedemption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    coupon_code = models.CharField(max_length=50, db_index=True)
    coupon_id = models.UUIDField(db_index=True)
    purchase = models.ForeignKey(FeaturePurchase, on_delete=models.CASCADE, related_name="coupon_redemptions")
    discount_applied = models.DecimalField(max_digits=12, decimal_places=2)
    redeemed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-redeemed_at"]

    def __str__(self) -> str:
        return self.coupon_code
