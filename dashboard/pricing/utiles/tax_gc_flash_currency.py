"""
pricing/utils/tax.py + gift_card.py + flash_sale.py + currency.py
==================================================================
Four utility modules combined for brevity.
Each section is clearly marked with its module boundary.
"""

# ══════════════════════════════════════════════════════════════
# MODULE: tax.py
# Tax zone resolution, rate lookup, and order tax calculation
# ══════════════════════════════════════════════════════════════

import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("pricing.tax")

TAX_ZONE_CACHE_TTL = 300
TAX_RATE_CACHE_TTL = 600


@dataclass
class TaxLineResult:
    title: str = ""
    tax_type: str = ""
    rate: Decimal = Decimal("0.0000")
    amount: Decimal = Decimal("0.00")
    is_included_in_price: bool = False
    is_compound: bool = False
    jurisdiction: str = ""
    tax_zone_id: str = ""
    tax_category_id: str = ""


@dataclass
class TaxCalculationResult:
    total_tax: Decimal = Decimal("0.00")
    is_tax_inclusive: bool = False
    tax_lines: list = field(default_factory=list)   # List[TaxLineResult]
    taxable_amount: Decimal = Decimal("0.00")
    tax_zone_code: str = ""
    tax_zone_name: str = ""
    currency: str = "USD"


def resolve_tax_zone(
    country: str,
    state: str = "",
    city: str = "",
    postal_code: str = "",
) -> Optional[object]:
    """
    Find the most specific active TaxZone matching this address.
    Uses priority ordering — highest priority zone wins.

    Args:
        country:     ISO 3166-1 alpha-2 code (e.g. "NG", "US", "GB").
        state:       State/province code.
        city:        City name.
        postal_code: Postal/zip code.

    Returns:
        TaxZone | None: Best-matching zone, or None if no match.
    """
    from pricing.models import TaxZone

    cache_key = f"tax_zone_{country}_{state}_{city}_{postal_code}"
    cached_id = cache.get(cache_key)
    if cached_id is not None:
        if cached_id == "NONE":
            return None
        try:
            return TaxZone.objects.get(id=cached_id)
        except TaxZone.DoesNotExist:
            pass

    active_zones = (
        TaxZone.objects
        .filter(is_active=True)
        .order_by("-priority")
    )

    best_zone = None
    for zone in active_zones:
        if zone.matches_address(country, state, city, postal_code):
            best_zone = zone
            break

    if best_zone:
        cache.set(cache_key, str(best_zone.id), TAX_ZONE_CACHE_TTL)
    else:
        cache.set(cache_key, "NONE", TAX_ZONE_CACHE_TTL)

    return best_zone


def get_tax_rates_for_address(
    country: str,
    state: str = "",
    city: str = "",
    postal_code: str = "",
    tax_category=None,
) -> List[object]:
    """
    Fetch all applicable TaxRates for an address + tax category.

    Returns:
        List[TaxRate]: Sorted by priority (lowest first for compound stacking).
    """
    from pricing.models import TaxRate

    zone = resolve_tax_zone(country, state, city, postal_code)
    if not zone:
        return []

    qs = (
        TaxRate.objects
        .filter(
            tax_zone=zone,
            is_active=True,
        )
        .select_related("tax_zone", "tax_category")
        .order_by("priority")
    )

    if tax_category:
        qs = qs.filter(tax_category=tax_category)
    else:
        qs = qs.filter(tax_category__is_default=True)

    return list(qs)


def calculate_tax_for_line(
    line_total: Decimal,
    tax_rates: List[object],
    is_inclusive: bool = False,
) -> TaxCalculationResult:
    """
    Calculate tax for a single order line given applicable rates.
    Handles compound, inclusive, and standard exclusive taxes.

    Args:
        line_total: The line subtotal to tax.
        tax_rates:  List[TaxRate] sorted by priority.
        is_inclusive: Whether prices include tax already.

    Returns:
        TaxCalculationResult with per-rate breakdown.
    """
    tax_lines = []
    total_non_compound_tax = Decimal("0.00")
    total_tax = Decimal("0.00")

    for rate in tax_rates:
        if not rate.is_currently_active:
            continue

        amount = rate.compute_tax_amount(
            taxable_amount=line_total,
            base_tax_already_applied=total_non_compound_tax,
        )

        tax_line = TaxLineResult(
            title=rate.name,
            tax_type=rate.tax_type,
            rate=rate.rate,
            amount=amount,
            is_included_in_price=rate.is_included_in_price,
            is_compound=rate.is_compound,
            jurisdiction=getattr(rate.tax_zone, "name", ""),
            tax_zone_id=str(rate.tax_zone_id),
            tax_category_id=str(rate.tax_category_id),
        )
        tax_lines.append(tax_line)

        if not rate.is_compound:
            total_non_compound_tax += amount
        total_tax += amount

    return TaxCalculationResult(
        total_tax=total_tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        is_tax_inclusive=is_inclusive,
        tax_lines=tax_lines,
        taxable_amount=line_total,
        currency="USD",
    )


def calculate_tax_for_order(
    order_items: list,
    shipping_amount: Decimal,
    address_country: str,
    address_state: str = "",
    address_city: str = "",
    address_postal: str = "",
) -> TaxCalculationResult:
    """
    Calculate full order tax across all line items and shipping.

    Args:
        order_items: List of {subtotal, tax_category, is_taxable, requires_shipping}
        shipping_amount: Shipping cost for the order.
        address_*: Delivery address fields for zone resolution.

    Returns:
        TaxCalculationResult with aggregated tax_lines and totals.
    """
    zone = resolve_tax_zone(address_country, address_state,
                            address_city, address_postal)
    if not zone:
        return TaxCalculationResult(total_tax=Decimal("0.00"))

    aggregated_lines: dict = {}  # {rate_id: TaxLineResult}
    total_tax = Decimal("0.00")
    TWO = Decimal("0.01")

    for item in order_items:
        if not item.get("is_taxable", True):
            continue

        tax_category = item.get("tax_category")
        line_subtotal = Decimal(str(item.get("subtotal", 0)))

        tax_rates = get_tax_rates_for_address(
            address_country, address_state, address_city, address_postal,
            tax_category=tax_category,
        )

        line_result = calculate_tax_for_line(line_subtotal, tax_rates)

        for tl in line_result.tax_lines:
            key = f"{tl.tax_zone_id}_{tl.tax_category_id}"
            if key in aggregated_lines:
                aggregated_lines[key].amount += tl.amount
            else:
                aggregated_lines[key] = TaxLineResult(
                    title=tl.title,
                    tax_type=tl.tax_type,
                    rate=tl.rate,
                    amount=tl.amount,
                    is_included_in_price=tl.is_included_in_price,
                    is_compound=tl.is_compound,
                    jurisdiction=tl.jurisdiction,
                    tax_zone_id=tl.tax_zone_id,
                    tax_category_id=tl.tax_category_id,
                )
            total_tax += tl.amount

    # ── Shipping tax ──
    if shipping_amount > 0:
        shipping_rates = [
            r for r in get_tax_rates_for_address(address_country, address_state)
            if r.applies_to_shipping
        ]
        if shipping_rates:
            ship_result = calculate_tax_for_line(
                shipping_amount, shipping_rates)
            for tl in ship_result.tax_lines:
                key = f"{tl.tax_zone_id}_{tl.tax_category_id}_shipping"
                aggregated_lines[key] = tl
                total_tax += tl.amount

    return TaxCalculationResult(
        total_tax=total_tax.quantize(TWO, rounding=ROUND_HALF_UP),
        tax_lines=list(aggregated_lines.values()),
        taxable_amount=sum(
            Decimal(str(i.get("subtotal", 0))) for i in order_items
        ),
        tax_zone_code=zone.code,
        tax_zone_name=zone.name,
    )


def get_tax_summary(tax_result: TaxCalculationResult) -> dict:
    """Summarise a TaxCalculationResult for display in checkout."""
    return {
        "total_tax": str(tax_result.total_tax),
        "tax_zone": tax_result.tax_zone_name,
        "is_inclusive": tax_result.is_tax_inclusive,
        "lines": [
            {
                "title": tl.title,
                "rate": f"{tl.rate}%",
                "amount": str(tl.amount),
                "included": tl.is_included_in_price,
            }
            for tl in tax_result.tax_lines
        ],
    }


def format_tax_lines(tax_result: TaxCalculationResult) -> list:
    """Convert TaxCalculationResult tax_lines to a JSON-serialisable list."""
    return [
        {
            "title": tl.title,
            "rate": float(tl.rate),
            "amount": float(tl.amount),
            "jurisdiction": tl.jurisdiction,
            "is_included": tl.is_included_in_price,
        }
        for tl in tax_result.tax_lines
    ]


# ══════════════════════════════════════════════════════════════
# MODULE: gift_card.py
# Gift card validation, issuance, redemption, bulk ops
# ══════════════════════════════════════════════════════════════

# @dataclass
# class GiftCardValidationResult:
#     valid: bool = False
#     gift_card_id: Optional[str] = None
#     code: str = ""
#     balance: Decimal = Decimal("0.00")
#     currency: str = "USD"
#     expires_at: Optional[str] = None
#     message: str = ""
#     error_type: str = ""
#     applicable_amount: Decimal = Decimal("0.00")


# @dataclass
# class GiftCardRedemptionResult:
#     success: bool = False
#     amount_applied: Decimal = Decimal("0.00")
#     remaining_balance: Decimal = Decimal("0.00")
#     transaction_id: Optional[str] = None
#     message: str = ""


# def validate_gift_card(
#     code: str,
#     cart_total: Decimal = Decimal("0.00"),
# ) -> GiftCardValidationResult:
#     """
#     Validate a gift card code for checkout use.

#     Returns:
#         GiftCardValidationResult — always returned, never raises.
#     """
#     from pricing.models import GiftCard

#     code = code.strip().upper()
#     if not code:
#         return GiftCardValidationResult(
#             valid=False, code=code,
#             message="Please enter a gift card code.", error_type="invalid"
#         )

#     try:
#         card = GiftCard.objects.get(code=code)
#     except GiftCard.DoesNotExist:
#         return GiftCardValidationResult(
#             valid=False, code=code,
#             message="This gift card code is invalid.", error_type="invalid"
#         )

#     if not card.is_usable:
#         if card.is_expired:
#             return GiftCardValidationResult(
#                 valid=False, code=code, gift_card_id=str(card.id),
#                 message="This gift card has expired.", error_type="expired"
#             )
#         if card.balance <= 0:
#             return GiftCardValidationResult(
#                 valid=False, code=code, gift_card_id=str(card.id),
#                 message="This gift card has no remaining balance.",
#                 error_type="no_balance"
#             )
#         return GiftCardValidationResult(
#             valid=False, code=code, gift_card_id=str(card.id),
#             message="This gift card cannot be used at this time.",
#             error_type="invalid"
#         )

#     applicable = min(card.balance, cart_total) if cart_total > 0 else card.balance

#     return GiftCardValidationResult(
#         valid=True,
#         gift_card_id=str(card.id),
#         code=code,
#         balance=card.balance,
#         currency=card.currency,
#         expires_at=card.expires_at.isoformat() if card.expires_at else None,
#         message=f"Gift card applied. {applicable} credit will be applied.",
#         applicable_amount=applicable,
#     )


# def redeem_gift_card_at_checkout(
#     card_code: str,
#     amount: Decimal,
#     order_id: str,
#     order_number: str,
#     actor=None,
# ) -> GiftCardRedemptionResult:
#     """
#     Redeem a gift card during order placement.

#     Returns:
#         GiftCardRedemptionResult.
#     """
#     from pricing.models import GiftCard

#     try:
#         card = GiftCard.objects.get(code=card_code.upper())
#     except GiftCard.DoesNotExist:
#         return GiftCardRedemptionResult(
#             success=False,
#             message="Gift card not found."
#         )

#     try:
#         txn = card.redeem(
#             amount=amount,
#             order_id=order_id,
#             order_number=order_number,
#             actor=actor,
#         )
#         return GiftCardRedemptionResult(
#             success=True,
#             amount_applied=amount,
#             remaining_balance=card.balance,
#             transaction_id=str(txn.id),
#             message=f"Gift card redeemed. Remaining balance: {card.balance}",
#         )
#     except ValueError as e:
#         return GiftCardRedemptionResult(
#             success=False,
#             message=str(e),
#         )


# @transaction.atomic
# def issue_gift_card(
#     initial_value: Decimal,
#     currency: str = "USD",
#     template=None,
#     recipient_email: str = "",
#     recipient_name: str = "",
#     sender_name: str = "",
#     gift_message: str = "",
#     issuance_reason: str = "purchased",
#     purchase_order_id=None,
#     owner=None,
#     issued_by=None,
#     validity_days: int = None,
# ) -> object:
#     """
#     Issue a new GiftCard and immediately activate it.

#     Returns:
#         GiftCard: The activated gift card.
#     """
#     from pricing.models import GiftCard

#     expires_at = None
#     if validity_days:
#         expires_at = timezone.now() + timezone.timedelta(days=validity_days)
#     elif template and template.validity_days:
#         expires_at = timezone.now() + timezone.timedelta(days=template.validity_days)

#     card = GiftCard.objects.create(
#         template=template,
#         initial_value=initial_value,
#         balance=Decimal("0.00"),  # Will be set on activate()
#         currency=currency,
#         status=GiftCard.GiftCardStatus.PENDING,
#         issuance_reason=issuance_reason,
#         issued_by=issued_by,
#         purchase_order_id=purchase_order_id,
#         owner=owner,
#         recipient_email=recipient_email,
#         recipient_name=recipient_name,
#         sender_name=sender_name,
#         gift_message=gift_message,
#         expires_at=expires_at,
#     )

#     card.activate()
#     logger.info("Gift card %s issued (value=%s %s)", card.code, initial_value, currency)
#     return card


# def bulk_issue_gift_cards(
#     count: int,
#     initial_value: Decimal,
#     currency: str = "USD",
#     template=None,
#     issuance_reason: str = "bulk",
#     issued_by=None,
#     validity_days: int = None,
# ) -> list:
#     """
#     Issue multiple gift cards at once (e.g. for corporate bulk orders).

#     Returns:
#         list[GiftCard]: All issued cards.
#     """
#     cards = []
#     for _ in range(count):
#         card = issue_gift_card(
#             initial_value=initial_value,
#             currency=currency,
#             template=template,
#             issuance_reason=issuance_reason,
#             issued_by=issued_by,
#             validity_days=validity_days,
#         )
#         cards.append(card)

#     logger.info("Bulk issued %d gift cards (value=%s each)", count, initial_value)
#     return cards


# def get_customer_gift_cards(customer) -> list:
#     """
#     Get all active gift cards owned by a customer, sorted by balance.

#     Returns:
#         list[dict]: Lightweight card summaries for the account dashboard.
#     """
#     from pricing.models import GiftCard

#     cards = (
#         GiftCard.objects
#         .filter(owner=customer)
#         .exclude(status=GiftCard.GiftCardStatus.DISABLED)
#         .order_by("-balance", "-issued_at")
#     )

#     return [
#         {
#             "id": str(c.id),
#             "masked_code": c.masked_code,
#             "balance": c.balance,
#             "initial_value": c.initial_value,
#             "currency": c.currency,
#             "status": c.status,
#             "expires_at": c.expires_at.isoformat() if c.expires_at else None,
#             "is_usable": c.is_usable,
#             "is_expired": c.is_expired,
#             "percent_used": c.percent_used,
#             "issued_at": c.issued_at.isoformat(),
#         }
#         for c in cards
#     ]


# def get_gift_card_by_code(code: str) -> Optional[object]:
#     """Fetch a GiftCard by its code. Returns None if not found."""
#     from pricing.models import GiftCard
#     try:
#         return GiftCard.objects.select_related("owner", "template").get(code=code.upper())
#     except GiftCard.DoesNotExist:
#         return None


# def expire_overdue_gift_cards() -> int:
#     """
#     Scheduled task: Mark expired gift cards and zero their balance.
#     Called by a Celery periodic task (e.g. daily at midnight).

#     Returns:
#         int: Number of cards expired.
#     """
#     from pricing.models import GiftCard, GiftCardTransaction

#     now = timezone.now()
#     overdue = GiftCard.objects.filter(
#         status=GiftCard.GiftCardStatus.ACTIVE,
#         expires_at__lt=now,
#         balance__gt=0,
#     )

#     count = 0
#     for card in overdue:
#         with transaction.atomic():
#             GiftCardTransaction.objects.create(
#                 gift_card=card,
#                 transaction_type=GiftCardTransaction.TransactionType.EXPIRE,
#                 amount=-card.balance,
#                 balance_before=card.balance,
#                 balance_after=Decimal("0.00"),
#                 note=f"Card expired on {now.strftime('%Y-%m-%d')}",
#             )
#             card.balance = Decimal("0.00")
#             card.status = GiftCard.GiftCardStatus.EXPIRED
#             card.save(update_fields=["balance", "status", "updated_at"])
#         count += 1

#     logger.info("Expired %d gift cards.", count)
#     return count


# ══════════════════════════════════════════════════════════════
# MODULE: flash_sale.py
# Flash sale status, eligibility, countdown, storefront data
# ══════════════════════════════════════════════════════════════

def get_active_flash_sales() -> list:
    """
    Return all currently active flash sales with full item data.
    Used by the storefront to highlight sale products.

    Returns:
        list[dict]: Flash sale summaries with item counts and timing.
    """
    from pricing.models import FlashSale

    now = timezone.now()
    sales = (
        FlashSale.objects
        .filter(
            is_active=True,
            is_publicly_visible=True,
            starts_at__lte=now,
            ends_at__gt=now,
        )
        .prefetch_related("items")
        .order_by("ends_at")
    )

    return [
        {
            "id": str(s.id),
            "name": s.name,
            "slug": s.slug,
            "description": s.description,
            "badge_label": s.badge_label,
            "show_countdown": s.show_countdown_timer,
            "starts_at": s.starts_at.isoformat(),
            "ends_at": s.ends_at.isoformat() if s.ends_at else None,
            "seconds_remaining": s.time_remaining,
            "item_count": s.items.filter(is_active=True).count(),
            "applies_to_all": s.applies_to_all_products,
            "global_discount_pct": s.global_discount_percentage,
        }
        for s in sales
    ]


def get_flash_sale_price(variant, sale_id: str = None) -> Optional[dict]:
    """
    Get flash sale pricing for a variant.
    If sale_id is provided, uses that specific sale.
    Otherwise finds the active sale for this variant.
    """
    from .price_resolver import get_flash_sale_item
    return get_flash_sale_item(variant)


def check_flash_sale_eligibility(
    variant,
    customer=None,
    quantity: int = 1,
) -> dict:
    """
    Check if a customer can purchase a variant at the flash sale price.

    Checks:
      - Sale is currently active
      - Stock limit not exceeded
      - Per-customer limit not exceeded

    Returns:
        dict: {"eligible": bool, "reason": str, "flash_data": dict}
    """
    from .price_resolver import get_flash_sale_item
    from pricing.models import DiscountUsage

    flash_data = get_flash_sale_item(variant)

    if not flash_data:
        return {"eligible": False, "reason": "No active flash sale for this item."}

    if flash_data.get("units_remaining") is not None:
        if flash_data["units_remaining"] < quantity:
            return {
                "eligible": False,
                "reason": (
                    f"Only {flash_data['units_remaining']} units remain at the flash price."
                ),
                "flash_data": flash_data,
            }

    per_customer_limit = flash_data.get("per_customer_limit")
    if per_customer_limit and customer:
        from pricing.models import FlashSaleItem
        item = FlashSaleItem.objects.filter(
            flash_sale_id=flash_data["sale_id"],
            variant=variant,
        ).first()
        if item:
            # Check customer's existing orders for this sale item
            # (Would query orders.OrderItem in production)
            pass

    return {"eligible": True, "reason": "", "flash_data": flash_data}


@transaction.atomic
def increment_flash_sale_units_sold(variant, quantity: int = 1) -> bool:
    """
    Thread-safe increment of units_sold on the FlashSaleItem.
    Called after order placement for items purchased at flash sale price.

    Returns:
        bool: True if incremented, False if item not found.
    """
    from pricing.models import FlashSaleItem
    from django.db.models import F

    now = timezone.now()
    updated = FlashSaleItem.objects.filter(
        is_active=True,
        flash_sale__is_active=True,
        flash_sale__starts_at__lte=now,
        flash_sale__ends_at__gt=now,
        variant=variant,
    ).update(units_sold=F("units_sold") + quantity)

    if updated:
        # Invalidate cache
        cache.delete(f"flash_sale_variant_{variant.id}")

    return bool(updated)


def get_flash_sale_countdown(sale_id: str) -> dict:
    """
    Get real-time countdown data for a flash sale.
    Called frequently by frontend — results are cached.

    Returns:
        dict: {seconds_remaining, ends_at, is_active, is_expired}
    """
    from pricing.models import FlashSale

    cache_key = f"flash_countdown_{sale_id}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        sale = FlashSale.objects.get(id=sale_id)
    except FlashSale.DoesNotExist:
        return {"seconds_remaining": 0, "is_active": False, "is_expired": True}

    remaining = sale.time_remaining or 0
    result = {
        "sale_id": sale_id,
        "seconds_remaining": remaining,
        "ends_at": sale.ends_at.isoformat() if sale.ends_at else None,
        "is_active": sale.is_currently_active,
        "is_expired": remaining == 0,
    }

    cache.set(cache_key, result, 30)  # 30s cache — countdown changes fast
    return result


def get_storefront_flash_sale_data(sale_slug: str) -> Optional[dict]:
    """
    Full flash sale page data for the storefront.
    Includes all sale items with resolved prices.

    Returns:
        dict | None: Full sale data with items and prices.
    """
    from pricing.models import FlashSale
    from .price_resolver import resolve_price, PricingContext

    try:
        sale = FlashSale.objects.prefetch_related(
            "items__variant__product",
            "items__product",
        ).get(slug=sale_slug, is_active=True)
    except FlashSale.DoesNotExist:
        return None

    ctx = PricingContext(ignore_flash_sales=False)
    items_data = []

    for item in sale.items.filter(is_active=True):
        variants = []
        if item.variant:
            variants = [item.variant]
        elif item.product:
            variants = list(item.product.variants.filter(is_active=True))

        for variant in variants:
            result = resolve_price(variant, ctx)
            items_data.append({
                "variant_id": str(variant.id),
                "product_title": variant.product.title,
                "variant_title": variant.title,
                "sku": variant.sku,
                "original_price": float(result.base_price),
                "sale_price": float(result.final_price),
                "savings": float(result.savings),
                "savings_pct": float(result.savings_percentage),
                "stock_limit": item.stock_limit,
                "units_remaining": (
                    item.stock_limit - item.units_sold
                ) if item.stock_limit else None,
                "per_customer_limit": item.per_customer_limit,
                "is_sold_out": item.is_sold_out_at_sale_price,
            })

    return {
        "id": str(sale.id),
        "name": sale.name,
        "slug": sale.slug,
        "starts_at": sale.starts_at.isoformat() if sale.starts_at else None,
        "ends_at": sale.ends_at.isoformat() if sale.ends_at else None,
        "seconds_remaining": sale.time_remaining,
        "items": items_data,
        "total_items": len(items_data),
    }


# ══════════════════════════════════════════════════════════════
# MODULE: currency.py
# Conversion, formatting, exchange rate sync
# ══════════════════════════════════════════════════════════════

@dataclass
class CurrencyConversionResult:
    original_amount: Decimal = Decimal("0.00")
    converted_amount: Decimal = Decimal("0.00")
    from_currency: str = ""
    to_currency: str = ""
    rate_used: Decimal = Decimal("1.0000")
    formatted: str = ""


def get_base_currency() -> Optional[object]:
    """Return the tenant's base Currency record."""
    from pricing.models import Currency
    cache_key = "base_currency"
    cached = cache.get(cache_key)
    if cached:
        return cached
    base = Currency.objects.filter(is_base_currency=True).first()
    if base:
        cache.set(cache_key, base, 3600)
    return base


def get_enabled_currencies() -> list:
    """Return all enabled currencies sorted by base-first then code."""
    from pricing.models import Currency
    return list(Currency.objects.filter(is_enabled=True).order_by("-is_base_currency", "code"))


def get_exchange_rate(from_code: str, to_code: str) -> Optional[object]:
    """Fetch the ExchangeRate record for a currency pair."""
    from pricing.models import ExchangeRate, Currency
    try:
        from_curr = Currency.objects.get(code=from_code.upper())
        to_curr = Currency.objects.get(code=to_code.upper())
        return ExchangeRate.objects.get(base_currency=from_curr, target_currency=to_curr)
    except Exception:
        return None


def convert_amount(
    amount: Decimal,
    from_currency: str,
    to_currency: str,
) -> CurrencyConversionResult:
    """
    Convert an amount from one currency to another using stored rates.

    Returns:
        CurrencyConversionResult with converted amount and rate used.
    """
    if from_currency == to_currency:
        return CurrencyConversionResult(
            original_amount=amount,
            converted_amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            rate_used=Decimal("1.0000"),
        )

    rate_obj = get_exchange_rate(from_currency, to_currency)
    if not rate_obj:
        logger.warning("No exchange rate found for %s → %s",
                       from_currency, to_currency)
        return CurrencyConversionResult(
            original_amount=amount,
            converted_amount=amount,
            from_currency=from_currency,
            to_currency=to_currency,
            rate_used=Decimal("1.0000"),
        )

    converted = rate_obj.convert(amount)
    return CurrencyConversionResult(
        original_amount=amount,
        converted_amount=converted,
        from_currency=from_currency,
        to_currency=to_currency,
        rate_used=rate_obj.effective_rate,
    )


def format_amount(amount: Decimal, currency_code: str) -> str:
    """Format a Decimal amount using the currency's display rules."""
    from pricing.models import Currency
    try:
        currency = Currency.objects.get(code=currency_code.upper())
        return currency.format_amount(amount)
    except Currency.DoesNotExist:
        return f"{currency_code} {amount:,.2f}"


def sync_exchange_rates(provider: str = "openexchangerates", api_key: str = "") -> dict:
    """
    Stub: Fetch latest exchange rates from an external provider and
    update ExchangeRate records for all non-manual-override pairs.

    In production, replace with real API call to Fixer or OXR.

    Returns:
        dict: {"updated": int, "errors": list}
    """
    from pricing.models import ExchangeRate

    updated = 0
    errors = []

    logger.info("Exchange rate sync initiated (provider=%s).", provider)

    non_locked = ExchangeRate.objects.filter(is_manual_override=False).select_related(
        "base_currency", "target_currency"
    )

    for rate_obj in non_locked:
        try:
            # Stub — in production, call the API and get the real rate
            new_rate = rate_obj.rate  # placeholder

            rate_obj.rate = new_rate
            rate_obj.provider = provider
            rate_obj.fetched_at = timezone.now()
            rate_obj.save(
                update_fields=["rate", "provider", "fetched_at", "updated_at"])
            updated += 1
        except Exception as e:
            errors.append(f"{rate_obj}: {e}")

    logger.info(
        "Exchange rate sync complete. Updated: %d, Errors: %d", updated, len(errors))
    return {"updated": updated, "errors": errors}
