"""
orders/utils/analytics.py
==========================
Time-series revenue, order volume, funnel conversion, product performance,
customer analytics, geographic breakdowns, and cohort retention.

All functions return plain dicts/lists — no Django template coupling.
Results are designed to be consumed directly by chart widgets (Chart.js,
Recharts, ApexCharts) or serialized as JSON in API responses.

Performance notes:
  - All aggregate queries use .values() + annotate() — no Python-level loops.
  - Heavy queries are cache-eligible; callers should add cache wrappers.
  - Date truncation uses Django's TruncDay/TruncWeek/TruncMonth for DB-level grouping.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import (
    Avg, Count, DecimalField, ExpressionWrapper, F, Max, Min,
    OuterRef, Q, Subquery, Sum, Value,
)
from django.db.models.functions import (
    TruncDate, TruncHour, TruncMonth, TruncWeek,
)
from django.utils import timezone

logger = logging.getLogger("orders.analytics")

# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _date_range(start: datetime, end: datetime, granularity: str) -> list:
    """Generate a complete list of period labels to fill gaps in data."""
    periods = []
    current = start.date()
    end_date = end.date()

    if granularity == "hour":
        current_dt = start
        while current_dt <= end:
            periods.append(current_dt.strftime("%Y-%m-%d %H:00"))
            current_dt += timedelta(hours=1)
    elif granularity == "day":
        while current <= end_date:
            periods.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
    elif granularity == "week":
        while current <= end_date:
            periods.append(current.strftime("%Y-W%W"))
            current += timedelta(weeks=1)
    elif granularity == "month":
        while current <= end_date:
            periods.append(current.strftime("%Y-%m"))
            current = (current.replace(day=1) + timedelta(days=32)).replace(day=1)

    return periods


def _fill_time_gaps(data_dict: dict, periods: list, default: Decimal = Decimal("0.00")) -> list:
    """Fill missing periods with default values for continuous chart lines."""
    return [{"period": p, "value": data_dict.get(p, default)} for p in periods]


def _get_paid_orders_qs(start: datetime, end: datetime):
    """Base queryset: paid, non-test orders within date range."""
    from orders.models import Order
    return Order.objects.filter(
        financial_status__in=[
            Order.FinancialStatus.PAID,
            Order.FinancialStatus.PARTIALLY_REFUNDED,
        ],
        is_test=False,
        placed_at__gte=start,
        placed_at__lte=end,
    )


def _resolve_granularity(start: datetime, end: datetime) -> str:
    """Auto-pick granularity based on date range size."""
    delta = (end - start).days
    if delta <= 2:
        return "hour"
    elif delta <= 90:
        return "day"
    elif delta <= 365:
        return "week"
    else:
        return "month"


# ─────────────────────────────────────────────────────────────
# SECTION 1 — REVENUE
# ─────────────────────────────────────────────────────────────

def get_revenue_over_time(
    start: datetime,
    end: datetime,
    granularity: str = "auto",
    include_refunds: bool = True,
) -> dict:
    """
    Gross and net revenue aggregated by time period.

    Returns:
        dict: {
            "granularity": str,
            "total_gross": Decimal,
            "total_net": Decimal,
            "total_refunded": Decimal,
            "series": [{"period": str, "gross": Decimal, "net": Decimal, "refunded": Decimal}]
        }
    """
    if granularity == "auto":
        granularity = _resolve_granularity(start, end)

    trunc_fn_map = {
        "hour": TruncHour,
        "day": TruncDate,
        "week": TruncWeek,
        "month": TruncMonth,
    }
    trunc_fn = trunc_fn_map.get(granularity, TruncDate)

    qs = _get_paid_orders_qs(start, end).annotate(
        period=trunc_fn("placed_at")
    ).values("period").annotate(
        gross=Sum("total_price"),
        refunded=Sum("total_refunded"),
    ).order_by("period")

    series = []
    total_gross = Decimal("0.00")
    total_refunded = Decimal("0.00")

    # Build lookup dict first, then fill gaps
    data_lookup = {}
    for row in qs:
        period_key = row["period"].strftime(
            "%Y-%m-%d %H:00" if granularity == "hour"
            else "%Y-%m-%d" if granularity == "day"
            else "%Y-W%W" if granularity == "week"
            else "%Y-%m"
        )
        gross = row["gross"] or Decimal("0.00")
        refunded = row["refunded"] or Decimal("0.00")
        net = gross - refunded
        data_lookup[period_key] = {"gross": gross, "refunded": refunded, "net": net}
        total_gross += gross
        total_refunded += refunded

    periods = _date_range(start, end, granularity)
    for period in periods:
        d = data_lookup.get(period, {"gross": Decimal("0.00"), "refunded": Decimal("0.00"), "net": Decimal("0.00")})
        series.append({"period": period, **d})

    return {
        "granularity": granularity,
        "total_gross": total_gross,
        "total_net": total_gross - total_refunded,
        "total_refunded": total_refunded,
        "series": series,
    }


# ─────────────────────────────────────────────────────────────
# SECTION 2 — ORDER VOLUME
# ─────────────────────────────────────────────────────────────

def get_orders_over_time(
    start: datetime,
    end: datetime,
    granularity: str = "auto",
) -> dict:
    """
    Order count and average order value over time.

    Returns:
        dict: {
            "total_orders": int,
            "avg_order_value": Decimal,
            "series": [{"period": str, "count": int, "avg_value": Decimal}]
        }
    """
    if granularity == "auto":
        granularity = _resolve_granularity(start, end)

    trunc_map = {"hour": TruncHour, "day": TruncDate, "week": TruncWeek, "month": TruncMonth}
    trunc_fn = trunc_map.get(granularity, TruncDate)

    qs = _get_paid_orders_qs(start, end).annotate(
        period=trunc_fn("placed_at")
    ).values("period").annotate(
        count=Count("id"),
        total=Sum("total_price"),
    ).order_by("period")

    total_orders = 0
    total_revenue = Decimal("0.00")
    data_lookup = {}

    for row in qs:
        fmt = "%Y-%m-%d" if granularity in ("day", "hour") else "%Y-%m"
        period_key = row["period"].strftime(fmt)
        count = row["count"] or 0
        total = row["total"] or Decimal("0.00")
        avg = (total / count).quantize(Decimal("0.01")) if count > 0 else Decimal("0.00")
        data_lookup[period_key] = {"count": count, "avg_value": avg}
        total_orders += count
        total_revenue += total

    periods = _date_range(start, end, granularity)
    series = [
        {
            "period": p,
            "count": data_lookup.get(p, {}).get("count", 0),
            "avg_value": data_lookup.get(p, {}).get("avg_value", Decimal("0.00")),
        }
        for p in periods
    ]

    overall_aov = (
        (total_revenue / total_orders).quantize(Decimal("0.01"))
        if total_orders > 0 else Decimal("0.00")
    )

    return {
        "total_orders": total_orders,
        "avg_order_value": overall_aov,
        "series": series,
    }


def get_average_order_value(start: datetime, end: datetime) -> Decimal:
    """Simple AOV calculation for a period."""
    result = _get_paid_orders_qs(start, end).aggregate(
        avg=Avg("total_price")
    )
    return (result["avg"] or Decimal("0.00")).quantize(Decimal("0.01"))


# ─────────────────────────────────────────────────────────────
# SECTION 3 — CART CONVERSION FUNNEL
# ─────────────────────────────────────────────────────────────

def get_conversion_funnel(start: datetime, end: datetime) -> dict:
    """
    Cart-to-order conversion funnel showing drop-off at each step.

    Funnel stages: Sessions → Carts → Checkouts → Orders

    Returns:
        dict: {
            "stages": [
                {"stage": str, "count": int, "pct_of_first": float, "drop_off_pct": float}
            ],
            "overall_conversion_rate": float,
        }
    """
    from orders.models import Cart, Order

    base_filter = Q(created_at__gte=start, created_at__lte=end)

    total_carts = Cart.objects.filter(base_filter).count()
    started_checkout = Cart.objects.filter(
        base_filter,
        checkout_step__gt="",
    ).count()
    reached_payment = Cart.objects.filter(
        base_filter,
        checkout_step__in=["payment", "review"],
    ).count()
    converted = Cart.objects.filter(
        base_filter,
        status=Cart.CartStatus.CONVERTED,
    ).count()

    def pct(n, d):
        return round(n / d * 100, 1) if d > 0 else 0.0

    stages = [
        {"stage": "Carts Created", "count": total_carts, "pct_of_first": 100.0, "drop_off_pct": 0.0},
        {"stage": "Checkout Started", "count": started_checkout, "pct_of_first": pct(started_checkout, total_carts), "drop_off_pct": pct(total_carts - started_checkout, total_carts)},
        {"stage": "Reached Payment", "count": reached_payment, "pct_of_first": pct(reached_payment, total_carts), "drop_off_pct": pct(started_checkout - reached_payment, total_carts)},
        {"stage": "Orders Placed", "count": converted, "pct_of_first": pct(converted, total_carts), "drop_off_pct": pct(reached_payment - converted, total_carts)},
    ]

    return {
        "stages": stages,
        "overall_conversion_rate": pct(converted, total_carts),
    }


# ─────────────────────────────────────────────────────────────
# SECTION 4 — PRODUCT PERFORMANCE
# ─────────────────────────────────────────────────────────────

def get_top_products_by_revenue(
    start: datetime,
    end: datetime,
    limit: int = 10,
) -> list:
    """
    Top products ranked by revenue in a time period.

    Returns:
        list[dict]: [
            {
                "product_title", "sku", "variant_title",
                "quantity_sold", "revenue", "avg_price",
                "return_rate", "gross_profit"
            }
        ]
    """
    from orders.models import OrderItem

    rows = (
        OrderItem.objects
        .filter(
            order__financial_status__in=["paid", "partially_refunded"],
            order__is_test=False,
            order__placed_at__gte=start,
            order__placed_at__lte=end,
        )
        .values("product_title", "sku", "variant_title")
        .annotate(
            quantity_sold=Sum("quantity"),
            revenue=Sum("subtotal"),
            avg_price=Avg("unit_price"),
            returns=Sum("quantity_returned"),
            gross_profit_total=Sum(
                ExpressionWrapper(
                    F("subtotal") - F("cost_per_item") * F("quantity"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
        )
        .order_by("-revenue")[:limit]
    )

    result = []
    for row in rows:
        qty = row["quantity_sold"] or 0
        returns = row["returns"] or 0
        return_rate = round(returns / qty * 100, 1) if qty > 0 else 0.0
        result.append({
            "product_title": row["product_title"],
            "sku": row["sku"],
            "variant_title": row["variant_title"],
            "quantity_sold": qty,
            "revenue": row["revenue"] or Decimal("0.00"),
            "avg_price": (row["avg_price"] or Decimal("0.00")).quantize(Decimal("0.01")),
            "return_rate": return_rate,
            "gross_profit": row["gross_profit_total"] or Decimal("0.00"),
        })

    return result


# ─────────────────────────────────────────────────────────────
# SECTION 5 — CUSTOMER ANALYTICS
# ─────────────────────────────────────────────────────────────

def get_top_customers_by_spend(
    start: datetime,
    end: datetime,
    limit: int = 10,
) -> list:
    """
    Top customers ranked by total spend in the period.

    Returns:
        list[dict]: [{"customer_email", "customer_name", "order_count", "total_spend", "avg_order"}]
    """
    from orders.models import Order

    rows = (
        _get_paid_orders_qs(start, end)
        .exclude(customer__isnull=True)
        .values("customer_email", "customer_name")
        .annotate(
            order_count=Count("id"),
            total_spend=Sum("total_price"),
            avg_order=Avg("total_price"),
        )
        .order_by("-total_spend")[:limit]
    )

    return [
        {
            "customer_email": row["customer_email"],
            "customer_name": row["customer_name"],
            "order_count": row["order_count"],
            "total_spend": row["total_spend"] or Decimal("0.00"),
            "avg_order": (row["avg_order"] or Decimal("0.00")).quantize(Decimal("0.01")),
        }
        for row in rows
    ]


def get_cohort_retention(
    cohort_start: datetime,
    cohort_end: datetime,
    periods: int = 6,
) -> dict:
    """
    Monthly cohort retention analysis.
    Groups customers by their first order month, then tracks
    how many made repeat purchases in subsequent months.

    Returns:
        dict: {
            "cohorts": [
                {
                    "cohort_month": str,
                    "cohort_size": int,
                    "retention": [{"period": int, "count": int, "rate": float}]
                }
            ]
        }
    """
    from orders.models import Order
    from django.db.models.functions import TruncMonth as TM

    # First order per customer
    first_orders = (
        Order.objects
        .filter(
            is_test=False,
            financial_status__in=["paid", "partially_refunded"],
            customer__isnull=False,
        )
        .values("customer_id")
        .annotate(first_month=Min(TM("placed_at")))
        .filter(first_month__gte=cohort_start, first_month__lte=cohort_end)
    )

    cohort_map = {}
    for row in first_orders:
        key = row["first_month"].strftime("%Y-%m")
        cohort_map.setdefault(key, set()).add(row["customer_id"])

    cohorts_result = []

    for cohort_key, customer_ids in sorted(cohort_map.items()):
        cohort_month = datetime.strptime(cohort_key, "%Y-%m")
        retention_data = []
        cohort_size = len(customer_ids)

        for period_offset in range(1, periods + 1):
            period_start = (
                cohort_month.replace(day=1) +
                timedelta(days=32 * period_offset)
            ).replace(day=1)
            period_end = (
                period_start + timedelta(days=32)
            ).replace(day=1) - timedelta(seconds=1)

            repeat_count = (
                Order.objects
                .filter(
                    customer_id__in=customer_ids,
                    is_test=False,
                    financial_status__in=["paid", "partially_refunded"],
                    placed_at__gte=period_start,
                    placed_at__lte=period_end,
                )
                .values("customer_id")
                .distinct()
                .count()
            )

            retention_data.append({
                "period": period_offset,
                "count": repeat_count,
                "rate": round(repeat_count / cohort_size * 100, 1) if cohort_size > 0 else 0.0,
            })

        cohorts_result.append({
            "cohort_month": cohort_key,
            "cohort_size": cohort_size,
            "retention": retention_data,
        })

    return {"cohorts": cohorts_result}


# ─────────────────────────────────────────────────────────────
# SECTION 6 — ORDER STATUS & OPERATIONS ANALYTICS
# ─────────────────────────────────────────────────────────────

def get_order_status_distribution(start: datetime, end: datetime) -> list:
    """
    Distribution of orders by status for donut/pie charts.

    Returns:
        list[dict]: [{"status", "label", "count", "percentage"}]
    """
    from orders.models import Order

    total = Order.objects.filter(
        placed_at__gte=start, placed_at__lte=end, is_test=False
    ).count()

    rows = (
        Order.objects
        .filter(placed_at__gte=start, placed_at__lte=end, is_test=False)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    return [
        {
            "status": row["status"],
            "label": row["status"].replace("_", " ").title(),
            "count": row["count"],
            "percentage": round(row["count"] / total * 100, 1) if total > 0 else 0.0,
        }
        for row in rows
    ]


def get_fulfillment_performance(start: datetime, end: datetime) -> dict:
    """
    Fulfillment speed metrics for the operations dashboard.

    Returns:
        dict: {
            "avg_days_to_ship": float,
            "avg_days_to_deliver": float,
            "on_time_rate": float,
            "late_fulfillments": int,
            "sla_breakdown": [{"days_range": str, "count": int}]
        }
    """
    from orders.models import Fulfillment, Order

    shipped = (
        Fulfillment.objects
        .filter(
            order__is_test=False,
            shipped_at__gte=start,
            shipped_at__lte=end,
            shipped_at__isnull=False,
        )
        .select_related("order")
        .values("order__placed_at", "shipped_at", "delivered_at")
    )

    days_to_ship = []
    days_to_deliver = []

    for row in shipped:
        if row["order__placed_at"] and row["shipped_at"]:
            delta = (row["shipped_at"] - row["order__placed_at"]).total_seconds() / 86400
            days_to_ship.append(delta)

        if row["shipped_at"] and row["delivered_at"]:
            delta = (row["delivered_at"] - row["shipped_at"]).total_seconds() / 86400
            days_to_deliver.append(delta)

    avg_ship = round(sum(days_to_ship) / len(days_to_ship), 1) if days_to_ship else 0.0
    avg_deliver = round(sum(days_to_deliver) / len(days_to_deliver), 1) if days_to_deliver else 0.0

    # SLA buckets: 0-1d, 1-2d, 2-3d, 3-5d, 5+d
    buckets = {"0-1d": 0, "1-2d": 0, "2-3d": 0, "3-5d": 0, "5+d": 0}
    late = 0
    SLA_DAYS = 3

    for d in days_to_ship:
        if d <= 1:
            buckets["0-1d"] += 1
        elif d <= 2:
            buckets["1-2d"] += 1
        elif d <= 3:
            buckets["2-3d"] += 1
        elif d <= 5:
            buckets["3-5d"] += 1
            late += 1
        else:
            buckets["5+d"] += 1
            late += 1

    total = len(days_to_ship)
    on_time_rate = round((total - late) / total * 100, 1) if total > 0 else 100.0

    return {
        "avg_days_to_ship": avg_ship,
        "avg_days_to_deliver": avg_deliver,
        "on_time_rate": on_time_rate,
        "late_fulfillments": late,
        "total_shipped": total,
        "sla_breakdown": [{"days_range": k, "count": v} for k, v in buckets.items()],
    }


def get_return_rate_stats(start: datetime, end: datetime) -> dict:
    """
    Return and refund rate metrics.

    Returns:
        dict: {
            "return_rate": float,
            "refund_rate": float,
            "avg_refund_amount": Decimal,
            "top_return_reasons": list
        }
    """
    from orders.models import Order, Return, Refund

    total_orders = _get_paid_orders_qs(start, end).count()
    orders_with_returns = (
        Return.objects
        .filter(requested_at__gte=start, requested_at__lte=end)
        .values("order")
        .distinct()
        .count()
    )
    total_refunds = Refund.objects.filter(
        created_at__gte=start, created_at__lte=end,
        status="succeeded"
    ).count()
    avg_refund = Refund.objects.filter(
        created_at__gte=start, created_at__lte=end,
        status="succeeded"
    ).aggregate(avg=Avg("net_amount"))["avg"] or Decimal("0.00")

    top_reasons = (
        Return.objects
        .filter(requested_at__gte=start, requested_at__lte=end)
        .values("reason")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )

    return {
        "return_rate": round(orders_with_returns / total_orders * 100, 2) if total_orders else 0.0,
        "refund_rate": round(total_refunds / total_orders * 100, 2) if total_orders else 0.0,
        "avg_refund_amount": avg_refund.quantize(Decimal("0.01")),
        "top_return_reasons": [
            {"reason": r["reason"], "count": r["count"]} for r in top_reasons
        ],
    }


def get_sales_by_channel(start: datetime, end: datetime) -> list:
    """
    Revenue and order breakdown by order source channel.

    Returns:
        list[dict]: [{"source", "label", "orders", "revenue", "percentage"}]
    """
    from orders.models import Order

    total_revenue = _get_paid_orders_qs(start, end).aggregate(
        total=Sum("total_price")
    )["total"] or Decimal("1.00")

    rows = (
        _get_paid_orders_qs(start, end)
        .values("source")
        .annotate(orders=Count("id"), revenue=Sum("total_price"))
        .order_by("-revenue")
    )

    return [
        {
            "source": row["source"],
            "label": row["source"].replace("_", " ").title(),
            "orders": row["orders"],
            "revenue": row["revenue"] or Decimal("0.00"),
            "percentage": round(
                float(row["revenue"] or 0) / float(total_revenue) * 100, 1
            ),
        }
        for row in rows
    ]


def get_geographic_breakdown(
    start: datetime,
    end: datetime,
    level: str = "country",
) -> list:
    """
    Revenue breakdown by country or city.

    Args:
        level: "country" or "city"

    Returns:
        list[dict]: [{"location", "orders", "revenue", "percentage"}]
    """
    from orders.models import Order, OrderAddress

    total_revenue = _get_paid_orders_qs(start, end).aggregate(
        total=Sum("total_price")
    )["total"] or Decimal("1.00")

    group_field = "country" if level == "country" else "city"

    rows = (
        OrderAddress.objects
        .filter(
            address_type="shipping",
            order__financial_status__in=["paid", "partially_refunded"],
            order__is_test=False,
            order__placed_at__gte=start,
            order__placed_at__lte=end,
        )
        .values(group_field)
        .annotate(
            orders=Count("order_id"),
            revenue=Sum("order__total_price"),
        )
        .order_by("-revenue")[:20]
    )

    return [
        {
            "location": row[group_field] or "Unknown",
            "orders": row["orders"],
            "revenue": row["revenue"] or Decimal("0.00"),
            "percentage": round(float(row["revenue"] or 0) / float(total_revenue) * 100, 1),
        }
        for row in rows
    ]
