"""
pricing/utils/dashboard.py
===========================
High-level pricing dashboard aggregation functions.
Powers the pricing & promotions section of the staff dashboard:
KPI cards, health checks, promotion status, expiry warnings,
gift card liability, and the attention queue.
"""

import logging
from decimal import Decimal

from django.db.models import Count, Q, Sum, Avg, F
from django.utils import timezone

logger = logging.getLogger("pricing.dashboard")


# ─────────────────────────────────────────────────────────────
# SECTION 1 — PRICING KPI CARDS
# ─────────────────────────────────────────────────────────────

def get_pricing_dashboard_kpis(period_days: int = 30) -> dict:
    """
    All top-level KPI cards for the Pricing & Promotions dashboard tab.

    Returns:
        dict: {
            discount_codes_active, total_discount_given,
            avg_discount_rate, gift_card_liability,
            active_promotions, flash_sales_live,
            conversion_lift_est, ...
        }
    """
    from pricing.models import (
        DiscountCode, AutomaticDiscount, FlashSale, GiftCard, PriceList
    )
    from pricing.models import DiscountUsage

    now = timezone.now()
    period_start = now - timezone.timedelta(days=period_days)
    prev_start = period_start - timezone.timedelta(days=period_days)

    # ── Discount codes ──
    active_codes = DiscountCode.objects.filter(is_active=True).count()
    codes_expiring_soon = DiscountCode.objects.filter(
        is_active=True,
        ends_at__gte=now,
        ends_at__lte=now + timezone.timedelta(days=7),
    ).count()

    # ── Discount given in period ──
    period_discount = DiscountUsage.objects.filter(
        is_reversed=False,
        used_at__gte=period_start
    ).aggregate(total=Sum("discount_amount"), count=Count("id"))

    prev_discount = DiscountUsage.objects.filter(
        is_reversed=False,
        used_at__gte=prev_start,
        used_at__lt=period_start,
    ).aggregate(total=Sum("discount_amount"))

    curr_total = period_discount["total"] or Decimal("0.00")
    prev_total = prev_discount["total"] or Decimal("0.00")
    discount_change_pct = (
        round(float((curr_total - prev_total) / prev_total * 100), 1)
        if prev_total > 0 else 0.0
    )

    # ── Gift card outstanding liability ──
    gc_liability = GiftCard.objects.filter(
        status="active"
    ).aggregate(total=Sum("balance"))["total"] or Decimal("0.00")

    # ── Active promotions ──
    active_auto = AutomaticDiscount.objects.filter(
        is_active=True,
    ).filter(
        Q(starts_at__isnull=True) | Q(starts_at__lte=now)
    ).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now)
    ).count()

    # ── Flash sales ──
    live_flash_sales = FlashSale.objects.filter(
        is_active=True,
        starts_at__lte=now,
        ends_at__gt=now,
    ).count()

    # ── Active price lists ──
    active_price_lists = PriceList.objects.filter(is_active=True).count()

    # ── Avg discount rate ──
    avg_discount_pct = DiscountCode.objects.filter(
        is_active=True,
        value_type="percentage",
    ).aggregate(avg=Avg("percentage_value"))["avg"] or Decimal("0.00")

    def _block(value, prev=None, format_as="number"):
        change = 0.0
        if prev is not None and prev != 0:
            change = round(float(value - prev) / float(prev) * 100, 1)
        return {
            "value": value,
            "change_pct": change,
            "trend": "up" if change > 0 else "down" if change < 0 else "flat",
            "format": format_as,
        }

    return {
        "period_days": period_days,
        "generated_at": now.isoformat(),
        "active_discount_codes": _block(active_codes, format_as="integer"),
        "codes_expiring_7d": codes_expiring_soon,
        "total_discount_given": _block(curr_total, prev_total, "currency"),
        "discount_order_count": period_discount["count"] or 0,
        "avg_discount_percentage": avg_discount_pct,
        "gift_card_liability": _block(gc_liability, format_as="currency"),
        "active_auto_discounts": active_auto,
        "live_flash_sales": live_flash_sales,
        "active_price_lists": active_price_lists,
        "discount_change_pct": discount_change_pct,
    }


# ─────────────────────────────────────────────────────────────
# SECTION 2 — ACTIVE PROMOTIONS SUMMARY
# ─────────────────────────────────────────────────────────────

def get_active_promotions_summary() -> dict:
    """
    All currently active promotions grouped by type.
    Used for the "Active Promotions" panel on the dashboard.

    Returns:
        dict: {discount_codes, automatic_discounts, flash_sales,
               buy_x_get_y, total_active}
    """
    from pricing.models import (
        DiscountCode, AutomaticDiscount, FlashSale, BuyXGetYPromotion
    )

    now = timezone.now()
    date_filter = (
        Q(starts_at__isnull=True) | Q(starts_at__lte=now)
    ) & (
        Q(ends_at__isnull=True) | Q(ends_at__gt=now)
    )

    # ── Active Discount Codes ──
    codes = DiscountCode.objects.filter(is_active=True).filter(date_filter).values(
        "code", "title", "value_type", "usage_count", "usage_limit", "ends_at"
    ).order_by("-usage_count")[:10]

    # ── Active Automatic Discounts ──
    auto_discounts = AutomaticDiscount.objects.filter(
        is_active=True
    ).filter(date_filter).values(
        "id", "title", "discount_method", "percentage_value", "priority", "usage_count"
    ).order_by("-priority")[:10]

    # ── Live Flash Sales ──
    flash = FlashSale.objects.filter(
        is_active=True,
        starts_at__lte=now,
        ends_at__gt=now,
    ).values("id", "name", "ends_at", "badge_label").annotate(
        item_count=Count("items")
    ).order_by("ends_at")[:5]

    # ── Active BXGY ──
    bxgy = BuyXGetYPromotion.objects.filter(
        is_active=True
    ).filter(date_filter).values(
        "id", "title", "buy_quantity", "get_quantity",
        "get_discount_percentage", "usage_count"
    ).order_by("-usage_count")[:5]

    total = (
        len(list(codes)) + len(list(auto_discounts)) +
        len(list(flash)) + len(list(bxgy))
    )

    return {
        "discount_codes": list(codes),
        "automatic_discounts": list(auto_discounts),
        "flash_sales": [
            {
                **f,
                "ends_at": f["ends_at"].isoformat() if f.get("ends_at") else None,
                "seconds_remaining": max(
                    0,
                    int((f["ends_at"] - now).total_seconds())
                ) if f.get("ends_at") else None,
            }
            for f in flash
        ],
        "buy_x_get_y": list(bxgy),
        "total_active": total,
        "generated_at": now.isoformat(),
    }


# ─────────────────────────────────────────────────────────────
# SECTION 3 — DISCOUNT CODES NEEDING ATTENTION
# ─────────────────────────────────────────────────────────────

def get_discount_codes_needing_attention() -> dict:
    """
    Identify discount codes that require staff review.
    Grouped by issue type.

    Issues:
      - Near usage limit (>80% used)
      - Expiring within 48 hours
      - Possibly fraudulent (IP clustering)
      - Zero uses (stale/untested codes)
      - Unlimited + no expiry (security concern)

    Returns:
        dict: {near_limit, expiring_soon, zero_usage, unlimited_no_expiry, totals}
    """
    from pricing.models import DiscountCode

    now = timezone.now()
    in_48h = now + timezone.timedelta(hours=48)
    active = DiscountCode.objects.filter(is_active=True)

    # Near usage limit (>80% consumed)
    near_limit = list(
        active
        .filter(usage_limit__isnull=False, usage_limit__gt=0)
        .extra(
            where=["usage_count::float / usage_limit::float >= 0.8"]
        )
        .values("code", "title", "usage_count", "usage_limit", "ends_at")
        .order_by("-usage_count")[:20]
    )

    # Expiring within 48 hours
    expiring_soon = list(
        active
        .filter(ends_at__gte=now, ends_at__lte=in_48h)
        .values("code", "title", "ends_at", "usage_count")
        .order_by("ends_at")
    )

    # Zero uses, created >7 days ago
    stale_cutoff = now - timezone.timedelta(days=7)
    zero_usage = list(
        active
        .filter(usage_count=0, created_at__lt=stale_cutoff)
        .values("code", "title", "created_at", "ends_at")
        .order_by("created_at")[:20]
    )

    # Unlimited + no expiry (potential risk)
    unlimited_no_expiry = list(
        active
        .filter(usage_limit__isnull=True, ends_at__isnull=True)
        .values("code", "title", "usage_count", "created_at")
        .order_by("-usage_count")[:10]
    )

    return {
        "near_limit": _format_codes_list(near_limit),
        "expiring_soon": _format_codes_list(expiring_soon),
        "zero_usage": _format_codes_list(zero_usage),
        "unlimited_no_expiry": _format_codes_list(unlimited_no_expiry),
        "totals": {
            "near_limit": len(near_limit),
            "expiring_soon": len(expiring_soon),
            "zero_usage": len(zero_usage),
            "unlimited_no_expiry": len(unlimited_no_expiry),
            "total_issues": (
                len(near_limit) + len(expiring_soon) +
                len(zero_usage) + len(unlimited_no_expiry)
            ),
        },
    }


# ─────────────────────────────────────────────────────────────
# SECTION 4 — EXPIRING PROMOTIONS
# ─────────────────────────────────────────────────────────────

def get_expiring_promotions(days_ahead: int = 7) -> dict:
    """
    All promotions expiring within the next N days.
    Used to show a warning banner in the dashboard.

    Returns:
        dict: {discount_codes, automatic_discounts, flash_sales,
               total_expiring, earliest_expiry}
    """
    from pricing.models import DiscountCode, AutomaticDiscount, FlashSale

    now = timezone.now()
    cutoff = now + timezone.timedelta(days=days_ahead)

    expiring_codes = list(
        DiscountCode.objects.filter(
            is_active=True,
            ends_at__gte=now,
            ends_at__lte=cutoff,
        ).values("code", "title", "ends_at", "usage_count").order_by("ends_at")
    )

    expiring_auto = list(
        AutomaticDiscount.objects.filter(
            is_active=True,
            ends_at__gte=now,
            ends_at__lte=cutoff,
        ).values("id", "title", "ends_at", "priority").order_by("ends_at")
    )

    expiring_flash = list(
        FlashSale.objects.filter(
            is_active=True,
            ends_at__gte=now,
            ends_at__lte=cutoff,
        ).values("id", "name", "ends_at").order_by("ends_at")
    )

    all_expiries = (
        [c.get("ends_at") for c in expiring_codes] +
        [a.get("ends_at") for a in expiring_auto] +
        [f.get("ends_at") for f in expiring_flash]
    )
    earliest = min((e for e in all_expiries if e), default=None)

    return {
        "discount_codes": _format_expiry_list(expiring_codes),
        "automatic_discounts": _format_expiry_list(expiring_auto),
        "flash_sales": _format_expiry_list(expiring_flash),
        "total_expiring": (
            len(expiring_codes) + len(expiring_auto) + len(expiring_flash)
        ),
        "earliest_expiry": earliest.isoformat() if earliest else None,
        "days_ahead": days_ahead,
    }


# ─────────────────────────────────────────────────────────────
# SECTION 5 — FLASH SALE LIVE STATUS
# ─────────────────────────────────────────────────────────────

def get_flash_sales_live_status() -> list:
    """
    Real-time status of all currently running flash sales.
    Used for the live monitoring panel.

    Returns:
        list[dict]: [{name, seconds_remaining, sell_through_pct,
                      items_sold_out, units_remaining_total}]
    """
    from pricing.models import FlashSale

    now = timezone.now()
    live_sales = FlashSale.objects.filter(
        is_active=True,
        starts_at__lte=now,
        ends_at__gt=now,
    ).prefetch_related("items")

    result = []
    for sale in live_sales:
        items = list(sale.items.filter(is_active=True))
        total_limit = sum(i.stock_limit or 0 for i in items if i.stock_limit)
        total_sold = sum(i.units_sold for i in items)
        sold_out_items = sum(1 for i in items if i.is_sold_out_at_sale_price)
        units_remaining = sum(
            (i.stock_limit - i.units_sold)
            for i in items
            if i.stock_limit and not i.is_sold_out_at_sale_price
        )

        sell_through = (
            round(total_sold / total_limit * 100, 1) if total_limit > 0 else None
        )

        result.append({
            "sale_id": str(sale.id),
            "name": sale.name,
            "slug": sale.slug,
            "ends_at": sale.ends_at.isoformat(),
            "seconds_remaining": sale.time_remaining,
            "total_items": len(items),
            "sold_out_items": sold_out_items,
            "units_remaining": units_remaining if total_limit > 0 else None,
            "sell_through_pct": sell_through,
            "is_fully_sold_out": sold_out_items == len(items) and len(items) > 0,
        })

    result.sort(key=lambda x: x["seconds_remaining"] or 0)
    return result


# ─────────────────────────────────────────────────────────────
# SECTION 6 — GIFT CARD BALANCE SUMMARY
# ─────────────────────────────────────────────────────────────

def get_gift_card_balance_summary() -> dict:
    """
    Current gift card liability and usage summary for the financial panel.

    Returns:
        dict: {total_active, total_liability, expiring_soon,
               issued_today, redeemed_today, fully_redeemed_all_time}
    """
    from pricing.models import GiftCard, GiftCardTransaction

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    active_agg = GiftCard.objects.filter(status="active").aggregate(
        count=Count("id"),
        liability=Sum("balance"),
        avg_balance=Avg("balance"),
    )

    expiring_30d = GiftCard.objects.filter(
        status="active",
        expires_at__gte=now,
        expires_at__lte=now + timezone.timedelta(days=30),
    ).aggregate(count=Count("id"), value=Sum("balance"))

    issued_today = GiftCard.objects.filter(
        issued_at__gte=today_start
    ).aggregate(count=Count("id"), value=Sum("initial_value"))

    redeemed_today = GiftCardTransaction.objects.filter(
        transaction_type="debit",
        created_at__gte=today_start,
    ).aggregate(count=Count("id"), value=Sum("amount"))

    fully_redeemed = GiftCard.objects.filter(status="redeemed").count()

    return {
        "total_active_cards": active_agg["count"] or 0,
        "total_liability": active_agg["liability"] or Decimal("0.00"),
        "avg_active_balance": active_agg["avg_balance"] or Decimal("0.00"),
        "expiring_30d_count": expiring_30d["count"] or 0,
        "expiring_30d_value": expiring_30d["value"] or Decimal("0.00"),
        "issued_today": {
            "count": issued_today["count"] or 0,
            "value": issued_today["value"] or Decimal("0.00"),
        },
        "redeemed_today": {
            "count": redeemed_today["count"] or 0,
            "value": abs(redeemed_today["value"] or Decimal("0.00")),
        },
        "fully_redeemed_all_time": fully_redeemed,
    }


# ─────────────────────────────────────────────────────────────
# SECTION 7 — TOP PERFORMING PROMOTIONS
# ─────────────────────────────────────────────────────────────

def get_top_performing_promotions(period_days: int = 30, limit: int = 5) -> list:
    """
    Rank all promotion types by total discount amount in the period.
    Combines coupon codes, auto discounts, and flash sales into one leaderboard.

    Returns:
        list[dict]: Top promotions across all types, sorted by impact.
    """
    from pricing.models import DiscountUsage
    from orders.models import OrderDiscount

    now = timezone.now()
    period_start = now - timezone.timedelta(days=period_days)

    # Coupon codes
    code_rows = list(
        DiscountUsage.objects
        .filter(is_reversed=False, used_at__gte=period_start)
        .values("discount_code__code", "discount_code__title")
        .annotate(
            total=Sum("discount_amount"),
            uses=Count("id"),
        )
        .order_by("-total")[:limit]
    )

    # Auto discounts + other order discounts
    auto_rows = list(
        OrderDiscount.objects
        .filter(
            discount_type="automatic",
            order__placed_at__gte=period_start,
            order__financial_status__in=["paid", "partially_refunded"],
        )
        .values("description")
        .annotate(total=Sum("amount"), uses=Count("id"))
        .order_by("-total")[:limit]
    )

    combined = []
    for row in code_rows:
        combined.append({
            "type": "discount_code",
            "name": row["discount_code__title"] or row["discount_code__code"],
            "code": row["discount_code__code"],
            "total_discount": row["total"] or Decimal("0.00"),
            "uses": row["uses"],
        })

    for row in auto_rows:
        combined.append({
            "type": "automatic_discount",
            "name": row["description"],
            "code": "",
            "total_discount": row["total"] or Decimal("0.00"),
            "uses": row["uses"],
        })

    combined.sort(key=lambda x: x["total_discount"], reverse=True)
    return combined[:limit]


# ─────────────────────────────────────────────────────────────
# SECTION 8 — PRICING HEALTH CHECKS
# ─────────────────────────────────────────────────────────────

def get_pricing_health_checks() -> list:
    """
    Configuration health checks for the pricing system.
    Surfaces misconfigurations before they cause customer-facing bugs.

    Returns:
        list[dict]: [{"check": str, "status": "ok|warning|error", "message": str}]
    """
    from pricing.models import (
        Currency, TaxZone, TaxRate, PriceList, DiscountCode, GiftCard
    )

    checks = []
    now = timezone.now()

    # ── Base currency configured ──
    base_currency = Currency.objects.filter(is_base_currency=True).first()
    if base_currency:
        checks.append({
            "check": "base_currency",
            "status": "ok",
            "message": f"Base currency set to {base_currency.code}.",
        })
    else:
        checks.append({
            "check": "base_currency",
            "status": "error",
            "message": "No base currency configured. All monetary calculations will fail.",
        })

    # ── Default tax category exists ──
    from pricing.models import TaxCategory
    default_tax_cat = TaxCategory.objects.filter(is_default=True, is_taxable=True).first()
    if default_tax_cat:
        checks.append({
            "check": "default_tax_category",
            "status": "ok",
            "message": f"Default tax category: {default_tax_cat.name}.",
        })
    else:
        checks.append({
            "check": "default_tax_category",
            "status": "warning",
            "message": "No default tax category set. Tax-unclassified products won't be taxed.",
        })

    # ── At least one active tax zone ──
    active_zones = TaxZone.objects.filter(is_active=True).count()
    if active_zones > 0:
        checks.append({
            "check": "tax_zones",
            "status": "ok",
            "message": f"{active_zones} active tax zone(s) configured.",
        })
    else:
        checks.append({
            "check": "tax_zones",
            "status": "warning",
            "message": "No tax zones configured. Tax will not be calculated.",
        })

    # ── No discount codes with 0 value ──
    zero_value_codes = DiscountCode.objects.filter(
        is_active=True,
        value_type__in=["percentage", "fixed_amount"],
        percentage_value__isnull=True,
        fixed_amount__isnull=True,
    ).count()
    if zero_value_codes == 0:
        checks.append({
            "check": "discount_code_values",
            "status": "ok",
            "message": "All active discount codes have valid values.",
        })
    else:
        checks.append({
            "check": "discount_code_values",
            "status": "error",
            "message": (
                f"{zero_value_codes} active discount code(s) have no value set — "
                f"they will apply a 0% / $0 discount."
            ),
        })

    # ── Gift cards with negative balance ──
    negative_gc = GiftCard.objects.filter(balance__lt=0).count()
    if negative_gc == 0:
        checks.append({
            "check": "gift_card_balances",
            "status": "ok",
            "message": "No gift cards with negative balances.",
        })
    else:
        checks.append({
            "check": "gift_card_balances",
            "status": "error",
            "message": (
                f"{negative_gc} gift card(s) have negative balances — data integrity issue."
            ),
        })

    # ── Active flash sales with no items ──
    from pricing.models import FlashSale
    empty_flash_sales = FlashSale.objects.filter(
        is_active=True,
        applies_to_all_products=False,
        ends_at__gt=now,
    ).annotate(item_count=Count("items")).filter(item_count=0).count()

    if empty_flash_sales == 0:
        checks.append({
            "check": "flash_sale_items",
            "status": "ok",
            "message": "All active flash sales have items configured.",
        })
    else:
        checks.append({
            "check": "flash_sale_items",
            "status": "warning",
            "message": (
                f"{empty_flash_sales} active flash sale(s) have no items — "
                f"they won't discount anything."
            ),
        })

    return checks


# ─────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────

def _format_codes_list(rows: list) -> list:
    """Format raw QuerySet rows for display."""
    result = []
    for row in rows:
        formatted = dict(row)
        for key in ("created_at", "ends_at", "last_used"):
            if key in formatted and formatted[key]:
                formatted[key] = formatted[key].isoformat()
        result.append(formatted)
    return result


def _format_expiry_list(rows: list) -> list:
    """Format rows with ends_at as ISO string."""
    result = []
    for row in rows:
        formatted = dict(row)
        if "ends_at" in formatted and formatted["ends_at"]:
            ends = formatted["ends_at"]
            formatted["ends_at"] = ends.isoformat()
            now = timezone.now()
            formatted["hours_remaining"] = round(
                (ends - now).total_seconds() / 3600, 1
            )
        result.append(formatted)
    return result
