"""
pricing/models.py
=================
App 9 — Pricing Domain
Multi-tenant e-commerce platform (django-tenants, schema-based isolation)

Complete model inventory (22 models):

  SECTION 1 — CURRENCY & EXCHANGE RATES
    1.  Currency
    2.  ExchangeRate

  SECTION 2 — PRICE LISTS (Tiered / B2B Pricing)
    3.  PriceList
    4.  PriceListCustomerGroup
    5.  PriceListEntry

  SECTION 3 — DISCOUNT CODES (Coupons)
    6.  DiscountCode
    7.  DiscountRule
    8.  DiscountUsage

  SECTION 4 — AUTOMATIC DISCOUNTS (Rule-Based, No Code)
    9.  AutomaticDiscount
    10. AutomaticDiscountCondition
    11. AutomaticDiscountBenefit

  SECTION 5 — ADVANCED PROMOTIONS
    12. BuyXGetYPromotion
    13. BuyXGetYItem
    14. VolumePricingTier
    15. FlashSale
    16. FlashSaleItem

  SECTION 6 — GIFT CARDS
    17. GiftCardTemplate
    18. GiftCard
    19. GiftCardTransaction

  SECTION 7 — TAX ENGINE
    20. TaxCategory
    21. TaxZone
    22. TaxRate

Architecture Notes:
  - All monetary values: Decimal(14,2) — never float.
  - All primary keys: UUID4.
  - All models are tenant-scoped (live inside tenant schema).
  - Cross-app references to catalog.Product, catalog.ProductVariant,
    catalog.Collection, accounts.Customer, accounts.CustomerGroup
    use string ForeignKey references to avoid circular imports.
  - GiftCard ledger uses append-only GiftCardTransaction — never
    mutate the balance field directly; use the adjust() method.
  - DiscountUsage is append-only — never delete rows.
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
from dashboard.settings.models import MixIdAndTimeModel, ActivatableModel, AuditModel
from public.userauth.models import Customer, CustomerGroup, TenantUser as User
from public.category.models import Category
from public.product.models import Product, ProductVariant


# ─────────────────────────────────────────────────────────────
# SECTION 1 — CURRENCY & EXCHANGE RATES
# ─────────────────────────────────────────────────────────────

class Currency(MixIdAndTimeModel):
    """
    Supported currencies for the tenant's store.

    The store has one primary (base) currency. Other currencies
    are display currencies — their rates are stored in ExchangeRate.
    Pricing, discounts, and gift cards are always stored in the base currency
    and converted at display time.

    ISO 4217 codes only (e.g. USD, NGN, GBP, EUR, GHS, KES).
    """

    code = models.CharField(
        _("ISO Code"),
        max_length=3,
        unique=True,
        help_text=_("ISO 4217 three-letter currency code. e.g. USD, NGN, GBP"),
        validators=[
            RegexValidator(
                regex=r"^[A-Z]{3}$",
                message="Currency code must be exactly 3 uppercase letters.",
            )
        ],
    )
    name = models.CharField(_("Currency Name"), max_length=100)
    symbol = models.CharField(
        _("Symbol"),
        max_length=10,
        help_text=_("Display symbol. e.g. $, ₦, £, €, GH₵"),
    )
    symbol_position = models.CharField(
        _("Symbol Position"),
        max_length=10,
        choices=[("before", _("Before amount ($10)")),
                 ("after", _("After amount (10$)"))],
        default="before",
    )
    decimal_places = models.PositiveSmallIntegerField(
        _("Decimal Places"),
        default=2,
        validators=[MaxValueValidator(4)],
        help_text=_(
            "Number of decimal places for this currency (0 for JPY, 2 for USD)."),
    )
    thousands_separator = models.CharField(
        _("Thousands Separator"),
        max_length=2,
        default=",",
    )
    decimal_separator = models.CharField(
        _("Decimal Separator"),
        max_length=2,
        default=".",
    )
    is_base_currency = models.BooleanField(
        _("Base Currency"),
        default=False,
        help_text=_(
            "The store's primary currency. All prices are stored in this currency. "
            "Only one currency can be the base."
        ),
    )
    is_enabled = models.BooleanField(
        _("Enabled"),
        default=True,
        help_text=_("Customers can browse and checkout in this currency."),
    )
    rounding_mode = models.CharField(
        _("Rounding Mode"),
        max_length=20,
        choices=[
            ("round_half_up", _("Round Half Up (standard)")),
            ("round_up", _("Always Round Up")),
            ("round_down", _("Always Round Down")),
            ("round_to_nearest_5", _("Round to Nearest 0.05")),
        ],
        default="round_half_up",
    )

    class Meta:
        verbose_name = _("Currency")
        verbose_name_plural = _("Currencies")
        ordering = ["-is_base_currency", "code"]

    def __str__(self):
        return f"{self.code} ({self.name})"

    def save(self, *args, **kwargs):
        """Enforce only one base currency at a time."""
        if self.is_base_currency:
            Currency.objects.exclude(pk=self.pk).filter(
                is_base_currency=True
            ).update(is_base_currency=False)
        super().save(*args, **kwargs)

    def format_amount(self, amount: Decimal) -> str:
        """Format a Decimal amount as a display string for this currency."""
        fmt = f"{amount:,.{self.decimal_places}f}"
        if self.symbol_position == "before":
            return f"{self.symbol}{fmt}"
        return f"{fmt}{self.symbol}"


class ExchangeRate(MixIdAndTimeModel):
    """
    Conversion rate from the store's base currency to a target currency.

    Rates are fetched from an external provider (Fixer, Open Exchange Rates,
    etc.) by a scheduled Celery task and stored here.

    e.g. If base = USD, rate for NGN = 1600.00 means 1 USD = 1600 NGN.

    Manual override allows merchant to lock a rate and ignore provider updates.
    """

    base_currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name="base_rates",
        verbose_name=_("Base Currency"),
        help_text=_(
            "The currency being converted FROM (usually the store base)."),
    )
    target_currency = models.ForeignKey(
        Currency,
        on_delete=models.CASCADE,
        related_name="target_rates",
        verbose_name=_("Target Currency"),
        help_text=_("The currency being converted TO."),
    )
    rate = models.DecimalField(
        _("Exchange Rate"),
        max_digits=20,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
        help_text=_("1 unit of base_currency = rate units of target_currency."),
    )
    rate_buy = models.DecimalField(
        _("Buy Rate"),
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        help_text=_("Bank buy rate (optional — for more accurate conversion)."),
    )
    rate_sell = models.DecimalField(
        _("Sell Rate"),
        max_digits=20,
        decimal_places=6,
        null=True,
        blank=True,
        help_text=_("Bank sell rate (optional)."),
    )
    markup_percentage = models.DecimalField(
        _("Markup (%)"),
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(
            Decimal("0.00")), MaxValueValidator(Decimal("50.00"))],
        help_text=_(
            "Additional markup applied on top of the raw rate to cover FX costs. "
            "e.g. 2.5 adds a 2.5% buffer."
        ),
    )
    is_manual_override = models.BooleanField(
        _("Manual Override"),
        default=False,
        help_text=_(
            "If True, this rate is locked and will not be updated by the rate sync task."
        ),
    )
    provider = models.CharField(
        _("Rate Provider"),
        max_length=100,
        blank=True,
        help_text=_("e.g. 'fixer.io', 'openexchangerates', 'manual'"),
    )
    fetched_at = models.DateTimeField(
        _("Fetched At"),
        null=True,
        blank=True,
        help_text=_("When the rate was last retrieved from the provider."),
    )

    class Meta:
        verbose_name = _("Exchange Rate")
        verbose_name_plural = _("Exchange Rates")
        unique_together = [("base_currency", "target_currency")]
        ordering = ["target_currency__code"]

    def __str__(self):
        return f"1 {self.base_currency.code} = {self.rate} {self.target_currency.code}"

    @property
    def effective_rate(self) -> Decimal:
        """Rate with markup applied."""
        markup_multiplier = Decimal(
            "1") + (self.markup_percentage / Decimal("100"))
        return (self.rate * markup_multiplier).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )

    def convert(self, amount: Decimal) -> Decimal:
        """Convert an amount from base to target currency."""
        return (amount * self.effective_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


# ─────────────────────────────────────────────────────────────
# SECTION 2 — PRICE LISTS (B2B / Tiered Pricing)
# ─────────────────────────────────────────────────────────────

class PriceList(AuditModel, ActivatableModel):
    """
    A named pricing context that overrides the default product prices
    for specific customer groups or individual customers.

    Use cases:
      - Wholesale pricing (50% off retail for Wholesale group)
      - VIP member pricing
      - Trade / Partner pricing
      - Staff pricing
      - Geographic pricing (USD prices vs NGN prices)
      - B2B contract pricing for specific accounts

    Priority: When multiple price lists apply to a customer, the one
    with the highest `priority` value wins. Tenant can configure this.

    Price list types:
      PERCENTAGE_DISCOUNT  → Apply flat % off the default price for all entries
      FIXED_PRICE          → Each PriceListEntry specifies an exact price
      FIXED_DISCOUNT       → Each entry specifies a fixed amount off
      MULTIPLIER           → Multiply the base price by a factor (e.g. 0.7 = 30% off)
    """

    class PriceListType(models.TextChoices):
        PERCENTAGE_DISCOUNT = "percentage_discount", _(
            "Percentage Discount (e.g. 20% off)")
        FIXED_PRICE = "fixed_price", _("Fixed Price (exact price per variant)")
        FIXED_DISCOUNT = "fixed_discount", _(
            "Fixed Amount Discount (e.g. $5 off)")
        MULTIPLIER = "multiplier", _("Price Multiplier (e.g. 0.7× base price)")

    class PriceCalculationBase(models.TextChoices):
        ORIGINAL_PRICE = "original_price", _(
            "Based on Original/Compare-At Price")
        SALE_PRICE = "sale_price", _("Based on Current Sale Price")
        COST_PRICE = "cost_price", _("Based on Cost Per Item")

    # ── Identity ──
    name = models.CharField(
        _("Price List Name"),
        max_length=255,
        help_text=_("e.g. 'Wholesale Prices', 'VIP Members', 'Trade Partners'"),
    )
    code = models.CharField(
        _("Internal Code"),
        max_length=50,
        unique=True,
        help_text=_(
            "Machine-readable identifier. e.g. 'WHOLESALE', 'VIP', 'STAFF'"),
    )
    description = models.TextField(_("Description"), blank=True)
    currency = models.ForeignKey(
        Currency,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="price_lists",
        verbose_name=_("Currency"),
        help_text=_(
            "If set, prices in this list are in this currency. "
            "Null = use store base currency."
        ),
    )

    # ── Type & amount ──
    price_list_type = models.CharField(
        _("Type"),
        max_length=25,
        choices=PriceListType.choices,
        default=PriceListType.FIXED_PRICE,
    )
    calculation_base = models.CharField(
        _("Calculation Base"),
        max_length=20,
        choices=PriceCalculationBase.choices,
        default=PriceCalculationBase.SALE_PRICE,
        help_text=_(
            "For PERCENTAGE_DISCOUNT and MULTIPLIER types — "
            "which base price to apply the reduction against."
        ),
    )
    global_discount_percentage = models.DecimalField(
        _("Global Discount (%)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(
            Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
        help_text=_(
            "Used with PERCENTAGE_DISCOUNT type. "
            "Applied to all products in this list unless overridden by PriceListEntry."
        ),
    )
    global_multiplier = models.DecimalField(
        _("Global Multiplier"),
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(
            Decimal("0.0001")), MaxValueValidator(Decimal("10.0000"))],
        help_text=_(
            "Used with MULTIPLIER type. e.g. 0.7000 = 30% off all products."
        ),
    )
    rounding_increment = models.DecimalField(
        _("Rounding Increment"),
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "Round computed prices to this increment. e.g. 0.99, 0.05, 1.00"),
    )

    # ── Access control ──
    is_public = models.BooleanField(
        _("Public"),
        default=False,
        help_text=_(
            "If True, any logged-in customer can access this price list. "
            "If False, only explicitly assigned customers/groups can."
        ),
    )
    requires_login = models.BooleanField(
        _("Requires Login"),
        default=True,
        help_text=_(
            "Price list is hidden from guest/unauthenticated visitors."),
    )
    priority = models.PositiveIntegerField(
        _("Priority"),
        default=0,
        help_text=_(
            "When multiple price lists apply to a customer, the one with "
            "the highest priority number wins. 0 = lowest, 100 = highest."
        ),
    )
    allow_discount_stacking = models.BooleanField(
        _("Allow Discount Code Stacking"),
        default=False,
        help_text=_(
            "If True, customers assigned to this price list can ALSO apply "
            "a discount code on top of the price list discount."
        ),
    )

    # ── Metadata ──
    internal_note = models.TextField(_("Internal Note"), blank=True)

    class Meta:
        verbose_name = _("Price List")
        verbose_name_plural = _("Price Lists")
        ordering = ["-priority", "name"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["is_active", "is_public"]),
            models.Index(fields=["priority"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    def get_price_for_variant(self, variant) -> Decimal | None:
        """
        Compute the price list price for a variant.

        Resolution order:
          1. Explicit PriceListEntry for this variant → return its price.
          2. Explicit PriceListEntry for the parent product (no variant) → use it.
          3. Fall back to global_discount_percentage / global_multiplier.
          4. None if no rule applies.

        Returns:
            Decimal | None: The computed price, or None if list doesn't cover this variant.
        """
        base_price = variant.effective_price

        # Try exact variant entry
        entry = self.entries.filter(
            variant=variant, is_active=True
        ).first()

        # Try product-level entry (variant=None on entry)
        if not entry:
            entry = self.entries.filter(
                product=variant.product, variant__isnull=True, is_active=True
            ).first()

        if entry:
            return entry.compute_price(base_price)

        # Global rule
        if self.price_list_type == self.PriceListType.PERCENTAGE_DISCOUNT:
            if self.global_discount_percentage:
                factor = Decimal(
                    "1") - (self.global_discount_percentage / Decimal("100"))
                computed = base_price * factor
                return self._apply_rounding(computed)

        elif self.price_list_type == self.PriceListType.MULTIPLIER:
            if self.global_multiplier:
                return self._apply_rounding(base_price * self.global_multiplier)

        return None

    def _apply_rounding(self, price: Decimal) -> Decimal:
        if self.rounding_increment:
            increment = self.rounding_increment
            return (price / increment).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * increment
        return price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PriceListCustomerGroup(MixIdAndTimeModel):
    """
    Assigns a PriceList to a CustomerGroup.
    When a customer in the group visits the store, the price list
    is automatically applied to all product prices.

    Also supports individual customer assignment (customer FK, no group).
    """

    price_list = models.ForeignKey(
        PriceList,
        on_delete=models.CASCADE,
        related_name="customer_group_assignments",
        verbose_name=_("Price List"),
    )
    customer_group = models.ForeignKey(
        CustomerGroup,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="price_list_assignments",
        verbose_name=_("Customer Group"),
        help_text=_("Assign the price list to a customer group."),
    )
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="price_list_assignments",
        verbose_name=_("Individual Customer"),
        help_text=_(
            "Assign the price list to a specific customer (overrides group assignment)."),
    )
    override_priority = models.PositiveIntegerField(
        _("Override Priority"),
        null=True,
        blank=True,
        help_text=_(
            "If set, overrides the price list's global priority for this assignment. "
            "Useful when one customer gets a higher-priority version of the same list."
        ),
    )
    assigned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="price_list_assignments_made",
    )

    class Meta:
        verbose_name = _("Price List Assignment")
        verbose_name_plural = _("Price List Assignments")
        unique_together = [
            ("price_list", "customer_group"),
            ("price_list", "customer"),
        ]
        indexes = [
            models.Index(fields=["customer_group"]),
            models.Index(fields=["customer"]),
        ]

    def __str__(self):
        target = self.customer or self.customer_group or "Unassigned"
        return f"{self.price_list.name} → {target}"


class PriceListEntry(MixIdAndTimeModel):
    """
    A specific price override for a ProductVariant (or entire Product)
    within a PriceList.

    Granularity levels (applied in order, most specific wins):
      1. Specific variant (product + variant set) → highest specificity
      2. Product-level (product set, variant null) → applies to all variants of this product
      3. Category-level (category set, product/variant null) → all products in category

    Entry types mirror PriceList.PriceListType but are per-line overrides:
      FIXED_PRICE: entry_price is the exact price.
      PERCENTAGE_DISCOUNT: entry_discount_percentage off base.
      FIXED_DISCOUNT: entry_fixed_discount off base.
      MULTIPLIER: entry_multiplier × base.
    """

    class EntryType(models.TextChoices):
        FIXED_PRICE = "fixed_price", _("Fixed Price")
        PERCENTAGE_DISCOUNT = "percentage_discount", _("Percentage Discount")
        FIXED_DISCOUNT = "fixed_discount", _("Fixed Amount Discount")
        MULTIPLIER = "multiplier", _("Price Multiplier")

    price_list = models.ForeignKey(
        PriceList,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name=_("Price List"),
    )

    # ── Target (most specific wins) ──
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="price_list_entries",
        verbose_name=_("Product"),
    )
    variant = models.ForeignKey(
        ProductVariant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="price_list_entries",
        verbose_name=_("Variant"),
    )
    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="price_list_entries",
        verbose_name=_("Category"),
        help_text=_(
            "Applied to all products in this category if no product/variant set."),
    )

    # ── Pricing ──
    entry_type = models.CharField(
        _("Entry Type"),
        max_length=25,
        choices=EntryType.choices,
        default=EntryType.FIXED_PRICE,
    )
    price = models.DecimalField(
        _("Fixed Price"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_(
            "For FIXED_PRICE type: the exact price in the price list currency."),
    )
    min_price = models.DecimalField(
        _("Minimum Price Floor"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_(
            "Computed price will never go below this value. "
            "Prevents discounts from going below cost."
        ),
    )
    discount_percentage = models.DecimalField(
        _("Discount Percentage"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(
            Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
        help_text=_("For PERCENTAGE_DISCOUNT type: % off the base price."),
    )
    fixed_discount = models.DecimalField(
        _("Fixed Discount Amount"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text=_("For FIXED_DISCOUNT type: flat amount off the base price."),
    )
    multiplier = models.DecimalField(
        _("Price Multiplier"),
        max_digits=6,
        decimal_places=4,
        null=True,
        blank=True,
        validators=[MinValueValidator(
            Decimal("0.0001")), MaxValueValidator(Decimal("10.0000"))],
        help_text=_("For MULTIPLIER type: e.g. 0.7000 = 30% off base price."),
    )
    compare_at_price = models.DecimalField(
        _("Compare At Price"),
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=_(
            "Strike-through price shown alongside the price list price."),
    )

    # ── Validity ──
    is_active = models.BooleanField(_("Active"), default=True)
    min_quantity = models.PositiveIntegerField(
        _("Minimum Quantity"),
        default=1,
        help_text=_(
            "This price only applies when ordering at least this many units."),
    )

    class Meta:
        verbose_name = _("Price List Entry")
        verbose_name_plural = _("Price List Entries")
        ordering = ["price_list", "product", "variant"]
        indexes = [
            models.Index(fields=["price_list", "variant"]),
            models.Index(fields=["price_list", "product"]),
            models.Index(fields=["price_list", "category"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        target = self.variant or self.product or self.category or "Global"
        return f"{self.price_list.name} — {target}: {self.entry_type}"

    def compute_price(self, base_price: Decimal) -> Decimal:
        """
        Compute the effective price from this entry given the variant's base price.
        Respects min_price floor.
        """
        TWO_PLACES = Decimal("0.01")

        if self.entry_type == self.EntryType.FIXED_PRICE and self.price is not None:
            computed = self.price

        elif self.entry_type == self.EntryType.PERCENTAGE_DISCOUNT and self.discount_percentage:
            factor = Decimal("1") - (self.discount_percentage / Decimal("100"))
            computed = base_price * factor

        elif self.entry_type == self.EntryType.FIXED_DISCOUNT and self.fixed_discount:
            computed = max(Decimal("0.00"), base_price - self.fixed_discount)

        elif self.entry_type == self.EntryType.MULTIPLIER and self.multiplier:
            computed = base_price * self.multiplier

        else:
            return base_price

        computed = computed.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        if self.min_price is not None:
            computed = max(computed, self.min_price)

        return computed
