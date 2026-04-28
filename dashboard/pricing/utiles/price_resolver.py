"""
pricing/utils/price_resolver.py
================================
The canonical price resolution pipeline.

Given a ProductVariant + optional Customer + optional quantity,
this module determines the FINAL price the customer pays by
walking through the full pricing hierarchy:

    Priority (highest → lowest):
    ┌──────────────────────────────────────────────────────┐
    │  1. FlashSale           (time-limited override)      │
    │  2. VolumePricingTier   (quantity-break price)       │
    │  3. PriceList entry     (B2B / customer group price) │
    │  4. Product base_price  (default fallback)           │
    └──────────────────────────────────────────────────────┘

Each layer can only LOWER the price — never raise it above
the product's base_price (unless explicitly configured).

The result is a PriceResolutionResult dataclass that carries
the final price PLUS the full audit trail of which layer
contributed to it — essential for display ("You save $X as
a VIP member") and debugging.

Usage:
    from pricing.utils import resolve_price, PricingContext

    ctx = PricingContext(customer=request.user.customer, quantity=3)
    result = resolve_price(variant, ctx)
    print(result.final_price)      # Decimal
    print(result.applied_layer)    # "flash_sale" | "volume" | "price_list" | "base"
    print(result.savings)          # Decimal — amount saved vs base
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger("pricing.price_resolver")

# Cache timeouts
FLASH_SALE_CACHE_TTL = 30        # 30s — flash sales change quickly
PRICE_LIST_CACHE_TTL = 300       # 5 min — price list lookups
VOLUME_TIER_CACHE_TTL = 600      # 10 min — volume tiers change rarely


# ─────────────────────────────────────────────────────────────
# CONTEXT & RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────

@dataclass
class PricingContext:
    """
    All the contextual inputs that affect price resolution.
    Pass this into resolve_price() instead of multiple kwargs.
    """
    customer: object = None             # accounts.Customer | None
    customer_group: object = None       # accounts.CustomerGroup | None (auto-resolved if None)
    quantity: int = 1                   # Units being purchased
    currency_code: str = "USD"          # Display currency
    include_tax: bool = False           # Include tax in returned price
    address_country: str = ""           # For tax-inclusive price calc
    address_state: str = ""
    ignore_flash_sales: bool = False    # For admin/B2B contexts
    ignore_volume_pricing: bool = False
    ignore_price_lists: bool = False
    price_list_override: object = None  # Force a specific PriceList


@dataclass
class PriceResolutionResult:
    """
    The complete, audited result of the pricing pipeline for one variant.
    """
    variant_id: str = ""
    base_price: Decimal = Decimal("0.00")
    final_price: Decimal = Decimal("0.00")
    compare_at_price: Optional[Decimal] = None
    currency: str = "USD"

    # ── Which layer set the price ──
    applied_layer: str = "base"
    # "base" | "price_list" | "volume" | "flash_sale"

    # ── Audit trail ──
    flash_sale_applied: bool = False
    flash_sale_id: Optional[str] = None
    flash_sale_name: str = ""
    flash_sale_discount_pct: Optional[Decimal] = None

    volume_tier_applied: bool = False
    volume_tier_min_qty: int = 0
    volume_tier_discount_pct: Optional[Decimal] = None

    price_list_applied: bool = False
    price_list_id: Optional[str] = None
    price_list_name: str = ""
    price_list_code: str = ""

    # ── Savings ──
    savings: Decimal = Decimal("0.00")
    savings_percentage: Decimal = Decimal("0.00")
    is_on_sale: bool = False

    # ── Labels for storefront ──
    sale_badge: str = ""
    savings_label: str = ""

    def __post_init__(self):
        if self.base_price > 0 and self.final_price < self.base_price:
            self.savings = self.base_price - self.final_price
            self.savings_percentage = (
                (self.savings / self.base_price * 100).quantize(Decimal("0.1"))
            )
            self.is_on_sale = True


@dataclass
class BulkPriceResult:
    """Result from resolve_prices_bulk() — a map of variant_id → PriceResolutionResult."""
    prices: dict = field(default_factory=dict)   # {str(variant_id): PriceResolutionResult}
    context: PricingContext = None
    resolved_at: str = ""


# ─────────────────────────────────────────────────────────────
# SECTION 1 — MAIN RESOLVER
# ─────────────────────────────────────────────────────────────

def resolve_price(variant, context: PricingContext = None) -> PriceResolutionResult:
    """
    Resolve the final price for a ProductVariant given a PricingContext.

    Pipeline:
      Step 1 — Get base price from variant
      Step 2 — Check active FlashSaleItem (highest priority, time-bounded)
      Step 3 — Check VolumePricingTier for requested quantity
      Step 4 — Check applicable PriceList entries for this customer/group
      Step 5 — Apply lowest price from all layers (never raise above base)
      Step 6 — Build audit trail and savings labels

    Args:
        variant: catalog.ProductVariant instance
        context: PricingContext with customer, quantity, etc.
                 Defaults to anonymous, qty=1 if None.

    Returns:
        PriceResolutionResult with full audit trail.
    """
    if context is None:
        context = PricingContext()

    base_price = variant.effective_price
    compare_at = variant.compare_at_price or variant.product.compare_at_price

    result = PriceResolutionResult(
        variant_id=str(variant.id),
        base_price=base_price,
        final_price=base_price,
        compare_at_price=compare_at,
        currency=context.currency_code,
        applied_layer="base",
    )

    candidate_prices = []  # (price, layer_name, metadata_dict)

    # ── Step 2: Flash Sale ──
    if not context.ignore_flash_sales:
        flash_result = get_flash_sale_item(variant)
        if flash_result:
            flash_price = flash_result["price"]
            candidate_prices.append((
                flash_price, "flash_sale", {
                    "flash_sale_applied": True,
                    "flash_sale_id": flash_result["sale_id"],
                    "flash_sale_name": flash_result["sale_name"],
                    "flash_sale_discount_pct": flash_result.get("discount_pct"),
                }
            ))

    # ── Step 3: Volume Pricing Tier ──
    if not context.ignore_volume_pricing and context.quantity >= 1:
        volume_result = get_volume_tier(variant, context.quantity, context.customer_group)
        if volume_result:
            vol_price = volume_result["price"]
            candidate_prices.append((
                vol_price, "volume", {
                    "volume_tier_applied": True,
                    "volume_tier_min_qty": volume_result["min_qty"],
                    "volume_tier_discount_pct": volume_result.get("discount_pct"),
                }
            ))

    # ── Step 4: Price List ──
    if not context.ignore_price_lists:
        price_list_result = _resolve_price_list_price(variant, context)
        if price_list_result:
            pl_price = price_list_result["price"]
            candidate_prices.append((
                pl_price, "price_list", {
                    "price_list_applied": True,
                    "price_list_id": price_list_result["price_list_id"],
                    "price_list_name": price_list_result["price_list_name"],
                    "price_list_code": price_list_result["price_list_code"],
                }
            ))

    # ── Step 5: Apply lowest price ──
    if candidate_prices:
        # Sort by price ascending — lowest wins
        candidate_prices.sort(key=lambda x: x[0])
        best_price, best_layer, best_meta = candidate_prices[0]

        # Never raise above base (safety guard)
        if best_price <= base_price:
            result.final_price = best_price
            result.applied_layer = best_layer
            for key, val in best_meta.items():
                setattr(result, key, val)

    # ── Step 6: Build labels ──
    result.__post_init__()  # Recalculate savings
    result.sale_badge = _build_sale_badge(result)
    result.savings_label = _build_savings_label(result, context.currency_code)

    return result


def resolve_prices_bulk(variants: list, context: PricingContext = None) -> BulkPriceResult:
    """
    Resolve prices for a list of ProductVariant instances in one call.
    More efficient than calling resolve_price() in a loop because it
    batches the flash sale and price list lookups.

    Args:
        variants: List of catalog.ProductVariant instances.
        context: Shared PricingContext for all variants.

    Returns:
        BulkPriceResult with a dict mapping variant_id → PriceResolutionResult.
    """
    if context is None:
        context = PricingContext()

    prices = {}

    # Pre-fetch flash sales and price list data in batch
    flash_sale_map = _batch_get_flash_sale_items(variants)
    price_list_map = _batch_get_price_list_prices(variants, context)

    for variant in variants:
        vid = str(variant.id)
        base_price = variant.effective_price
        compare_at = variant.compare_at_price or variant.product.compare_at_price

        result = PriceResolutionResult(
            variant_id=vid,
            base_price=base_price,
            final_price=base_price,
            compare_at_price=compare_at,
            currency=context.currency_code,
            applied_layer="base",
        )

        candidates = []

        if not context.ignore_flash_sales and vid in flash_sale_map:
            fd = flash_sale_map[vid]
            candidates.append((fd["price"], "flash_sale", {
                "flash_sale_applied": True,
                "flash_sale_id": fd["sale_id"],
                "flash_sale_name": fd["sale_name"],
                "flash_sale_discount_pct": fd.get("discount_pct"),
            }))

        if not context.ignore_price_lists and vid in price_list_map:
            pd = price_list_map[vid]
            candidates.append((pd["price"], "price_list", {
                "price_list_applied": True,
                "price_list_id": pd["price_list_id"],
                "price_list_name": pd["price_list_name"],
                "price_list_code": pd["price_list_code"],
            }))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            best_price, best_layer, best_meta = candidates[0]
            if best_price <= base_price:
                result.final_price = best_price
                result.applied_layer = best_layer
                for k, v in best_meta.items():
                    setattr(result, k, v)

        result.__post_init__()
        result.sale_badge = _build_sale_badge(result)
        result.savings_label = _build_savings_label(result, context.currency_code)
        prices[vid] = result

    return BulkPriceResult(
        prices=prices,
        context=context,
        resolved_at=timezone.now().isoformat(),
    )


# ─────────────────────────────────────────────────────────────
# SECTION 2 — LAYER LOOKUPS
# ─────────────────────────────────────────────────────────────

def get_flash_sale_item(variant) -> Optional[dict]:
    """
    Find the active FlashSaleItem for a variant right now.

    Returns:
        dict | None: {price, sale_id, sale_name, discount_pct, stock_limit,
                      units_sold, per_customer_limit, ends_at}
    """
    from pricing.models import FlashSale, FlashSaleItem

    cache_key = f"flash_sale_variant_{variant.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached != "NONE" else None

    now = timezone.now()

    # Try exact variant match first, then product-level
    item = (
        FlashSaleItem.objects
        .filter(
            is_active=True,
            flash_sale__is_active=True,
            flash_sale__starts_at__lte=now,
            flash_sale__ends_at__gt=now,
        )
        .filter(
            models.Q(variant=variant) | models.Q(product=variant.product, variant__isnull=True)
        )
        .select_related("flash_sale")
        .order_by("-variant")  # variant-specific takes priority
        .first()
    )

    if not item or item.is_sold_out_at_sale_price:
        cache.set(cache_key, "NONE", FLASH_SALE_CACHE_TTL)
        return None

    base = variant.effective_price
    sale_price = item.compute_sale_price(base)

    discount_pct = None
    if item.discount_percentage:
        discount_pct = item.discount_percentage
    elif sale_price < base and base > 0:
        discount_pct = ((base - sale_price) / base * 100).quantize(Decimal("0.1"))

    result = {
        "price": sale_price,
        "sale_id": str(item.flash_sale.id),
        "sale_name": item.flash_sale.name,
        "discount_pct": discount_pct,
        "stock_limit": item.stock_limit,
        "units_sold": item.units_sold,
        "units_remaining": (item.stock_limit - item.units_sold) if item.stock_limit else None,
        "per_customer_limit": item.per_customer_limit,
        "ends_at": item.flash_sale.ends_at.isoformat() if item.flash_sale.ends_at else None,
    }

    cache.set(cache_key, result, FLASH_SALE_CACHE_TTL)
    return result


def get_volume_tier(variant, quantity: int, customer_group=None) -> Optional[dict]:
    """
    Find the applicable VolumePricingTier for the given quantity and customer group.

    Returns:
        dict | None: {price, min_qty, max_qty, discount_pct, show_savings_label}
    """
    from pricing.models import VolumePricingTier
    from django.db import models as dj_models

    cache_key = f"volume_tier_{variant.id}_{quantity}_{getattr(customer_group, 'id', 'none')}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached != "NONE" else None

    tier = (
        VolumePricingTier.objects
        .filter(
            variant=variant,
            is_active=True,
            min_quantity__lte=quantity,
        )
        .filter(
            dj_models.Q(max_quantity__gte=quantity) | dj_models.Q(max_quantity__isnull=True)
        )
        .filter(
            dj_models.Q(customer_group=customer_group) | dj_models.Q(customer_group__isnull=True)
        )
        .order_by("-min_quantity")  # most specific (highest threshold) wins
        .first()
    )

    if not tier:
        cache.set(cache_key, "NONE", VOLUME_TIER_CACHE_TTL)
        return None

    base = variant.effective_price
    tier_price = tier.compute_price(base)

    discount_pct = None
    if base > 0 and tier_price < base:
        discount_pct = ((base - tier_price) / base * 100).quantize(Decimal("0.1"))

    result = {
        "price": tier_price,
        "min_qty": tier.min_quantity,
        "max_qty": tier.max_quantity,
        "discount_pct": discount_pct,
        "show_savings_label": tier.show_savings_label,
        "tier_id": str(tier.id),
    }

    cache.set(cache_key, result, VOLUME_TIER_CACHE_TTL)
    return result


def get_applicable_price_lists(customer) -> list:
    """
    Return all PriceLists that apply to a given customer, sorted by priority.

    Resolution:
      1. Price lists assigned directly to this customer (highest priority)
      2. Price lists assigned to any of the customer's groups
      3. Public price lists (is_public=True)

    Returns:
        list[PriceList]: Sorted by effective priority, highest first.
    """
    from pricing.models import PriceList

    if not customer:
        return list(
            PriceList.objects.filter(
                is_active=True,
                is_public=True,
            ).order_by("-priority")
        )

    now = timezone.now()
    base_filter = (
        PriceList.objects
        .filter(is_active=True)
        .filter(
            models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now)
        )
        .filter(
            models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now)
        )
    )

    # Direct customer assignment
    direct = base_filter.filter(
        customer_group_assignments__customer=customer
    )

    # Group-based assignment
    customer_groups = getattr(customer, "groups", customer.__class__.objects.none())
    if hasattr(customer, "group_set"):
        customer_groups = customer.group_set.all()
    elif hasattr(customer, "customer_group"):
        customer_groups = [customer.customer_group] if customer.customer_group else []

    group_based = base_filter.filter(
        customer_group_assignments__customer_group__in=customer_groups
    )

    # Public lists
    public = base_filter.filter(is_public=True)

    # Merge + deduplicate + sort by priority
    seen_ids = set()
    result = []
    for pl in list(direct) + list(group_based) + list(public):
        if pl.id not in seen_ids:
            seen_ids.add(pl.id)
            result.append(pl)

    result.sort(key=lambda pl: pl.priority, reverse=True)
    return result


# ─────────────────────────────────────────────────────────────
# SECTION 3 — INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _resolve_price_list_price(variant, context: PricingContext) -> Optional[dict]:
    """
    Find the best price list price for a variant given a pricing context.
    Walks applicable price lists in priority order and returns the first match.
    """
    if context.price_list_override:
        price_lists = [context.price_list_override]
    else:
        customer = context.customer
        if not customer and not context.ignore_price_lists:
            return None
        price_lists = get_applicable_price_lists(customer)

    for pl in price_lists:
        if not pl.is_currently_active:
            continue
        price = pl.get_price_for_variant(variant)
        if price is not None and price < variant.effective_price:
            return {
                "price": price,
                "price_list_id": str(pl.id),
                "price_list_name": pl.name,
                "price_list_code": pl.code,
            }

    return None


def _batch_get_flash_sale_items(variants: list) -> dict:
    """
    Batch-fetch active flash sale items for a list of variants.
    Returns {str(variant_id): flash_data_dict}
    """
    from pricing.models import FlashSaleItem
    from django.db import models as dj_models

    now = timezone.now()
    variant_ids = [v.id for v in variants]
    product_ids = list({v.product_id for v in variants})

    items = (
        FlashSaleItem.objects
        .filter(
            is_active=True,
            flash_sale__is_active=True,
            flash_sale__starts_at__lte=now,
            flash_sale__ends_at__gt=now,
        )
        .filter(
            dj_models.Q(variant_id__in=variant_ids) |
            dj_models.Q(product_id__in=product_ids, variant__isnull=True)
        )
        .select_related("flash_sale", "variant", "product")
    )

    variant_map = {}
    product_map = {}

    for item in items:
        if item.is_sold_out_at_sale_price:
            continue
        if item.variant_id:
            variant_map[str(item.variant_id)] = item
        elif item.product_id:
            product_map[str(item.product_id)] = item

    result = {}
    for v in variants:
        vid = str(v.id)
        pid = str(v.product_id)
        item = variant_map.get(vid) or product_map.get(pid)
        if not item:
            continue
        base = v.effective_price
        sale_price = item.compute_sale_price(base)
        if sale_price >= base:
            continue
        discount_pct = item.discount_percentage or (
            ((base - sale_price) / base * 100).quantize(Decimal("0.1")) if base > 0 else None
        )
        result[vid] = {
            "price": sale_price,
            "sale_id": str(item.flash_sale.id),
            "sale_name": item.flash_sale.name,
            "discount_pct": discount_pct,
            "ends_at": item.flash_sale.ends_at.isoformat() if item.flash_sale.ends_at else None,
        }

    return result


def _batch_get_price_list_prices(variants: list, context: PricingContext) -> dict:
    """
    Batch-fetch price list prices for a list of variants.
    Returns {str(variant_id): price_data_dict}
    """
    if not context.customer and not context.price_list_override:
        return {}

    price_lists = (
        [context.price_list_override]
        if context.price_list_override
        else get_applicable_price_lists(context.customer)
    )

    result = {}
    for v in variants:
        vid = str(v.id)
        base = v.effective_price
        for pl in price_lists:
            if not pl.is_currently_active:
                continue
            price = pl.get_price_for_variant(v)
            if price is not None and price < base:
                result[vid] = {
                    "price": price,
                    "price_list_id": str(pl.id),
                    "price_list_name": pl.name,
                    "price_list_code": pl.code,
                }
                break  # Highest priority list already applied

    return result


def _build_sale_badge(result: PriceResolutionResult) -> str:
    """Build the short label shown on product cards."""
    if result.applied_layer == "flash_sale":
        return f"FLASH -{result.flash_sale_discount_pct or result.savings_percentage}%"
    if result.applied_layer == "volume":
        return f"BULK SAVE {result.volume_tier_discount_pct or result.savings_percentage}%"
    if result.applied_layer == "price_list":
        return f"{result.price_list_code} PRICE"
    if result.is_on_sale:
        return f"SALE -{result.savings_percentage}%"
    return ""


def _build_savings_label(result: PriceResolutionResult, currency: str) -> str:
    """Build the human-readable savings message for the product page."""
    if result.savings <= 0:
        return ""
    if result.applied_layer == "volume":
        return (
            f"You save {currency} {result.savings} "
            f"({result.savings_percentage}% off) by buying in bulk!"
        )
    if result.applied_layer == "price_list":
        return (
            f"Your {result.price_list_name} price saves you "
            f"{currency} {result.savings} ({result.savings_percentage}% off)"
        )
    if result.applied_layer == "flash_sale":
        return (
            f"Flash Sale! You save {currency} {result.savings} "
            f"({result.savings_percentage}% off) — limited time!"
        )
    return f"You save {currency} {result.savings} ({result.savings_percentage}% off)"


# Alias — import models lazily to avoid circular imports
try:
    from django.db import models
except ImportError:
    pass
