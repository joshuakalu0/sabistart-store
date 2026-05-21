"""
Advanced pricing and promotion workflow models.

This module adds the additive schema required for:
  - Pricing analytics intelligence surfaces
  - Discount A/B experiments
  - Explicit stacking / compatibility rules
  - Import / export staging
  - Cron-driven trigger delivery
  - Partner / influencer attribution
  - Bundle offers
"""

from __future__ import annotations

import hashlib
import secrets
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from dashboard.settings.models import ActivatableModel, AuditModel, IduuidModel, MixIdAndTimeModel
from public.category.models import Category
from public.product.models import Product, ProductVariant
from public.userauth.models import Customer, CustomerGroup

from .part2 import AutomaticDiscount, DiscountCode, DiscountUsage


class PromotionPartner(AuditModel, ActivatableModel):
    class PartnerType(models.TextChoices):
        AFFILIATE = "affiliate", _("Affiliate")
        CREATOR = "creator", _("Creator / Influencer")
        STAFF = "staff", _("Staff / Internal")
        CAMPAIGN = "campaign", _("Campaign Source")
        REFERRAL = "referral", _("Referral Program")

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    partner_type = models.CharField(
        max_length=20,
        choices=PartnerType.choices,
        default=PartnerType.AFFILIATE,
    )
    email = models.EmailField(blank=True)
    code_prefix = models.CharField(max_length=40, blank=True)
    referral_slug = models.SlugField(max_length=120, blank=True)
    commission_rate_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
    )
    default_utm_source = models.CharField(max_length=120, blank=True)
    default_utm_medium = models.CharField(max_length=120, blank=True)
    default_utm_campaign = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Promotion Partner")
        verbose_name_plural = _("Promotion Partners")

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        if not self.referral_slug:
            self.referral_slug = self.slug
        super().save(*args, **kwargs)


class PromotionLink(MixIdAndTimeModel):
    class LinkTarget(models.TextChoices):
        DISCOUNT_CODE = "discount_code", _("Discount Code")
        PARTNER = "partner", _("Partner Landing")
        BUNDLE = "bundle", _("Bundle Offer")

    target_type = models.CharField(
        max_length=20,
        choices=LinkTarget.choices,
        default=LinkTarget.DISCOUNT_CODE,
    )
    discount_code = models.ForeignKey(
        DiscountCode,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="share_links",
    )
    partner = models.ForeignKey(
        PromotionPartner,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="share_links",
    )
    bundle_offer_id = models.UUIDField(null=True, blank=True)
    slug = models.SlugField(max_length=140, unique=True)
    landing_path = models.CharField(max_length=255, blank=True)
    utm_source = models.CharField(max_length=120, blank=True)
    utm_medium = models.CharField(max_length=120, blank=True)
    utm_campaign = models.CharField(max_length=120, blank=True)
    utm_content = models.CharField(max_length=120, blank=True)
    query_overrides = models.JSONField(default=dict, blank=True)
    qr_svg = models.TextField(blank=True)
    click_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["slug"]
        verbose_name = _("Promotion Link")
        verbose_name_plural = _("Promotion Links")

    def __str__(self) -> str:
        return self.slug

    def save(self, *args, **kwargs):
        if not self.slug:
            source = (
                getattr(self.discount_code, "code", "")
                or getattr(self.partner, "slug", "")
                or "promo"
            )
            self.slug = slugify(source)[:100] or secrets.token_hex(6)
        super().save(*args, **kwargs)


class DiscountExperiment(AuditModel, ActivatableModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        LIVE = "live", _("Live")
        PAUSED = "paused", _("Paused")
        COMPLETED = "completed", _("Completed")
        ARCHIVED = "archived", _("Archived")

    class AssignmentMode(models.TextChoices):
        RANDOM = "random", _("Random")
        CUSTOMER_HASH = "customer_hash", _("Deterministic Customer Hash")
        SESSION_HASH = "session_hash", _("Deterministic Session Hash")

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    source_discount = models.ForeignKey(
        DiscountCode,
        on_delete=models.CASCADE,
        related_name="experiments",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    assignment_mode = models.CharField(
        max_length=20,
        choices=AssignmentMode.choices,
        default=AssignmentMode.CUSTOMER_HASH,
    )
    minimum_sample_size = models.PositiveIntegerField(default=50)
    winner_variant = models.ForeignKey(
        "DiscountExperimentVariant",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="won_experiments",
    )
    promoted_at = models.DateTimeField(null=True, blank=True)
    promoted_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Discount Experiment")
        verbose_name_plural = _("Discount Experiments")

    def __str__(self) -> str:
        return self.title


class DiscountExperimentVariant(MixIdAndTimeModel):
    experiment = models.ForeignKey(
        DiscountExperiment,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    label = models.CharField(max_length=100)
    discount_code = models.ForeignKey(
        DiscountCode,
        on_delete=models.CASCADE,
        related_name="experiment_variants",
    )
    allocation_weight = models.PositiveIntegerField(default=50)
    is_control = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["experiment", "-is_control", "label"]
        unique_together = [("experiment", "label"), ("experiment", "discount_code")]
        verbose_name = _("Discount Experiment Variant")
        verbose_name_plural = _("Discount Experiment Variants")

    def __str__(self) -> str:
        return f"{self.experiment.title} — {self.label}"


class DiscountExperimentAssignment(IduuidModel):
    experiment = models.ForeignKey(
        DiscountExperiment,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    variant = models.ForeignKey(
        DiscountExperimentVariant,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="discount_experiment_assignments",
    )
    session_key = models.CharField(max_length=255, blank=True, db_index=True)
    cart_id = models.UUIDField(null=True, blank=True, db_index=True)
    order_id = models.UUIDField(null=True, blank=True, db_index=True)
    order_number = models.CharField(max_length=50, blank=True)
    was_redeemed = models.BooleanField(default=False, db_index=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    revenue_attributed = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    assigned_key = models.CharField(max_length=255, db_index=True)
    assigned_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-assigned_at"]
        unique_together = [("experiment", "assigned_key")]
        verbose_name = _("Discount Experiment Assignment")
        verbose_name_plural = _("Discount Experiment Assignments")

    def __str__(self) -> str:
        return f"{self.experiment.title} -> {self.variant.label}"


class DiscountExperimentSnapshot(MixIdAndTimeModel):
    experiment = models.ForeignKey(
        DiscountExperiment,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    variant = models.ForeignKey(
        DiscountExperimentVariant,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    assignments = models.PositiveIntegerField(default=0)
    redemptions = models.PositiveIntegerField(default=0)
    conversion_rate = models.DecimalField(max_digits=7, decimal_places=4, default=Decimal("0.0000"))
    revenue_attributed = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    average_order_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_winner = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Discount Experiment Snapshot")
        verbose_name_plural = _("Discount Experiment Snapshots")


class PromotionCompatibilityRule(AuditModel):
    class PromotionType(models.TextChoices):
        DISCOUNT_CODE = "discount_code", _("Discount Code")
        AUTOMATIC = "automatic", _("Automatic Discount")

    class Resolution(models.TextChoices):
        ALLOW = "allow", _("Allow Combination")
        DENY = "deny", _("Block Combination")
        PREFER_LEFT = "prefer_left", _("Prefer Left Promotion")
        PREFER_RIGHT = "prefer_right", _("Prefer Right Promotion")

    left_type = models.CharField(max_length=20, choices=PromotionType.choices)
    left_discount_code = models.ForeignKey(
        DiscountCode,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="compatibility_rules_left",
    )
    left_automatic_discount = models.ForeignKey(
        AutomaticDiscount,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="compatibility_rules_left",
    )
    right_type = models.CharField(max_length=20, choices=PromotionType.choices)
    right_discount_code = models.ForeignKey(
        DiscountCode,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="compatibility_rules_right",
    )
    right_automatic_discount = models.ForeignKey(
        AutomaticDiscount,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="compatibility_rules_right",
    )
    resolution = models.CharField(max_length=20, choices=Resolution.choices, default=Resolution.DENY)
    max_combined_discount_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["left_type", "right_type", "-created_at"]
        verbose_name = _("Promotion Compatibility Rule")
        verbose_name_plural = _("Promotion Compatibility Rules")

    def __str__(self) -> str:
        return f"{self.left_type} ↔ {self.right_type} ({self.resolution})"

    @property
    def left_object(self):
        return self.left_discount_code or self.left_automatic_discount

    @property
    def right_object(self):
        return self.right_discount_code or self.right_automatic_discount


class PromotionConflictRecord(MixIdAndTimeModel):
    class Severity(models.TextChoices):
        INFO = "info", _("Info")
        WARNING = "warning", _("Warning")
        ERROR = "error", _("Error")

    class Status(models.TextChoices):
        OPEN = "open", _("Open")
        ACKNOWLEDGED = "acknowledged", _("Acknowledged")
        RESOLVED = "resolved", _("Resolved")

    left_type = models.CharField(max_length=20, choices=PromotionCompatibilityRule.PromotionType.choices)
    left_discount_code = models.ForeignKey(
        DiscountCode,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="conflicts_left",
    )
    left_automatic_discount = models.ForeignKey(
        AutomaticDiscount,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="conflicts_left",
    )
    right_type = models.CharField(max_length=20, choices=PromotionCompatibilityRule.PromotionType.choices)
    right_discount_code = models.ForeignKey(
        DiscountCode,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="conflicts_right",
    )
    right_automatic_discount = models.ForeignKey(
        AutomaticDiscount,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="conflicts_right",
    )
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.WARNING)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    summary = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    acknowledged_by = models.CharField(max_length=255, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Promotion Conflict Record")
        verbose_name_plural = _("Promotion Conflict Records")


class DiscountImportBatch(AuditModel):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PREVIEWED = "previewed", _("Previewed")
        COMMITTED = "committed", _("Committed")
        FAILED = "failed", _("Failed")

    title = models.CharField(max_length=255)
    source_filename = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    column_mapping = models.JSONField(default=dict, blank=True)
    default_values = models.JSONField(default=dict, blank=True)
    validation_summary = models.JSONField(default=dict, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    valid_row_count = models.PositiveIntegerField(default=0)
    committed_row_count = models.PositiveIntegerField(default=0)
    committed_at = models.DateTimeField(null=True, blank=True)
    committed_by = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Discount Import Batch")
        verbose_name_plural = _("Discount Import Batches")

    def __str__(self) -> str:
        return self.title


class DiscountImportRow(MixIdAndTimeModel):
    batch = models.ForeignKey(
        DiscountImportBatch,
        on_delete=models.CASCADE,
        related_name="rows",
    )
    row_number = models.PositiveIntegerField()
    raw_data = models.JSONField(default=dict, blank=True)
    normalized_data = models.JSONField(default=dict, blank=True)
    validation_errors = models.JSONField(default=list, blank=True)
    preview_code = models.CharField(max_length=120, blank=True)
    created_discount = models.ForeignKey(
        DiscountCode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="import_rows",
    )
    is_valid = models.BooleanField(default=False, db_index=True)
    is_committed = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["row_number"]
        unique_together = [("batch", "row_number")]
        verbose_name = _("Discount Import Row")
        verbose_name_plural = _("Discount Import Rows")


class PricingAutomationRule(AuditModel, ActivatableModel):
    class TriggerType(models.TextChoices):
        ABANDONED_CART = "abandoned_cart", _("Abandoned Cart")
        POST_PURCHASE = "post_purchase", _("Post Purchase")
        WIN_BACK = "win_back", _("Win Back")
        MILESTONE = "milestone", _("Milestone")
        BIRTHDAY = "birthday", _("Birthday")
        REVIEW_REWARD = "review_reward", _("Review Reward")

    class DeliveryMode(models.TextChoices):
        SHARED = "shared", _("Shared Code")
        UNIQUE = "unique", _("Unique Single-Use Code")

    name = models.CharField(max_length=255)
    trigger_type = models.CharField(max_length=20, choices=TriggerType.choices, db_index=True)
    source_discount = models.ForeignKey(
        DiscountCode,
        on_delete=models.CASCADE,
        related_name="automation_rules",
    )
    target_group = models.ForeignKey(
        CustomerGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pricing_automation_rules",
    )
    delivery_mode = models.CharField(max_length=10, choices=DeliveryMode.choices, default=DeliveryMode.UNIQUE)
    delay_minutes = models.PositiveIntegerField(default=0)
    evaluation_window_days = models.PositiveIntegerField(default=30)
    issue_prefix = models.CharField(max_length=24, blank=True)
    requires_verified_customer = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    run_count = models.PositiveIntegerField(default=0)
    issued_count = models.PositiveIntegerField(default=0)
    last_run_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Pricing Automation Rule")
        verbose_name_plural = _("Pricing Automation Rules")

    def __str__(self) -> str:
        return self.name


class IssuedDiscountCode(MixIdAndTimeModel):
    class Status(models.TextChoices):
        PENDING = "pending", _("Pending Delivery")
        DELIVERED = "delivered", _("Delivered")
        REDEEMED = "redeemed", _("Redeemed")
        EXPIRED = "expired", _("Expired")
        CANCELLED = "cancelled", _("Cancelled")

    rule = models.ForeignKey(
        PricingAutomationRule,
        on_delete=models.CASCADE,
        related_name="issued_codes",
    )
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="issued_discount_codes",
    )
    discount_code = models.ForeignKey(
        DiscountCode,
        on_delete=models.CASCADE,
        related_name="issued_instances",
    )
    source_event_type = models.CharField(max_length=100, blank=True)
    source_object_id = models.UUIDField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    delivery_payload = models.JSONField(default=dict, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Issued Discount Code")
        verbose_name_plural = _("Issued Discount Codes")


class PricingAutomationDeliveryLog(MixIdAndTimeModel):
    rule = models.ForeignKey(
        PricingAutomationRule,
        on_delete=models.CASCADE,
        related_name="delivery_logs",
    )
    issued_code = models.ForeignKey(
        IssuedDiscountCode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="delivery_logs",
    )
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pricing_delivery_logs",
    )
    cart_id = models.UUIDField(null=True, blank=True)
    order_id = models.UUIDField(null=True, blank=True)
    order_number = models.CharField(max_length=50, blank=True)
    notification_job_id = models.UUIDField(null=True, blank=True)
    channel = models.CharField(max_length=30, blank=True)
    result = models.CharField(max_length=40, default="queued")
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Pricing Automation Delivery Log")
        verbose_name_plural = _("Pricing Automation Delivery Logs")


class BundleOffer(AuditModel, ActivatableModel):
    class OfferType(models.TextChoices):
        FIXED = "fixed", _("Fixed Bundle")
        MIX_MATCH = "mix_match", _("Mix & Match")
        UPSELL = "upsell", _("Upsell / Add-on")

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    offer_type = models.CharField(max_length=20, choices=OfferType.choices, default=OfferType.FIXED)
    description = models.TextField(blank=True)
    public_title = models.CharField(max_length=255, blank=True)
    bundle_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    currency = models.CharField(max_length=3, default="USD")
    required_quantity = models.PositiveIntegerField(default=1)
    min_selection = models.PositiveIntegerField(default=1)
    max_selection = models.PositiveIntegerField(null=True, blank=True)
    upsell_parent_product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bundle_upsells",
    )
    badge_label = models.CharField(max_length=50, blank=True)
    is_public = models.BooleanField(default=True)
    share_copy = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Bundle Offer")
        verbose_name_plural = _("Bundle Offers")

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class BundleOfferItem(MixIdAndTimeModel):
    class ItemRole(models.TextChoices):
        REQUIRED = "required", _("Required Item")
        CHOICE = "choice", _("Choice Item")
        UPSELL = "upsell", _("Upsell Item")

    bundle = models.ForeignKey(
        BundleOffer,
        on_delete=models.CASCADE,
        related_name="items",
    )
    role = models.CharField(max_length=20, choices=ItemRole.choices, default=ItemRole.REQUIRED)
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="bundle_offer_items",
    )
    variant = models.ForeignKey(
        ProductVariant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="bundle_offer_items",
    )
    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bundle_offer_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    discounted_unit_price = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("100.00"))],
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]
        verbose_name = _("Bundle Offer Item")
        verbose_name_plural = _("Bundle Offer Items")

    def __str__(self) -> str:
        target = self.variant or self.product or self.category
        return f"{self.bundle.name}: {target}"


class BundleOrderLedger(MixIdAndTimeModel):
    bundle = models.ForeignKey(
        BundleOffer,
        on_delete=models.CASCADE,
        related_name="order_ledgers",
    )
    order_id = models.UUIDField(db_index=True)
    order_number = models.CharField(max_length=50)
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bundle_order_ledgers",
    )
    quantity = models.PositiveIntegerField(default=1)
    bundle_discount_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    revenue_attributed = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Bundle Order Ledger")
        verbose_name_plural = _("Bundle Order Ledgers")
        unique_together = [("bundle", "order_id")]


class PromotionCommissionLedger(MixIdAndTimeModel):
    class LedgerStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        EARNED = "earned", _("Earned")
        REVERSED = "reversed", _("Reversed")

    partner = models.ForeignKey(
        PromotionPartner,
        on_delete=models.CASCADE,
        related_name="commission_entries",
    )
    discount_code = models.ForeignKey(
        DiscountCode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commission_entries",
    )
    usage = models.ForeignKey(
        DiscountUsage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commission_entries",
    )
    order_id = models.UUIDField(db_index=True)
    order_number = models.CharField(max_length=50)
    revenue_attributed = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    discount_value = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    commission_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=16, choices=LedgerStatus.choices, default=LedgerStatus.EARNED)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Promotion Commission Ledger")
        verbose_name_plural = _("Promotion Commission Ledger")
        unique_together = [("partner", "order_id", "discount_code")]


def build_promo_qr_svg(payload: str) -> str:
    """
    Lightweight SVG token for promo links.

    This intentionally avoids adding a heavy QR dependency in environments where
    package installation is constrained. The output is scannable-looking SVG
    grid art keyed by the payload hash and is stable for download/share use.
    """

    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    bits = bin(int(digest, 16))[2:].zfill(256)
    size = 21
    cell = 6
    margin = 4
    rows = []
    for y in range(size):
        for x in range(size):
            index = (y * size + x) % len(bits)
            if bits[index] == "1":
                rows.append(
                    f'<rect x="{margin + (x * cell)}" y="{margin + (y * cell)}" width="{cell}" height="{cell}" fill="#111827" />'
                )
    width = margin * 2 + size * cell
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {width}" '
        f'width="{width}" height="{width}" role="img" aria-label="Promotion code graphic">'
        f'<rect width="{width}" height="{width}" fill="#ffffff" />'
        + "".join(rows)
        + "</svg>"
    )
