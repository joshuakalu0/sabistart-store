"""
pricing/models_part2.py — Discount Codes, Automatic Discounts, Advanced Promotions
Sections 3, 4, 5
"""

import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from dashboard.settings.models import MixIdAndTimeModel, ActivatableModel, IduuidModel, AuditModel
from public.userauth.models import Customer, CustomerGroup
from public.category.models import Category
from public.product.models import Product, ProductVariant


# ─────────────────────────────────────────────────────────────
# SECTION 3 — DISCOUNT CODES (Coupons)
# ─────────────────────────────────────────────────────────────

class DiscountCode(AuditModel, ActivatableModel):
    """
    Customer-entered coupon codes applied at checkout.

    Supported value types:
      PERCENTAGE      → 20% off the cart (or eligible items)
      FIXED_AMOUNT    → $15 off the order
      FREE_SHIPPING   → Removes shipping cost
      BUY_X_GET_Y     → Triggers a BuyXGetYPromotion when code is entered
      FREE_ITEM       → Adds a specific free product to the cart

    Scope controls what the discount applies to:
      ORDER           → Entire order subtotal
      SPECIFIC_ITEMS  → Only products/variants/collections in DiscountRule
      SHIPPING        → Only the shipping line

    Stacking:
      Tenants configure whether codes can stack with price lists,
      automatic discounts, or other codes. The `is_combinable`
      and `combines_with` fields control this.
    """

    class ValueType(models.TextChoices):
        PERCENTAGE = "percentage", _("Percentage Off (e.g. 20%)")
        FIXED_AMOUNT = "fixed_amount", _("Fixed Amount Off (e.g. $15)")
        FREE_SHIPPING = "free_shipping", _("Free Shipping")
        BUY_X_GET_Y = "buy_x_get_y", _("Buy X Get Y (triggers a promotion)")
        FREE_ITEM = "free_item", _("Free Item")

    class DiscountScope(models.TextChoices):
        ORDER = "order", _("Entire Order")
        SPECIFIC_ITEMS = "specific_items", _("Specific Products / Collections")
        SHIPPING = "shipping", _("Shipping Only")

    class AllocationMethod(models.TextChoices):
        ACROSS = "across", _("Spread Proportionally Across Eligible Items")
        EACH = "each", _("Applied to Each Eligible Item Independently")
        ONE = "one", _("Applied Once to the Highest-Priced Eligible Item")

    # ── Code ──
    code = models.CharField(
        _("Discount Code"),
        max_length=100,
        unique=True,
        db_index=True,
        help_text=_(
            "The code customers enter at checkout. "
            "Stored uppercase. e.g. SUMMER20, VIP50, FREESHIP"
        ),
    )
    title = models.CharField(
        _("Title"),
        max_length=255,
        help_text=_("Internal name for this discount. Not shown to customers."),
    )
    description = models.TextField(
        _("Customer-Facing Description"),
        blank=True,
        help_text=_("Optional description shown in cart when code is applied."),
    )

    # ── Value ──
    value_type = models.CharField(
        _("Value Type"),
        max_length=20,
        choices=ValueType.choices,
        default=ValueType.PERCENTAGE,
    )
    percentage_value = models.DecimalField(
        _("Percentage (%)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(
            Decimal("0.01")), MaxValueValidator(Decimal("100.00"))],
        help_text=_("Required for PERCENTAGE type. e.g. 20.00 for 20% off."),
    )
    fixed_amount = models.DecimalField(
        _("Fixed Amount"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=_("Required for FIXED_AMOUNT type. In store base currency."),
    )
    currency = models.CharField(
        _("Currency"),
        max_length=3,
        default="USD",
        help_text=_("Currency for fixed_amount discounts."),
    )
    free_item_variant = models.ForeignKey(
        ProductVariant,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="free_item_discounts",
        verbose_name=_("Free Item Variant"),
        help_text=_(
            "For FREE_ITEM type: the variant added to the cart for free."),
    )
    buy_x_get_y_promotion = models.ForeignKey(
        "BuyXGetYPromotion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trigger_codes",
        verbose_name=_("Buy X Get Y Promotion"),
        help_text=_(
            "For BUY_X_GET_Y type: the promotion triggered by this code."),
    )

    # ── Scope ──
    scope = models.CharField(
        _("Discount Scope"),
        max_length=20,
        choices=DiscountScope.choices,
        default=DiscountScope.ORDER,
    )
    allocation_method = models.CharField(
        _("Allocation Method"),
        max_length=10,
        choices=AllocationMethod.choices,
        default=AllocationMethod.ACROSS,
        help_text=_(
            "How the discount value is spread across eligible line items. "
            "Affects per-line refund and return calculations."
        ),
    )

    # ── Usage limits ──
    usage_limit = models.PositiveIntegerField(
        _("Total Usage Limit"),
        null=True,
        blank=True,
        help_text=_(
            "Maximum total number of times this code can be redeemed across all customers. "
            "Null = unlimited."
        ),
    )
    usage_limit_per_customer = models.PositiveIntegerField(
        _("Per-Customer Usage Limit"),
        null=True,
        blank=True,
        default=1,
        help_text=_(
            "How many times one customer can use this code. Null = unlimited."),
    )
    usage_count = models.PositiveIntegerField(
        _("Total Uses"),
        default=0,
        help_text=_(
            "Auto-incremented. Never edit directly — use DiscountUsage records."),
    )

    # ── Conditions ──
    minimum_order_amount = models.DecimalField(
        _("Minimum Order Amount"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_(
            "Cart subtotal must be at least this amount to apply the code."),
    )
    minimum_quantity = models.PositiveIntegerField(
        _("Minimum Item Quantity"),
        null=True,
        blank=True,
        help_text=_("Cart must contain at least this many eligible items."),
    )
    requires_first_order = models.BooleanField(
        _("First Order Only"),
        default=False,
        help_text=_("Code can only be used by customers with no prior orders."),
    )
    customer_eligibility = models.CharField(
        _("Customer Eligibility"),
        max_length=20,
        choices=[
            ("all", _("All Customers")),
            ("group", _("Specific Customer Groups")),
            ("individual", _("Specific Customers")),
        ],
        default="all",
    )

    # ── Stacking ──
    is_combinable_with_price_lists = models.BooleanField(
        _("Combinable with Price Lists"),
        default=False,
    )
    is_combinable_with_automatic_discounts = models.BooleanField(
        _("Combinable with Automatic Discounts"),
        default=False,
    )
    is_combinable_with_other_codes = models.BooleanField(
        _("Combinable with Other Codes"),
        default=False,
        help_text=_("Rarely True — allows stacking multiple coupon codes."),
    )

    # ── Max discount cap ──
    max_discount_amount = models.DecimalField(
        _("Maximum Discount Amount Cap"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=_(
            "For PERCENTAGE type: caps the discount at this amount. "
            "e.g. 20% off but no more than $50."
        ),
    )

    # ── Metadata ──
    internal_note = models.TextField(_("Internal Note"), blank=True)
    last_used_at = models.DateTimeField(
        _("Last Used At"), null=True, blank=True)
    attributed_partner = models.ForeignKey(
        "pricing.PromotionPartner",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="discount_codes",
        verbose_name=_("Attributed Partner"),
        help_text=_("Optional influencer, affiliate, or campaign source credited for this code."),
    )
    total_stack_cap_amount = models.DecimalField(
        _("Total Stack Cap Amount"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=_("Maximum combined savings allowed when this code stacks with other promotions."),
    )
    eligible_countries = models.JSONField(
        _("Eligible Countries"),
        default=list,
        blank=True,
        help_text=_("Optional ISO country codes that can use this code."),
    )
    eligible_states = models.JSONField(
        _("Eligible States"),
        default=list,
        blank=True,
        help_text=_("Optional state or region filters for this code."),
    )
    eligible_cities = models.JSONField(
        _("Eligible Cities"),
        default=list,
        blank=True,
        help_text=_("Optional city filters for this code."),
    )

    class Meta:
        verbose_name = _("Discount Code")
        verbose_name_plural = _("Discount Codes")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["is_active", "starts_at", "ends_at"]),
            models.Index(fields=["value_type", "scope"]),
            models.Index(fields=["usage_count"]),
        ]

    def __str__(self):
        return f"{self.code} — {self.title}"

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    @property
    def is_usage_limit_reached(self) -> bool:
        if self.usage_limit is None:
            return False
        return self.usage_count >= self.usage_limit

    @property
    def remaining_uses(self) -> int | None:
        if self.usage_limit is None:
            return None
        return max(0, self.usage_limit - self.usage_count)

    def calculate_discount_amount(self, cart_subtotal: Decimal) -> Decimal:
        """
        Calculate the money amount discounted given a cart subtotal.
        Does NOT check eligibility — assumes it has already been validated.
        """
        TWO_PLACES = Decimal("0.01")

        if self.value_type == self.ValueType.PERCENTAGE:
            amount = (cart_subtotal * self.percentage_value / Decimal("100")).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
            if self.max_discount_amount:
                amount = min(amount, self.max_discount_amount)
            return amount

        elif self.value_type == self.ValueType.FIXED_AMOUNT:
            return min(self.fixed_amount or Decimal("0"), cart_subtotal)

        elif self.value_type in (self.ValueType.FREE_SHIPPING, self.ValueType.FREE_ITEM):
            return Decimal("0.00")  # handled separately at cart level

        return Decimal("0.00")

    @transaction.atomic
    def increment_usage(self):
        """Thread-safe usage counter increment."""
        DiscountCode.objects.filter(pk=self.pk).update(
            usage_count=models.F("usage_count") + 1,
            last_used_at=timezone.now(),
        )


class DiscountRule(MixIdAndTimeModel):
    """
    Eligibility conditions that restrict a DiscountCode to specific
    products, variants, collections, or customer groups.

    Multiple rules on one code use AND logic by default (all must match).
    Set match_condition = 'any' for OR logic.

    Rule types:
      PRODUCT         → Code applies only to specific products
      VARIANT         → Code applies only to specific variants
      COLLECTION      → Code applies to all products in a collection
      CATEGORY        → Code applies to all products in a category
      CUSTOMER_GROUP  → Code is only usable by customers in a group
      SPECIFIC_CUSTOMER → Code is only usable by one specific customer
      MINIMUM_AMOUNT  → Cart subtotal must exceed a value (same as DiscountCode.minimum_order_amount but per-rule)
      MINIMUM_QUANTITY → Cart must have minimum item count
    """

    class RuleType(models.TextChoices):
        PRODUCT = "product", _("Specific Product(s)")
        VARIANT = "variant", _("Specific Variant(s)")
        COLLECTION = "collection", _("Product Collection(s)")
        CATEGORY = "category", _("Product Category")
        CUSTOMER_GROUP = "customer_group", _("Customer Group")
        SPECIFIC_CUSTOMER = "specific_customer", _("Specific Customer")
        MINIMUM_AMOUNT = "minimum_amount", _("Minimum Order Amount")
        MINIMUM_QUANTITY = "minimum_quantity", _("Minimum Item Quantity")
        EXCLUDE_SALE_ITEMS = "exclude_sale_items", _(
            "Exclude Sale/Discounted Items")
        EXCLUDE_SPECIFIC_PRODUCTS = "exclude_products", _(
            "Exclude Specific Products")

    class MatchCondition(models.TextChoices):
        ALL = "all", _("All rules must match (AND)")
        ANY = "any", _("Any rule must match (OR)")

    discount_code = models.ForeignKey(
        DiscountCode,
        on_delete=models.CASCADE,
        related_name="rules",
        verbose_name=_("Discount Code"),
    )
    rule_type = models.CharField(
        _("Rule Type"),
        max_length=30,
        choices=RuleType.choices,
    )
    match_condition = models.CharField(
        _("Match Condition"),
        max_length=5,
        choices=MatchCondition.choices,
        default=MatchCondition.ALL,
        help_text=_(
            "Whether ALL or ANY rules must match for the code to apply."),
    )

    # ── Targets (only one should be set per rule) ──
    product = models.ForeignKey(
        Product,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="discount_rules",
    )
    variant = models.ForeignKey(
        ProductVariant,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="discount_rules",
    )
    # collection = models.ForeignKey(
    #     "public.product.Collection",
    #     null=True, blank=True,
    #     on_delete=models.CASCADE,
    #     related_name="discount_rules",
    # )
    category = models.ForeignKey(
        Category,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="discount_rules",
    )
    customer_group = models.ForeignKey(
        CustomerGroup,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="discount_rules",
    )
    customer = models.ForeignKey(
        Customer,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="discount_rules",
    )
    amount_threshold = models.DecimalField(
        _("Amount Threshold"),
        max_digits=14,
        decimal_places=2,
        null=True, blank=True,
        help_text=_("For MINIMUM_AMOUNT rule: the minimum cart subtotal."),
    )
    quantity_threshold = models.PositiveIntegerField(
        _("Quantity Threshold"),
        null=True, blank=True,
        help_text=_("For MINIMUM_QUANTITY rule: the minimum item count."),
    )

    class Meta:
        verbose_name = _("Discount Rule")
        verbose_name_plural = _("Discount Rules")
        ordering = ["discount_code", "rule_type"]
        indexes = [
            models.Index(fields=["discount_code", "rule_type"]),
        ]

    def __str__(self):
        return f"{self.discount_code.code} — Rule: {self.rule_type}"


class DiscountUsage(IduuidModel):
    """
    IMMUTABLE append-only ledger recording every redemption of a DiscountCode.
    Never UPDATE or DELETE rows. Only INSERT.

    One row per order redemption. Used for:
      - Per-customer usage limit enforcement
      - Usage analytics and reporting
      - Fraud detection (same customer, multiple accounts)
      - Reconciliation with DiscountCode.usage_count
    """

    discount_code = models.ForeignKey(
        DiscountCode,
        on_delete=models.CASCADE,
        related_name="usages",
        verbose_name=_("Discount Code"),
    )
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="discount_usages",
        verbose_name=_("Customer"),
        help_text=_("Null for guest checkouts."),
    )

    # ── FK-less order reference ──
    order_id = models.UUIDField(
        _("Order ID"),
        db_index=True,
        help_text=_(
            "FK-less ref to orders.Order. Avoids cross-app circular FK."),
    )
    order_number = models.CharField(
        _("Order Number"),
        max_length=50,
        help_text=_("Denormalized for display without joining orders table."),
    )

    # ── Amounts ──
    discount_amount = models.DecimalField(
        _("Discount Amount Applied"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("Actual money amount discounted on this order."),
    )
    order_subtotal_at_use = models.DecimalField(
        _("Order Subtotal at Time of Use"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_("Snapshot of cart subtotal when code was applied."),
    )
    currency = models.CharField(_("Currency"), max_length=3, default="USD")

    # ── Context ──
    customer_email = models.EmailField(
        _("Customer Email"),
        blank=True,
        help_text=_("Denormalized for reporting, especially for guest orders."),
    )
    ip_address = models.GenericIPAddressField(
        _("IP Address"),
        null=True,
        blank=True,
        help_text=_(
            "Used for fraud detection (same IP, multiple accounts, same code)."),
    )
    user_agent = models.TextField(_("User Agent"), blank=True)

    is_reversed = models.BooleanField(
        _("Is Reversed"),
        default=False,
        db_index=True,
        help_text=_(
            "Marks redemptions that were later voided or cancelled so they are "
            "excluded from live validation and analytics."
        ),
    )
    reversed_at = models.DateTimeField(
        _("Reversed At"),
        null=True,
        blank=True,
    )
    reversal_reason = models.CharField(
        _("Reversal Reason"),
        max_length=255,
        blank=True,
    )

    # ── Immutable timestamp ──
    used_at = models.DateTimeField(
        _("Used At"),
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        verbose_name = _("Discount Usage")
        verbose_name_plural = _("Discount Usages")
        ordering = ["-used_at"]
        indexes = [
            models.Index(fields=["discount_code", "customer"]),
            models.Index(fields=["discount_code", "-used_at"]),
            models.Index(fields=["order_id"]),
            models.Index(fields=["customer_email"]),
            models.Index(fields=["ip_address"]),
            models.Index(fields=["discount_code", "is_reversed", "-used_at"]),
        ]

    def __str__(self):
        return (
            f"{self.discount_code.code} used on Order {self.order_number} "
            f"(−{self.discount_amount})"
        )


# ─────────────────────────────────────────────────────────────
# SECTION 4 — AUTOMATIC DISCOUNTS
# ─────────────────────────────────────────────────────────────

class AutomaticDiscount(AuditModel, ActivatableModel):
    """
    Rule-based discounts that apply automatically without a code.
    Evaluated at cart/checkout time against all active automatic discounts.

    Examples:
      "10% off everything in the Summer Collection"
      "Free shipping on orders over $75"
      "20% off for VIP customers on Electronics"
      "Buy 3+ units of any T-shirt and get 15% off"
      "$10 off your second order"

    A customer can have at most one automatic discount applied at a time
    (unless allow_stacking=True). The one with the highest `priority` wins.

    Conditions and Benefits are in separate models for clean separation
    and independent extensibility.
    """

    class DiscountMethod(models.TextChoices):
        PERCENTAGE = "percentage", _("Percentage Off")
        FIXED_AMOUNT = "fixed_amount", _("Fixed Amount Off")
        FREE_SHIPPING = "free_shipping", _("Free Shipping")
        BUY_X_GET_Y = "buy_x_get_y", _("Buy X Get Y (linked promotion)")
        FREE_ITEM = "free_item", _("Free Item Added")
        TIERED = "tiered", _("Tiered (amount unlocks bigger discount)")

    # ── Identity ──
    title = models.CharField(
        _("Title"),
        max_length=255,
        help_text=_("Internal name. e.g. 'Summer Collection 10% Off'"),
    )
    customer_facing_title = models.CharField(
        _("Customer-Facing Title"),
        max_length=255,
        blank=True,
        help_text=_(
            "Shown in cart when discount is applied. Defaults to title if blank."),
    )
    description = models.TextField(_("Internal Description"), blank=True)

    # ── Discount value ──
    discount_method = models.CharField(
        _("Discount Method"),
        max_length=20,
        choices=DiscountMethod.choices,
        default=DiscountMethod.PERCENTAGE,
    )
    percentage_value = models.DecimalField(
        _("Percentage (%)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(
            Decimal("0.01")), MaxValueValidator(Decimal("100.00"))],
    )
    fixed_amount = models.DecimalField(
        _("Fixed Amount"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    max_discount_amount = models.DecimalField(
        _("Maximum Discount Cap"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    buy_x_get_y_promotion = models.ForeignKey(
        "BuyXGetYPromotion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="automatic_triggers",
    )
    free_item_variant = models.ForeignKey(
        ProductVariant,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="automatic_free_item_discounts",
    )
    free_item_quantity = models.PositiveIntegerField(
        _("Free Item Quantity"),
        default=1,
    )

    # ── Stacking ──
    allow_stacking = models.BooleanField(
        _("Allow Stacking with Other Automatic Discounts"),
        default=False,
    )
    is_combinable_with_codes = models.BooleanField(
        _("Combinable with Discount Codes"),
        default=False,
    )
    priority = models.PositiveIntegerField(
        _("Priority"),
        default=0,
        help_text=_(
            "Higher number wins when multiple automatic discounts are eligible."),
    )

    # ── Usage tracking ──
    usage_count = models.PositiveIntegerField(
        _("Total Uses"),
        default=0,
        editable=False,
    )
    usage_limit = models.PositiveIntegerField(
        _("Total Usage Limit"),
        null=True,
        blank=True,
    )
    usage_limit_per_customer = models.PositiveIntegerField(
        _("Per-Customer Usage Limit"),
        null=True,
        blank=True,
    )

    internal_note = models.TextField(_("Internal Note"), blank=True)
    attributed_partner = models.ForeignKey(
        "pricing.PromotionPartner",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="automatic_discounts",
        verbose_name=_("Attributed Partner"),
    )
    total_stack_cap_amount = models.DecimalField(
        _("Total Stack Cap Amount"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=_("Maximum combined savings allowed when this automatic discount stacks."),
    )
    eligible_countries = models.JSONField(
        _("Eligible Countries"),
        default=list,
        blank=True,
    )
    eligible_states = models.JSONField(
        _("Eligible States"),
        default=list,
        blank=True,
    )
    eligible_cities = models.JSONField(
        _("Eligible Cities"),
        default=list,
        blank=True,
    )

    class Meta:
        verbose_name = _("Automatic Discount")
        verbose_name_plural = _("Automatic Discounts")
        ordering = ["-priority", "-starts_at"]
        indexes = [
            models.Index(fields=["is_active", "starts_at", "ends_at"]),
            models.Index(fields=["priority", "is_active"]),
        ]

    def __str__(self):
        return self.title

    @transaction.atomic
    def increment_usage(self):
        AutomaticDiscount.objects.filter(pk=self.pk).update(
            usage_count=models.F("usage_count") + 1
        )


class AutomaticDiscountCondition(MixIdAndTimeModel):
    """
    A single prerequisite condition that must be satisfied for the
    AutomaticDiscount to activate on a cart.

    Multiple conditions on one discount use AND logic by default.

    Condition types:
      MINIMUM_SUBTOTAL     → cart subtotal ≥ amount
      MINIMUM_QUANTITY     → cart item count ≥ n
      CUSTOMER_GROUP       → customer belongs to group
      PRODUCT_IN_CART      → specific product must be in cart
      COLLECTION_IN_CART   → product from collection must be in cart
      FIRST_ORDER          → customer has no prior orders
      CUSTOMER_TAG         → customer has a specific tag
      ORDER_COUNT          → customer has at least N prior orders
    """

    class ConditionType(models.TextChoices):
        MINIMUM_SUBTOTAL = "minimum_subtotal", _("Minimum Cart Subtotal")
        MINIMUM_QUANTITY = "minimum_quantity", _("Minimum Item Quantity")
        CUSTOMER_GROUP = "customer_group", _("Customer Belongs to Group")
        PRODUCT_IN_CART = "product_in_cart", _("Specific Product in Cart")
        COLLECTION_IN_CART = "collection_in_cart", _(
            "Product from Collection in Cart")
        FIRST_ORDER = "first_order", _("Customer's First Order")
        CUSTOMER_TAG = "customer_tag", _("Customer Has Tag")
        ORDER_COUNT_MIN = "order_count_min", _("Customer Has Minimum N Orders")
        ORDER_COUNT_MAX = "order_count_max", _("Customer Has At Most N Orders")
        CART_HAS_ITEM_TAG = "cart_has_item_tag", _(
            "Cart Contains Item with Tag")

    automatic_discount = models.ForeignKey(
        AutomaticDiscount,
        on_delete=models.CASCADE,
        related_name="conditions",
        verbose_name=_("Automatic Discount"),
    )
    condition_type = models.CharField(
        _("Condition Type"),
        max_length=30,
        choices=ConditionType.choices,
    )

    # ── Condition values ──
    amount_threshold = models.DecimalField(
        _("Amount Threshold"),
        max_digits=14,
        decimal_places=2,
        null=True, blank=True,
    )
    quantity_threshold = models.PositiveIntegerField(
        _("Quantity Threshold"),
        null=True, blank=True,
    )
    integer_threshold = models.PositiveIntegerField(
        _("Integer Threshold (order count, etc.)"),
        null=True, blank=True,
    )
    customer_group = models.ForeignKey(
        CustomerGroup,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="automatic_discount_conditions",
    )
    product = models.ForeignKey(
        Product,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="automatic_discount_conditions",
    )
    # collection = models.ForeignKey(
    #     "public.product.Collection",
    #     null=True, blank=True,
    #     on_delete=models.CASCADE,
    #     related_name="automatic_discount_conditions",
    # )
    string_value = models.CharField(
        _("String Value (tag, etc.)"),
        max_length=255,
        blank=True,
        help_text=_("For CUSTOMER_TAG, CART_HAS_ITEM_TAG condition types."),
    )

    class Meta:
        verbose_name = _("Automatic Discount Condition")
        verbose_name_plural = _("Automatic Discount Conditions")
        ordering = ["automatic_discount", "condition_type"]

    def __str__(self):
        return f"{self.automatic_discount.title} — Condition: {self.condition_type}"


class AutomaticDiscountBenefit(MixIdAndTimeModel):
    """
    The benefit (what the customer receives) from an AutomaticDiscount
    when all its conditions are met.

    For simple discounts, the benefit is just the discount value itself
    (already on AutomaticDiscount). This model handles complex benefits:
      - Specific products/collections receive different discount rates
      - Different tiers of the TIERED discount method
      - Combinations of discount + free item
    """

    class BenefitScope(models.TextChoices):
        ALL_ELIGIBLE = "all_eligible", _("All Eligible Items in Cart")
        SPECIFIC_PRODUCT = "specific_product", _("Specific Product Only")
        SPECIFIC_COLLECTION = "specific_collection", _(
            "Specific Collection Only")
        CHEAPEST_ITEM = "cheapest_item", _("Cheapest Item in Cart")
        MOST_EXPENSIVE_ITEM = "most_expensive", _(
            "Most Expensive Item in Cart")
        SHIPPING = "shipping", _("Shipping Line Only")

    automatic_discount = models.ForeignKey(
        AutomaticDiscount,
        on_delete=models.CASCADE,
        related_name="benefits",
        verbose_name=_("Automatic Discount"),
    )
    benefit_scope = models.CharField(
        _("Benefit Scope"),
        max_length=25,
        choices=BenefitScope.choices,
        default=BenefitScope.ALL_ELIGIBLE,
    )
    percentage_value = models.DecimalField(
        _("Percentage (%)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(
            Decimal("0.01")), MaxValueValidator(Decimal("100.00"))],
    )
    fixed_amount = models.DecimalField(
        _("Fixed Amount"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # ── Tiered thresholds ──
    tier_min_subtotal = models.DecimalField(
        _("Tier Minimum Subtotal"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "For TIERED discounts: cart must reach this to unlock this tier."),
    )
    tier_order = models.PositiveSmallIntegerField(
        _("Tier Order"),
        default=0,
        help_text=_("Lower = activated first. Higher tiers override lower."),
    )

    # ── Target ──
    product = models.ForeignKey(
        Product,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="automatic_discount_benefits",
    )
    # collection = models.ForeignKey(
    #     "public.product.Collection",
    #     null=True, blank=True,
    #     on_delete=models.CASCADE,
    #     related_name="automatic_discount_benefits",
    # )

    class Meta:
        verbose_name = _("Automatic Discount Benefit")
        verbose_name_plural = _("Automatic Discount Benefits")
        ordering = ["automatic_discount", "tier_order"]

    def __str__(self):
        return f"{self.automatic_discount.title} — Benefit ({self.benefit_scope})"


# ─────────────────────────────────────────────────────────────
# SECTION 5 — ADVANCED PROMOTIONS
# ─────────────────────────────────────────────────────────────

class BuyXGetYPromotion(AuditModel, ActivatableModel):
    """
    Buy X items → Get Y items free or discounted.

    Examples:
      "Buy 2 shirts, get 1 free"           → buy_quantity=2, get_quantity=1, get_discount=100%
      "Buy $100 of shoes, get 50% off bags" → uses amounts instead of quantities
      "Buy 3 face masks, get 3 for 50% off" → buy_quantity=3, get_quantity=3, get_discount=50%
      "Spend $150+, get a free tote bag"    → minimum_spend=150, get specific free item

    Buy items and Get items can be the same or different products/collections.

    Trigger:
      - Linked to DiscountCode.buy_x_get_y_promotion → triggered by code
      - Linked to AutomaticDiscount.buy_x_get_y_promotion → triggered automatically
    """

    class BuyType(models.TextChoices):
        QUANTITY = "quantity", _("Buy X Units")
        AMOUNT = "amount", _("Spend $X Amount")
        COLLECTION = "collection", _("Buy from Collection")

    class GetType(models.TextChoices):
        SAME_ITEMS = "same_items", _("Get Same Items (from buy set)")
        DIFFERENT_ITEMS = "different_items", _(
            "Get Different Items (from get set)")
        SPECIFIC_VARIANT = "specific_variant", _("Get a Specific Variant")

    title = models.CharField(_("Promotion Title"), max_length=255)
    description = models.TextField(_("Description"), blank=True)

    # ── Buy side ──
    buy_type = models.CharField(
        _("Buy Type"),
        max_length=15,
        choices=BuyType.choices,
        default=BuyType.QUANTITY,
    )
    buy_quantity = models.PositiveIntegerField(
        _("Buy Quantity"),
        null=True, blank=True,
        help_text=_("Number of units to buy to trigger the promotion."),
    )
    buy_minimum_amount = models.DecimalField(
        _("Minimum Spend Amount"),
        max_digits=14,
        decimal_places=2,
        null=True, blank=True,
        help_text=_("For AMOUNT type: spend at least this much to trigger."),
    )

    # ── Get side ──
    get_type = models.CharField(
        _("Get Type"),
        max_length=20,
        choices=GetType.choices,
        default=GetType.SAME_ITEMS,
    )
    get_quantity = models.PositiveIntegerField(
        _("Get Quantity"),
        default=1,
        help_text=_("Number of free/discounted items the customer receives."),
    )
    get_discount_percentage = models.DecimalField(
        _("Get Item Discount (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("100.00"),
        validators=[MinValueValidator(
            Decimal("0.01")), MaxValueValidator(Decimal("100.00"))],
        help_text=_("100 = free. 50 = half price. 0 = no discount."),
    )
    get_specific_variant = models.ForeignKey(
        ProductVariant,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="bxgy_get_promotions",
        verbose_name=_("Free/Discounted Variant"),
        help_text=_("For SPECIFIC_VARIANT get type."),
    )

    # ── Application ──
    apply_to = models.CharField(
        _("Apply to"),
        max_length=20,
        choices=[
            ("cheapest", _("Cheapest Eligible Item(s)")),
            ("most_expensive", _("Most Expensive Eligible Item(s)")),
            ("first_in_cart", _("First Added to Cart")),
        ],
        default="cheapest",
        help_text=_(
            "Which items receive the discount when the condition is met."),
    )
    max_applications_per_order = models.PositiveIntegerField(
        _("Max Applications Per Order"),
        default=1,
        help_text=_(
            "How many times this promotion can apply within one order. "
            "e.g. 'Buy 2 get 1 free' with max=3 means buy 6, get 3 free."
        ),
    )
    one_per_customer = models.BooleanField(
        _("One Per Customer"),
        default=False,
    )

    # ── Usage ──
    usage_count = models.PositiveIntegerField(
        _("Total Uses"), default=0, editable=False)
    usage_limit = models.PositiveIntegerField(
        _("Usage Limit"), null=True, blank=True)

    # ── Metadata ──

    internal_note = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Buy X Get Y Promotion")
        verbose_name_plural = _("Buy X Get Y Promotions")
        ordering = ["-starts_at"]
        indexes = [
            models.Index(fields=["is_active", "starts_at", "ends_at"]),
        ]

    def __str__(self):
        return self.title


class BuyXGetYItem(MixIdAndTimeModel):
    """
    Defines the eligible products for the Buy side or Get side
    of a BuyXGetYPromotion.

    Each BuyXGetYPromotion can have multiple BuyXGetYItems on each side.
    When multiple items are listed on the Buy side, the customer can
    buy any combination of them to trigger the promotion.
    """

    class Side(models.TextChoices):
        BUY = "buy", _("Buy Side (trigger items)")
        GET = "get", _("Get Side (discounted items)")

    promotion = models.ForeignKey(
        BuyXGetYPromotion,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Promotion"),
    )
    side = models.CharField(
        _("Side"),
        max_length=5,
        choices=Side.choices,
        help_text=_("Whether this item is on the Buy side or Get side."),
    )

    # ── Target (one of these should be set) ──
    product = models.ForeignKey(
        Product,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="bxgy_items",
    )
    variant = models.ForeignKey(
        ProductVariant,
        null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="bxgy_items",
    )
    # collection = models.ForeignKey(
    #     "public.product.Collection",
    #     null=True, blank=True,
    #     on_delete=models.CASCADE,
    #     related_name="bxgy_items",
    # )
    category = models.ForeignKey(
        Category,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="bxgy_items",
    )
    minimum_quantity = models.PositiveIntegerField(
        _("Minimum Quantity from This Target"),
        default=1,
        help_text=_("How many of this item/collection must be in the cart."),
    )

    class Meta:
        verbose_name = _("Buy X Get Y Item")
        verbose_name_plural = _("Buy X Get Y Items")
        ordering = ["promotion", "side"]

    def __str__(self):
        target = self.variant or self.product or self.category
        return f"{self.promotion.title} — {self.side}: {target}"


class VolumePricingTier(MixIdAndTimeModel):
    """
    Quantity-break / volume pricing for a specific ProductVariant.
    The more units ordered, the cheaper the per-unit price.

    Example:
      1–4 units  → $25.00 each
      5–9 units  → $22.00 each
      10–24 units→ $19.00 each
      25+ units  → $16.00 each

    Volume pricing is evaluated AFTER price lists and BEFORE discount codes.
    If a customer's price list price is already lower, the lower of the
    two is used (controlled by `applies_on_top_of_price_lists`).
    """

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="volume_tiers",
        verbose_name=_("Product Variant"),
    )
    customer_group = models.ForeignKey(
        CustomerGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="volume_tiers",
        verbose_name=_("Customer Group"),
        help_text=_(
            "If set, this tier only applies to customers in this group. "
            "Null = applies to all customers."
        ),
    )

    # ── Quantity range ──
    min_quantity = models.PositiveIntegerField(
        _("Minimum Quantity"),
        validators=[MinValueValidator(1)],
        help_text=_("This tier activates when order quantity ≥ min_quantity."),
    )
    max_quantity = models.PositiveIntegerField(
        _("Maximum Quantity"),
        null=True,
        blank=True,
        help_text=_(
            "This tier deactivates when order quantity > max_quantity. Null = no upper limit."),
    )

    # ── Pricing ──
    price_type = models.CharField(
        _("Price Type"),
        max_length=15,
        choices=[
            ("fixed", _("Fixed Price Per Unit")),
            ("percentage", _("% Off Base Price")),
            ("fixed_discount", _("Fixed Amount Off Base Price")),
        ],
        default="fixed",
    )
    price = models.DecimalField(
        _("Fixed Price Per Unit"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    discount_percentage = models.DecimalField(
        _("Discount Percentage"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(
            Decimal("0.01")), MaxValueValidator(Decimal("100.00"))],
    )
    fixed_discount = models.DecimalField(
        _("Fixed Discount Per Unit"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    # ── Flags ──
    is_active = models.BooleanField(_("Active"), default=True)
    applies_on_top_of_price_lists = models.BooleanField(
        _("Applies on Top of Price Lists"),
        default=False,
        help_text=_(
            "If True, this tier is combined with price list pricing. "
            "If False, only the lower price wins."
        ),
    )
    show_savings_label = models.BooleanField(
        _("Show Savings Label"),
        default=True,
        help_text=_(
            "Display 'You save X% by buying in bulk' label on the product page."),
    )

    class Meta:
        verbose_name = _("Volume Pricing Tier")
        verbose_name_plural = _("Volume Pricing Tiers")
        ordering = ["variant", "min_quantity"]
        unique_together = [("variant", "customer_group", "min_quantity")]
        indexes = [
            models.Index(fields=["variant", "is_active"]),
            models.Index(fields=["customer_group"]),
        ]

    def __str__(self):
        max_str = str(self.max_quantity) if self.max_quantity else "∞"
        return (
            f"{self.variant} — Volume {self.min_quantity}–{max_str} "
            f"@ {self.price or f'{self.discount_percentage}% off'}"
        )

    def compute_price(self, base_price: Decimal) -> Decimal:
        """Compute the effective per-unit price for this tier."""
        TWO = Decimal("0.01")
        if self.price_type == "fixed" and self.price is not None:
            return self.price
        elif self.price_type == "percentage" and self.discount_percentage:
            factor = Decimal("1") - (self.discount_percentage / Decimal("100"))
            return (base_price * factor).quantize(TWO, rounding=ROUND_HALF_UP)
        elif self.price_type == "fixed_discount" and self.fixed_discount:
            return max(Decimal("0.00"), base_price - self.fixed_discount)
        return base_price


class FlashSale(MixIdAndTimeModel, ActivatableModel):
    """
    Time-limited sale with hard start/end times, optional countdown timer,
    and per-product quantity limits.

    Flash sales have their own priority system — they override regular
    prices and price lists during their active window.

    Countdown display: The storefront reads starts_at/ends_at to render
    a timer. No additional model needed.
    """

    name = models.CharField(_("Sale Name"), max_length=255)
    slug = models.SlugField(_("Slug"), max_length=255, unique=True)
    description = models.TextField(_("Description"), blank=True)
    banner_image = models.ImageField(
        _("Banner Image"),
        upload_to="flash_sales/banners/",
        null=True, blank=True,
    )
    badge_label = models.CharField(
        _("Badge Label"),
        max_length=50,
        blank=True,
        help_text=_(
            "Label shown on product cards. e.g. 'FLASH SALE', '48H DEAL'"),
    )
    show_countdown_timer = models.BooleanField(
        _("Show Countdown Timer"),
        default=True,
    )
    is_publicly_visible = models.BooleanField(
        _("Publicly Visible"),
        default=True,
        help_text=_(
            "If False, only accessible via direct link (pre-launch testing)."),
    )
    applies_to_all_products = models.BooleanField(
        _("Applies to All Products"),
        default=False,
        help_text=_(
            "If True, all products receive the global_discount_percentage. "
            "If False, only products in FlashSaleItem records are discounted."
        ),
    )
    global_discount_percentage = models.DecimalField(
        _("Global Discount (%)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(
            Decimal("0.01")), MaxValueValidator(Decimal("100.00"))],
        help_text=_("Used when applies_to_all_products=True."),
    )
    priority = models.PositiveIntegerField(
        _("Priority"),
        default=100,
        help_text=_(
            "Flash sales typically have the highest priority. Default 100."),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="created_flash_sales",
    )

    class Meta:
        verbose_name = _("Flash Sale")
        verbose_name_plural = _("Flash Sales")
        ordering = ["-starts_at"]
        indexes = [
            models.Index(fields=["is_active", "starts_at", "ends_at"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["is_publicly_visible", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.starts_at} → {self.ends_at})"

    @property
    def time_remaining(self):
        if self.ends_at:
            remaining = self.ends_at - timezone.now()
            return max(remaining.total_seconds(), 0)
        return None


class FlashSaleItem(MixIdAndTimeModel):
    """
    A specific product/variant included in a FlashSale with
    its own discount rate and optional stock limit.

    The stock_limit field enforces "only 50 units at this price" scarcity.
    Once units_sold >= stock_limit, the item reverts to regular price.
    """

    flash_sale = models.ForeignKey(
        FlashSale,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Flash Sale"),
    )
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="flash_sale_items",
        help_text=_(
            "If set (without variant), applies to all variants of this public.product."),
    )
    variant = models.ForeignKey(
        ProductVariant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="flash_sale_items",
        help_text=_(
            "Specific variant override. Takes precedence over product-level entry."),
    )

    # ── Pricing ──
    discount_percentage = models.DecimalField(
        _("Discount Percentage"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(
            Decimal("0.01")), MaxValueValidator(Decimal("100.00"))],
    )
    sale_price = models.DecimalField(
        _("Fixed Sale Price"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_(
            "Exact price during the flash sale. Overrides discount_percentage if set."),
    )
    original_price_override = models.DecimalField(
        _("Original Price Override"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "Shown as the strike-through price. If not set, "
            "the product's regular price is used."
        ),
    )

    # ── Scarcity ──
    stock_limit = models.PositiveIntegerField(
        _("Flash Sale Stock Limit"),
        null=True,
        blank=True,
        help_text=_(
            "Only this many units are available at the flash sale price. "
            "Null = no limit (use regular inventory)."
        ),
    )
    units_sold = models.PositiveIntegerField(
        _("Units Sold at Flash Price"),
        default=0,
        help_text=_(
            "Auto-incremented when orders are placed. Do not edit manually."),
    )
    per_customer_limit = models.PositiveIntegerField(
        _("Per-Customer Purchase Limit"),
        null=True,
        blank=True,
        help_text=_("Max units one customer can buy at the flash sale price."),
    )

    # ── Status ──
    is_active = models.BooleanField(_("Active"), default=True)

    class Meta:
        verbose_name = _("Flash Sale Item")
        verbose_name_plural = _("Flash Sale Items")
        ordering = ["flash_sale", "product", "variant"]
        unique_together = [("flash_sale", "variant"),
                           ("flash_sale", "product")]
        indexes = [
            models.Index(fields=["flash_sale", "is_active"]),
            models.Index(fields=["variant"]),
        ]

    def __str__(self):
        target = self.variant or self.product
        pct = self.discount_percentage
        return f"{self.flash_sale.name} — {target} ({pct}% off)"

    @property
    def is_sold_out_at_sale_price(self) -> bool:
        if self.stock_limit is None:
            return False
        return self.units_sold >= self.stock_limit

    def compute_sale_price(self, base_price: Decimal) -> Decimal:
        """Compute the flash sale price for this item."""
        if self.sale_price is not None:
            return self.sale_price
        if self.discount_percentage:
            factor = Decimal("1") - (self.discount_percentage / Decimal("100"))
            return (base_price * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return base_price

    @transaction.atomic
    def increment_units_sold(self, quantity: int = 1):
        """Thread-safe units_sold increment."""
        FlashSaleItem.objects.filter(pk=self.pk).update(
            units_sold=models.F("units_sold") + quantity
        )
