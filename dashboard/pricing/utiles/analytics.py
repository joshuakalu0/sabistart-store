"""
pricing/utils/analytics.py
===========================
Pricing-domain analytics: discount performance, promotion ROI,
gift card stats, revenue lift, price list adoption, and tax reporting.

All functions return plain dicts/lists — no Django template coupling.
Heavy queries use .values().annotate() for pure DB aggregation.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import (
    Avg, Count, DecimalField, ExpressionWrapper, F, Q, Sum, Max, Min,
)
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek
from django.utils import timezone

logger = logging.getLogger("pricing.analytics")


# ─────────────────────────────────────────────────────────────
# SECTION 1 — DISCOUNT CODE PERFORMANCE
# ─────────────────────────────────────────────────────────────

def get_discount_performance(
    start: datetime,
    end: datetime,
    code: str = None,
) -> dict:
    """
    Performance metrics for all discount codes (or a specific code)
    within a date range.

    Returns:
        dict: {
            total_uses, total_discount_amount, avg_discount_per_order,
            total_orders_with_discount, avg_order_subtotal,
            unique_customers, revenue_impact (estimated),
            codes: [per-code breakdown]
        }
    """
    from pricing.models import DiscountUsage

    qs = DiscountUsage.objects.filter(
        is_reversed=False,
        used_at__gte=start, used_at__lte=end
    ).select_related("discount_code")

    if code:
        qs = qs.filter(discount_code__code=code.upper())

    aggregate = qs.aggregate(
        total_uses=Count("id"),
        total_discount_amount=Sum("discount_amount"),
        avg_discount=Avg("discount_amount"),
        avg_order_subtotal=Avg("order_subtotal_at_use"),
        unique_customers=Count("customer", distinct=True),
        unique_orders=Count("order_id", distinct=True),
    )

    # Per-code breakdown
    per_code = list(
        qs.values("discount_code__code", "discount_code__title")
        .annotate(
            uses=Count("id"),
            total_discount=Sum("discount_amount"),
            avg_discount=Avg("discount_amount"),
            unique_customers=Count("customer", distinct=True),
            last_used=Max("used_at"),
        )
        .order_by("-total_discount")[:20]
    )

    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "total_uses": aggregate["total_uses"] or 0,
        "total_discount_amount": aggregate["total_discount_amount"] or Decimal("0.00"),
        "avg_discount_per_order": aggregate["avg_discount"] or Decimal("0.00"),
        "avg_order_subtotal": aggregate["avg_order_subtotal"] or Decimal("0.00"),
        "unique_customers": aggregate["unique_customers"] or 0,
        "unique_orders": aggregate["unique_orders"] or 0,
        "codes": [
            {
                "code": row["discount_code__code"],
                "title": row["discount_code__title"],
                "uses": row["uses"],
                "total_discount": row["total_discount"] or Decimal("0.00"),
                "avg_discount": row["avg_discount"] or Decimal("0.00"),
                "unique_customers": row["unique_customers"],
                "last_used": row["last_used"].isoformat() if row["last_used"] else None,
            }
            for row in per_code
        ],
    }


def get_top_discount_codes(
    start: datetime,
    end: datetime,
    metric: str = "total_discount",
    limit: int = 10,
) -> list:
    """
    Rank discount codes by a given metric.

    Args:
        metric: "total_discount" | "uses" | "unique_customers"

    Returns:
        list[dict]: Top codes with full stats.
    """
    from pricing.models import DiscountUsage

    valid_metrics = {
        "total_discount": "-total_discount",
        "uses": "-uses",
        "unique_customers": "-unique_customers",
    }
    order_by = valid_metrics.get(metric, "-total_discount")

    rows = (
        DiscountUsage.objects
        .filter(is_reversed=False, used_at__gte=start, used_at__lte=end)
        .values("discount_code__code", "discount_code__title", "discount_code__value_type")
        .annotate(
            uses=Count("id"),
            total_discount=Sum("discount_amount"),
            unique_customers=Count("customer", distinct=True),
            avg_order_value=Avg("order_subtotal_at_use"),
        )
        .order_by(order_by)[:limit]
    )

    return [
        {
            "rank": i + 1,
            "code": row["discount_code__code"],
            "title": row["discount_code__title"],
            "value_type": row["discount_code__value_type"],
            "uses": row["uses"],
            "total_discount": row["total_discount"] or Decimal("0.00"),
            "unique_customers": row["unique_customers"],
            "avg_order_value": row["avg_order_value"] or Decimal("0.00"),
        }
        for i, row in enumerate(rows)
    ]


def get_discount_usage_over_time(
    start: datetime,
    end: datetime,
    granularity: str = "day",
    code: str = None,
) -> list:
    """
    Discount usage over time for a time-series chart.

    Returns:
        list[dict]: [{"period": str, "uses": int, "discount_amount": Decimal}]
    """
    from pricing.models import DiscountUsage

    trunc_map = {"day": TruncDate, "week": TruncWeek, "month": TruncMonth}
    trunc_fn = trunc_map.get(granularity, TruncDate)

    qs = DiscountUsage.objects.filter(
        is_reversed=False,
        used_at__gte=start,
        used_at__lte=end,
    )
    if code:
        qs = qs.filter(discount_code__code=code.upper())

    rows = (
        qs.annotate(period=trunc_fn("used_at"))
        .values("period")
        .annotate(uses=Count("id"), discount_amount=Sum("discount_amount"))
        .order_by("period")
    )

    return [
        {
            "period": row["period"].strftime("%Y-%m-%d"),
            "uses": row["uses"],
            "discount_amount": row["discount_amount"] or Decimal("0.00"),
        }
        for row in rows
    ]


# ─────────────────────────────────────────────────────────────
# SECTION 2 — AUTOMATIC DISCOUNT PERFORMANCE
# ─────────────────────────────────────────────────────────────

def get_automatic_discount_performance(start: datetime, end: datetime) -> list:
    """
    Compute performance metrics for all automatic discounts.
    Since AutomaticDiscounts don't have usage records like DiscountCode,
    this is computed from order data.

    Returns:
        list[dict]: Performance summary per automatic discount.
    """
    from pricing.models import AutomaticDiscount
    from orders.models import OrderDiscount

    discounts = AutomaticDiscount.objects.filter(is_active=True).values(
        "id", "title", "discount_method", "usage_count", "percentage_value"
    )

    result = []
    for d in discounts:
        order_usage = OrderDiscount.objects.filter(
            discount_id=d["id"],
            discount_type="automatic",
            order__placed_at__gte=start,
            order__placed_at__lte=end,
        ).aggregate(
            total=Sum("amount"),
            count=Count("id"),
        )

        result.append({
            "discount_id": str(d["id"]),
            "title": d["title"],
            "method": d["discount_method"],
            "total_usage_all_time": d["usage_count"],
            "total_discount_in_period": order_usage["total"] or Decimal("0.00"),
            "orders_in_period": order_usage["count"] or 0,
        })

    result.sort(key=lambda x: x["total_discount_in_period"], reverse=True)
    return result


# ─────────────────────────────────────────────────────────────
# SECTION 3 — FLASH SALE PERFORMANCE
# ─────────────────────────────────────────────────────────────

def get_flash_sale_performance(start: datetime, end: datetime) -> list:
    """
    Revenue, units sold, and sell-through rate for flash sales.

    Returns:
        list[dict]: Per-sale performance metrics.
    """
    from pricing.models import FlashSale, FlashSaleItem
    from orders.models import OrderItem

    sales = FlashSale.objects.filter(
        Q(starts_at__gte=start) | Q(ends_at__lte=end)
    ).prefetch_related("items")

    result = []
    for sale in sales:
        # Aggregate units sold and revenue from order items
        order_data = OrderItem.objects.filter(
            order__placed_at__gte=sale.starts_at,
            order__placed_at__lte=sale.ends_at or timezone.now(),
            variant__flash_sale_items__flash_sale=sale,
        ).aggregate(
            total_units=Sum("quantity"),
            total_revenue=Sum("subtotal"),
        )

        total_stock_limit = sum(
            (item.stock_limit or 0) for item in sale.items.all()
        )
        total_units_sold = sum(item.units_sold for item in sale.items.all())

        sell_through = (
            round(total_units_sold / total_stock_limit * 100, 1)
            if total_stock_limit > 0 else None
        )

        result.append({
            "sale_id": str(sale.id),
            "name": sale.name,
            "slug": sale.slug,
            "starts_at": sale.starts_at.isoformat() if sale.starts_at else None,
            "ends_at": sale.ends_at.isoformat() if sale.ends_at else None,
            "is_active": sale.is_currently_active,
            "item_count": sale.items.count(),
            "total_stock_limited": total_stock_limit,
            "units_sold_at_flash_price": total_units_sold,
            "sell_through_pct": sell_through,
            "total_revenue_est": order_data["total_revenue"] or Decimal("0.00"),
            "total_units_est": order_data["total_units"] or 0,
        })

    result.sort(key=lambda x: x["total_revenue_est"], reverse=True)
    return result


# ─────────────────────────────────────────────────────────────
# SECTION 4 — GIFT CARD ANALYTICS
# ─────────────────────────────────────────────────────────────

def get_gift_card_stats(start: datetime, end: datetime) -> dict:
    """
    Gift card issuance, redemption, and outstanding liability stats.

    Returns:
        dict: {
            issued_count, total_issued_value, redeemed_count,
            total_redeemed_value, outstanding_liability,
            avg_redemption_value, expiry_breakdown, by_issuance_reason
        }
    """
    from pricing.models import GiftCard, GiftCardTransaction

    issued_in_period = GiftCard.objects.filter(issued_at__gte=start, issued_at__lte=end)
    issued_agg = issued_in_period.aggregate(
        count=Count("id"),
        total_value=Sum("initial_value"),
        avg_value=Avg("initial_value"),
    )

    redeemed_txns = GiftCardTransaction.objects.filter(
        transaction_type="debit",
        created_at__gte=start,
        created_at__lte=end,
    ).aggregate(
        count=Count("id"),
        total_redeemed=Sum("amount"),  # negative values
    )

    # Outstanding liability = sum of all active card balances
    outstanding = GiftCard.objects.filter(
        status="active"
    ).aggregate(liability=Sum("balance"))

    # Expiry breakdown
    now = timezone.now()
    expiring_30d = GiftCard.objects.filter(
        status="active",
        expires_at__gte=now,
        expires_at__lte=now + timedelta(days=30),
    ).aggregate(count=Count("id"), value=Sum("balance"))

    expiring_90d = GiftCard.objects.filter(
        status="active",
        expires_at__gte=now,
        expires_at__lte=now + timedelta(days=90),
    ).aggregate(count=Count("id"), value=Sum("balance"))

    # By issuance reason
    by_reason = list(
        issued_in_period
        .values("issuance_reason")
        .annotate(count=Count("id"), total_value=Sum("initial_value"))
        .order_by("-count")
    )

    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "issued_count": issued_agg["count"] or 0,
        "total_issued_value": issued_agg["total_value"] or Decimal("0.00"),
        "avg_issued_value": issued_agg["avg_value"] or Decimal("0.00"),
        "redeemed_transactions": redeemed_txns["count"] or 0,
        "total_redeemed_value": abs(redeemed_txns["total_redeemed"] or Decimal("0.00")),
        "outstanding_liability": outstanding["liability"] or Decimal("0.00"),
        "expiring_30d": {
            "count": expiring_30d["count"] or 0,
            "value": expiring_30d["value"] or Decimal("0.00"),
        },
        "expiring_90d": {
            "count": expiring_90d["count"] or 0,
            "value": expiring_90d["value"] or Decimal("0.00"),
        },
        "by_issuance_reason": by_reason,
    }


# ─────────────────────────────────────────────────────────────
# SECTION 5 — PRICE LIST & PROMOTION ROI
# ─────────────────────────────────────────────────────────────

def get_revenue_by_price_list(start: datetime, end: datetime) -> list:
    """
    Revenue breakdown by price list to measure B2B pricing performance.

    Returns:
        list[dict]: [{price_list_name, orders, revenue, avg_order_value}]
    """
    from orders.models import Order, OrderDiscount

    rows = (
        OrderDiscount.objects
        .filter(
            discount_type="code",
            order__placed_at__gte=start,
            order__placed_at__lte=end,
            order__financial_status__in=["paid", "partially_refunded"],
        )
        .values("description")
        .annotate(
            orders=Count("order", distinct=True),
            total_discount=Sum("amount"),
            avg_discount=Avg("amount"),
        )
        .order_by("-orders")[:15]
    )

    return [
        {
            "price_list_name": row["description"],
            "orders": row["orders"],
            "total_discount": row["total_discount"] or Decimal("0.00"),
            "avg_discount": row["avg_discount"] or Decimal("0.00"),
        }
        for row in rows
    ]


def get_promotion_roi(start: datetime, end: datetime) -> list:
    """
    Estimate ROI for each promotion type by comparing discount cost
    against the revenue generated during the promotion window.

    Returns:
        list[dict]: Promotions sorted by estimated ROI.
    """
    from pricing.models import FlashSale
    from orders.models import Order

    result = []

    # Flash sale ROI
    sales = FlashSale.objects.filter(
        Q(starts_at__gte=start) | Q(ends_at__lte=end)
    )
    for sale in sales:
        sale_revenue = Order.objects.filter(
            placed_at__gte=sale.starts_at,
            placed_at__lte=sale.ends_at or timezone.now(),
            financial_status__in=["paid", "partially_refunded"],
        ).aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")

        discount_cost = Order.objects.filter(
            placed_at__gte=sale.starts_at,
            placed_at__lte=sale.ends_at or timezone.now(),
        ).aggregate(total=Sum("total_discounts"))["total"] or Decimal("0.00")

        roi = (
            round(float((sale_revenue - discount_cost) / discount_cost * 100), 1)
            if discount_cost > 0 else None
        )

        result.append({
            "promotion_type": "flash_sale",
            "promotion_name": sale.name,
            "promotion_id": str(sale.id),
            "revenue_generated": sale_revenue,
            "discount_cost": discount_cost,
            "net_revenue": sale_revenue - discount_cost,
            "roi_pct": roi,
        })

    result.sort(key=lambda x: (x["roi_pct"] or 0), reverse=True)
    return result


def get_price_list_adoption(start: datetime, end: datetime) -> list:
    """
    Measure how many customers are on each price list and their order volume.

    Returns:
        list[dict]: Price list adoption metrics.
    """
    from pricing.models import PriceList, PriceListCustomerGroup

    result = []
    price_lists = PriceList.objects.filter(is_active=True).order_by("-priority")

    for pl in price_lists:
        assigned_customers = PriceListCustomerGroup.objects.filter(
            price_list=pl
        ).count()

        result.append({
            "price_list_id": str(pl.id),
            "name": pl.name,
            "code": pl.code,
            "type": pl.price_list_type,
            "priority": pl.priority,
            "assigned_customer_groups_or_customers": assigned_customers,
            "is_public": pl.is_public,
            "is_active": pl.is_active,
        })

    return result


# ─────────────────────────────────────────────────────────────
# SECTION 6 — TAX ANALYTICS
# ─────────────────────────────────────────────────────────────

def get_tax_collected_by_zone(start: datetime, end: datetime) -> list:
    """
    Total tax collected per tax zone for the period.
    Used for tax filing and remittance reporting.

    Returns:
        list[dict]: [{zone_name, zone_code, tax_type, total_tax, order_count}]
    """
    from orders.models import OrderTax

    rows = (
        OrderTax.objects
        .filter(
            order__placed_at__gte=start,
            order__placed_at__lte=end,
            order__financial_status__in=["paid", "partially_refunded"],
        )
        .values("title", "jurisdiction")
        .annotate(
            total_tax=Sum("amount"),
            order_count=Count("order", distinct=True),
            avg_rate=Avg("rate"),
        )
        .order_by("-total_tax")
    )

    return [
        {
            "tax_title": row["title"],
            "jurisdiction": row["jurisdiction"],
            "total_tax_collected": row["total_tax"] or Decimal("0.00"),
            "order_count": row["order_count"],
            "avg_rate": row["avg_rate"] or Decimal("0"),
        }
        for row in rows
    ]
