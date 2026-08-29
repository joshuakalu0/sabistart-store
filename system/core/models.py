"""
Core Platform Models - Multi-Tenant SaaS

Enterprise-grade model structure for Shopify-like platform.

Architecture:
- Clean separation: Tenant infrastructure vs business logic
- Client: Core tenant instance (TenantMixin)
- ClientDetails: Additional client information (One-to-One with Client)
- Domain: Client domains (DomainMixin)

Models:
- Client: Tenant instances (TenantMixin)
- ClientDetails: Additional client information
- Domain: Client domains (DomainMixin)
- StoreSettings: Store-level settings
"""

from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
from django_tenants.models import TenantMixin, DomainMixin
from decimal import Decimal
import uuid
import secrets
from django.conf import settings


from django.utils.translation import gettext_lazy as _


class Shop(TenantMixin):
    class ProvisioningStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        PROVISIONING = "provisioning", _("Provisioning")
        IN_PROGRESS = "in_progress", _("In Progress")
        READY = "ready", _("Ready")
        FAILED = "failed", _("Failed")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='owned_shops',
        help_text="PlatformUser who owns this tenant shop"
    )
    name = models.CharField(max_length=100)
    created_on = models.DateField(auto_now_add=True)

    # Schema creation & migrations are fully decoupled from the HTTP request/response
    # cycle (Celery-free). Tenant rows are saved as PROVISIONING at signup; migrations
    # run later in micro-chunks via the login guard middleware, the provisioning poll
    # endpoint, or `manage.py run_tenant_chunked_migrations`.
    # NOTE: legacy rows may still carry 'pending' — both are treated as
    # "not yet provisioned" by the guard and the chunked runner.
    auto_create_schema = False

    provisioning_status = models.CharField(
        max_length=20,
        choices=ProvisioningStatus.choices,
        default=ProvisioningStatus.PROVISIONING,
        db_index=True,
        verbose_name=_("Provisioning Status"),
    )
    provisioning_error = models.TextField(
        blank=True,
        default="",
        verbose_name=_("Provisioning Error Trace"),
    )
    provisioned_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Provisioned At"),
    )

    def __str__(self):
        return self.name


class Domain(DomainMixin):
    pass



# ============================================
# FEATURE SYSTEM
# ============================================

# class Feature(models.Model):
#     """
#     Purchasable capability (resource, static, or usage-based).

#     Feature Types:
#     - RESOURCE: Adds capacity (e.g., +50 product slots)
#     - STATIC: Enable/disable functionality (e.g., analytics)
#     - USAGE: Consumable quantity (e.g., AI tokens)
#     """
#     FEATURE_TYPE_CHOICES = [
#         ('resource', 'Resource'),      # Capacity-based
#         ('static', 'Static'),          # On/off feature
#         ('usage', 'Usage-based'),      # Consumable
#     ]

#     BILLING_CYCLE_CHOICES = [
#         ('monthly', 'Monthly'),
#         ('annual', 'Annual'),
#         ('one_time', 'One-time'),
#         ('perpetual', 'Perpetual'),    # Never expires
#     ]

#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     # Identity
#     name = models.CharField(max_length=100, unique=True, db_index=True)
#     slug = models.SlugField(max_length=100, unique=True, db_index=True)
#     description = models.TextField()

#     # Type and behavior
#     feature_type = models.CharField(
#         max_length=20, choices=FEATURE_TYPE_CHOICES, db_index=True)
#     billing_cycle = models.CharField(
#         max_length=20, choices=BILLING_CYCLE_CHOICES, default='monthly')

#     # Pricing
#     price = models.DecimalField(
#         max_digits=10,
#         decimal_places=2,
#         default=0,
#         validators=[MinValueValidator(Decimal('0'))]
#     )
#     currency = models.CharField(max_length=3, default='USD')

#     # Resource-specific (for feature_type='resource')
#     resource_unit = models.CharField(
#         max_length=50,
#         blank=True,
#         help_text="Unit type (e.g., 'products', 'storage_gb')"
#     )
#     resource_quantity = models.PositiveIntegerField(
#         default=0,
#         help_text="Quantity provided (e.g., 50 products)"
#     )

#     # Usage-specific (for feature_type='usage')
#     usage_unit = models.CharField(
#         max_length=50,
#         blank=True,
#         help_text="Unit type (e.g., 'tokens', 'api_calls')"
#     )
#     usage_quantity = models.PositiveIntegerField(
#         default=0,
#         help_text="Quantity provided (e.g., 10000 tokens)"
#     )

#     # Status
#     is_active = models.BooleanField(default=True, db_index=True)
#     is_purchasable = models.BooleanField(
#         default=True, help_text="Can be purchased individually")

#     # Display
#     display_order = models.PositiveIntegerField(default=0)
#     icon = models.CharField(max_length=50, blank=True,
#                             help_text="Icon identifier")

#     # Metadata
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         db_table = 'features'
#         verbose_name = 'Feature'
#         verbose_name_plural = 'Features'
#         ordering = ['display_order', 'name']
#         indexes = [
#             models.Index(fields=['feature_type', 'is_active']),
#             models.Index(fields=['is_purchasable', 'is_active']),
#             models.Index(fields=['billing_cycle']),
#         ]

#     def __str__(self):
#         return f"{self.name} ({self.get_feature_type_display()})"


# class FeatureBundle(models.Model):
#     """
#     Collection of features sold together.
#     Bundles expand into individual entitlements on purchase.
#     """
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     # Identity
#     name = models.CharField(max_length=100, unique=True)
#     slug = models.SlugField(max_length=100, unique=True, db_index=True)
#     description = models.TextField()

#     # Pricing
#     price = models.DecimalField(
#         max_digits=10,
#         decimal_places=2,
#         validators=[MinValueValidator(Decimal('0'))]
#     )
#     currency = models.CharField(max_length=3, default='USD')
#     discount_percentage = models.DecimalField(
#         max_digits=5,
#         decimal_places=2,
#         default=0,
#         help_text="Discount vs individual purchase"
#     )

#     # Features included
#     features = models.ManyToManyField(
#         Feature, through='BundleFeature', related_name='bundles')

#     # Status
#     is_active = models.BooleanField(default=True, db_index=True)
#     is_featured = models.BooleanField(
#         default=False, help_text="Highlight in marketplace")

#     # Display
#     display_order = models.PositiveIntegerField(default=0)

#     # Metadata
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         db_table = 'feature_bundles'
#         verbose_name = 'Feature Bundle'
#         verbose_name_plural = 'Feature Bundles'
#         ordering = ['display_order', 'name']
#         indexes = [
#             models.Index(fields=['is_active', 'is_featured']),
#         ]

#     def __str__(self):
#         return self.name


# class BundleFeature(models.Model):
#     """Through model for bundle-feature relationship with quantity override"""
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     bundle = models.ForeignKey(FeatureBundle, on_delete=models.CASCADE)
#     feature = models.ForeignKey(Feature, on_delete=models.CASCADE)
#     quantity_override = models.PositiveIntegerField(
#         null=True,
#         blank=True,
#         help_text="Override feature quantity in bundle"
#     )

#     class Meta:
#         db_table = 'bundle_features'
#         unique_together = ['bundle', 'feature']
#         verbose_name = 'Bundle Feature'
#         verbose_name_plural = 'Bundle Features'


# # ============================================
# # PURCHASES & TRANSACTIONS
# # ============================================

# class Purchase(models.Model):
#     """
#     Transaction record for feature/bundle purchases.
#     Immutable audit trail.
#     """
#     PURCHASE_TYPE_CHOICES = [
#         ('feature', 'Feature'),
#         ('bundle', 'Bundle'),
#     ]

#     STATUS_CHOICES = [
#         ('pending', 'Pending'),
#         ('completed', 'Completed'),
#         ('failed', 'Failed'),
#         ('refunded', 'Refunded'),
#         ('cancelled', 'Cancelled'),
#     ]

#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     # Purchase details
#     shop = models.ForeignKey(
#         Shop, on_delete=models.PROTECT, related_name='purchases')
#     purchase_type = models.CharField(
#         max_length=20, choices=PURCHASE_TYPE_CHOICES)

#     # What was purchased
#     feature = models.ForeignKey(
#         Feature, on_delete=models.SET_NULL, null=True, blank=True)
#     bundle = models.ForeignKey(
#         FeatureBundle, on_delete=models.SET_NULL, null=True, blank=True)
#     quantity = models.PositiveIntegerField(
#         default=1, help_text="For usage-based features")

#     # Financial
#     amount = models.DecimalField(max_digits=10, decimal_places=2)
#     currency = models.CharField(max_length=3, default='USD')
#     status = models.CharField(
#         max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)

#     # Payment reference
#     payment_gateway = models.CharField(max_length=50, blank=True)
#     payment_reference = models.CharField(
#         max_length=255, blank=True, db_index=True)
#     payment_metadata = models.JSONField(default=dict, blank=True)

#     # Refund tracking
#     refund_amount = models.DecimalField(
#         max_digits=10, decimal_places=2, default=0)
#     refund_reason = models.TextField(blank=True)
#     refunded_at = models.DateTimeField(null=True, blank=True)

#     # Timestamps
#     purchased_at = models.DateTimeField(auto_now_add=True, db_index=True)
#     completed_at = models.DateTimeField(null=True, blank=True)

#     class Meta:
#         db_table = 'purchases'
#         verbose_name = 'Purchase'
#         verbose_name_plural = 'Purchases'
#         ordering = ['-purchased_at']
#         indexes = [
#             models.Index(fields=['shop', 'status', '-purchased_at']),
#             models.Index(fields=['status', '-purchased_at']),
#             models.Index(fields=['payment_reference']),
#         ]

#     def __str__(self):
#         item = self.feature.name if self.feature else self.bundle.name if self.bundle else 'Unknown'
#         return f"Purchase #{self.id} - {self.shop.name} - {item}"


# # ============================================
# # SHOP ENTITLEMENTS
# # ============================================

# class ShopEntitlement(models.Model):
#     """
#     Active feature entitlement for a shop.
#     Created when feature is purchased, tracks expiry and usage.
#     """
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     shop = models.ForeignKey(
#         Shop, on_delete=models.CASCADE, related_name='entitlements')
#     feature = models.ForeignKey(Feature, on_delete=models.PROTECT)
#     purchase = models.ForeignKey(
#         Purchase, on_delete=models.SET_NULL, null=True, blank=True)

#     # Quantity (for resource and usage features)
#     quantity_granted = models.PositiveIntegerField(
#         default=0, help_text="Total quantity granted")
#     quantity_used = models.PositiveIntegerField(
#         default=0, help_text="Quantity consumed")

#     # Lifecycle
#     is_active = models.BooleanField(default=True, db_index=True)
#     activated_at = models.DateTimeField(auto_now_add=True)
#     expires_at = models.DateTimeField(null=True, blank=True, db_index=True)

#     # Renewal
#     auto_renew = models.BooleanField(default=False)
#     last_renewed_at = models.DateTimeField(null=True, blank=True)

#     class Meta:
#         db_table = 'shop_entitlements'
#         verbose_name = 'Shop Entitlement'
#         verbose_name_plural = 'Shop Entitlements'
#         ordering = ['-activated_at']
#         indexes = [
#             models.Index(fields=['shop', 'feature', 'is_active']),
#             models.Index(fields=['is_active', 'expires_at']),
#             models.Index(fields=['auto_renew', 'expires_at']),
#         ]

#     def __str__(self):
#         return f"{self.shop.name} - {self.feature.name}"

#     @property
#     def is_expired(self):
#         """Check if entitlement has expired"""
#         if not self.expires_at:
#             return False
#         return timezone.now() > self.expires_at

#     @property
#     def quantity_remaining(self):
#         """Remaining quantity for usage-based features"""
#         return max(0, self.quantity_granted - self.quantity_used)

#     @property
#     def is_valid(self):
#         """Check if entitlement is currently valid"""
#         return self.is_active and not self.is_expired and self.quantity_remaining > 0


# # ============================================
# # RESOURCE QUOTA TRACKING
# # ============================================

# class ResourceQuota(models.Model):
#     """
#     Aggregated resource capacity for a shop.
#     Calculated from active resource-type entitlements.

#     Example: Shop has 3 entitlements for product space:
#     - Base: 50 products
#     - Addon 1: +50 products
#     - Addon 2: +100 products
#     Total: 200 products
#     """
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     shop = models.ForeignKey(
#         Shop, on_delete=models.CASCADE, related_name='resource_quotas')
#     resource_type = models.CharField(
#         max_length=50,
#         db_index=True,
#         help_text="Resource identifier (e.g., 'products', 'storage_gb')"
#     )

#     # Capacity
#     total_quota = models.PositiveIntegerField(
#         default=0, help_text="Total capacity from entitlements")
#     used_quota = models.PositiveIntegerField(
#         default=0, help_text="Currently used")

#     # Timestamps
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         db_table = 'resource_quotas'
#         verbose_name = 'Resource Quota'
#         verbose_name_plural = 'Resource Quotas'
#         unique_together = ['shop', 'resource_type']
#         indexes = [
#             models.Index(fields=['shop', 'resource_type']),
#         ]

#     def __str__(self):
#         return f"{self.shop.name} - {self.resource_type}: {self.used_quota}/{self.total_quota}"

#     @property
#     def available_quota(self):
#         """Available capacity"""
#         return max(0, self.total_quota - self.used_quota)

#     @property
#     def is_quota_exceeded(self):
#         """Check if quota is exceeded"""
#         return self.used_quota > self.total_quota

#     @property
#     def usage_percentage(self):
#         """Usage as percentage"""
#         if self.total_quota == 0:
#             return 0
#         return min(100, (self.used_quota / self.total_quota) * 100)


# # ============================================
# # USAGE TRACKING
# # ============================================

# class UsageRecord(models.Model):
#     """
#     Individual usage event for usage-based features.
#     Tracks consumption of tokens, API calls, etc.
#     Immutable audit trail.
#     """
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

#     entitlement = models.ForeignKey(
#         ShopEntitlement, on_delete=models.PROTECT, related_name='usage_records')
#     shop = models.ForeignKey(
#         Shop, on_delete=models.PROTECT, related_name='usage_records')

#     # Usage details
#     quantity_used = models.PositiveIntegerField(default=1)
#     description = models.CharField(max_length=255, blank=True)

#     # Context
#     metadata = models.JSONField(
#         default=dict,
#         blank=True,
#         help_text="Additional context (e.g., API endpoint, model used)"
#     )

#     # Timestamp
#     used_at = models.DateTimeField(auto_now_add=True, db_index=True)

#     class Meta:
#         db_table = 'usage_records'
#         verbose_name = 'Usage Record'
#         verbose_name_plural = 'Usage Records'
#         ordering = ['-used_at']
#         indexes = [
#             models.Index(fields=['shop', '-used_at']),
#             models.Index(fields=['entitlement', '-used_at']),
#         ]

#     def __str__(self):
#         return f"{self.shop.name} - {self.entitlement.feature.name} - {self.quantity_used} units"
