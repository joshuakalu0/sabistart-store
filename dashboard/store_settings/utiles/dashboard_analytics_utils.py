"""
Dashboard & Analytics Utilities — Admin/Merchant Layer
=======================================================
Production-ready analytics, reporting, and dashboard utility functions
for the multi-tenant e-commerce platform.

All query functions return plain Python dicts or lists so they can be
serialised to JSON for REST endpoints, or passed directly to Django
templates without ORM objects leaking into views.

Design contracts:
  - All DB queries are scoped to the current tenant schema automatically
    (django-tenants handles schema routing via connection.schema_name).
  - Every heavy query has a cache layer with explicit TTL and invalidation.
  - Date-range helpers default to sensible periods; all accept overrides.
  - Metric dicts always include a `label`, `value`, and optional `change_pct`
    key so the frontend can render KPI cards uniformly.

Modules
-------
1.  Date range helpers         – period boundaries, comparison windows
2.  Revenue analytics          – GMV, AOV, refunds, net revenue, by-period charts
3.  Order analytics            – volume, status funnel, fulfillment times, geography
4.  Product analytics          – top sellers, low stock, views, conversion, dead stock
5.  Customer analytics         – new vs returning, LTV, cohort retention, churn
6.  Traffic & conversion       – visits, bounce rate, funnel (if integrated)
7.  Inventory health           – stock alerts, turnover rate, reorder suggestions
8.  Marketing analytics        – coupon usage, referral sources, campaign ROI
9.  Store health KPIs          – single `get_store_health()` snapshot
10. Export utilities           – CSV / Excel export helpers for any dataset
11. Dashboard home aggregator  – `get_dashboard_home_data()` for the main view
12. Comparison utilities       – period-over-period delta calculation
13. Chart data serializers     – format raw DB aggregates → Chart.js–ready dicts
14. Notification / alert rules – generate in-dashboard alerts from live data
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from django.core.cache import cache
from django.db import connection
from django.db.models import (
    Avg, Count, DecimalField, ExpressionWrapper, F, Max, Min,
    OuterRef, Q, Subquery, Sum, Value,
)
from django.db.models.functions import (
    TruncDay, TruncHour, TruncMonth, TruncWeek, TruncYear,
)
from django.utils import timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _schema() -> str:
    return connection.schema_name or "public"


def _cache_key(namespace: str, *parts) -> str:
    import hashlib
    suffix = ":".join(str(p) for p in parts)
    raw = f"dash:{_schema()}:{namespace}:{suffix}"
    if len(raw) > 250:
        raw = f"dash:{_schema()}:{namespace}:{hashlib.md5(suffix.encode()).hexdigest()}"
    return raw


def _cached(key: str, loader, ttl: int = 60 * 5):
    """Generic cache-or-compute helper."""
    val = cache.get(key)
    if val is None:
        val = loader()
        cache.set(key, val, ttl)
    return val


# ============================================================================
# 1. DATE RANGE HELPERS
# ============================================================================

class DateRange:
    """Simple value object for a start/end pair of date-aware datetimes."""

    def __init__(self, start: datetime, end: datetime):
        self.start = start
        self.end   = end

    def __repr__(self):
        return f"DateRange({self.start.date()} → {self.end.date()})"

    @property
    def days(self) -> int:
        return (self.end - self.start).days

    def previous_period(self) -> "DateRange":
        """Return a window of equal length immediately before this one."""
        delta = self.end - self.start
        return DateRange(self.start - delta, self.start)


def today_range() -> DateRange:
    now = timezone.now()
    return DateRange(now.replace(hour=0, minute=0, second=0, microsecond=0), now)


def yesterday_range() -> DateRange:
    now  = timezone.now()
    yesterday = now - timedelta(days=1)
    return DateRange(
        yesterday.replace(hour=0, minute=0, second=0, microsecond=0),
        yesterday.replace(hour=23, minute=59, second=59),
    )


def last_n_days(n: int) -> DateRange:
    end   = timezone.now()
    start = end - timedelta(days=n)
    return DateRange(start, end)


def this_month_range() -> DateRange:
    now = timezone.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return DateRange(start, now)


def last_month_range() -> DateRange:
    now   = timezone.now()
    first_this = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_prev  = first_this - timedelta(seconds=1)
    first_prev = last_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return DateRange(first_prev, last_prev)


def this_year_range() -> DateRange:
    now   = timezone.now()
    start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return DateRange(start, now)


def custom_range(start: datetime, end: datetime) -> DateRange:
    return DateRange(start, end)


def parse_period(period: str) -> DateRange:
    """
    Convert a shorthand period string to a DateRange.

    Accepted values:
        "today", "yesterday", "7d", "30d", "90d", "mtd", "ytd",
        "last_month", "1y", or "YYYY-MM-DD:YYYY-MM-DD"
    """
    period = period.lower().strip()
    mapping = {
        "today":      today_range,
        "yesterday":  yesterday_range,
        "7d":         lambda: last_n_days(7),
        "30d":        lambda: last_n_days(30),
        "90d":        lambda: last_n_days(90),
        "mtd":        this_month_range,
        "last_month": last_month_range,
        "ytd":        this_year_range,
        "1y":         lambda: last_n_days(365),
    }
    if period in mapping:
        return mapping[period]()
    # Try "YYYY-MM-DD:YYYY-MM-DD"
    if ":" in period:
        try:
            start_str, end_str = period.split(":", 1)
            start = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)
            end   = datetime.fromisoformat(end_str).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
            return custom_range(start, end)
        except ValueError:
            pass
    return last_n_days(30)  # default fallback


# ============================================================================
# 2. REVENUE ANALYTICS
# ============================================================================

def get_revenue_summary(dr: Optional[DateRange] = None) -> Dict:
    """
    Return key revenue KPIs for the given period.

    Returns:
        {
          "gross_revenue":    Decimal,
          "net_revenue":      Decimal,
          "total_refunds":    Decimal,
          "order_count":      int,
          "aov":              Decimal,
          "gross_revenue_change_pct":  float,   # vs previous period
          "net_revenue_change_pct":    float,
          "order_count_change_pct":    float,
        }
    """
    if dr is None:
        dr = last_n_days(30)

    from shop.models import Order  # noqa: adjust import path

    def _compute(date_range: DateRange) -> Dict:
        qs = Order.objects.filter(
            created_at__gte=date_range.start,
            created_at__lte=date_range.end,
            status__in=["completed", "paid", "shipped", "delivered"],
        )
        agg = qs.aggregate(
            gross=Sum("total_amount"),
            refunds=Sum("refunded_amount"),
            count=Count("id"),
        )
        gross   = agg["gross"]   or Decimal("0")
        refunds = agg["refunds"] or Decimal("0")
        count   = agg["count"]   or 0
        net     = gross - refunds
        aov     = (gross / count).quantize(Decimal("0.01")) if count else Decimal("0")
        return {"gross": gross, "net": net, "refunds": refunds, "count": count, "aov": aov}

    current  = _compute(dr)
    previous = _compute(dr.previous_period())

    def _pct_change(curr, prev) -> Optional[float]:
        if prev == 0:
            return None
        return round(float((curr - prev) / prev * 100), 1)

    return {
        "gross_revenue":              current["gross"],
        "net_revenue":                current["net"],
        "total_refunds":              current["refunds"],
        "order_count":                current["count"],
        "aov":                        current["aov"],
        "gross_revenue_change_pct":   _pct_change(current["gross"], previous["gross"]),
        "net_revenue_change_pct":     _pct_change(current["net"], previous["net"]),
        "order_count_change_pct":     _pct_change(current["count"], previous["count"]),
        "period_label":               f"{dr.start.date()} – {dr.end.date()}",
    }


def get_revenue_over_time(
    dr: Optional[DateRange] = None,
    granularity: str = "day",  # "hour" | "day" | "week" | "month"
) -> List[Dict]:
    """
    Return revenue time-series data for charting.

    Returns:
        [{"label": "2024-01-15", "gross": 1250.00, "orders": 5}, ...]
    """
    if dr is None:
        dr = last_n_days(30)

    from shop.models import Order  # noqa

    trunc_map = {
        "hour":  TruncHour,
        "day":   TruncDay,
        "week":  TruncWeek,
        "month": TruncMonth,
    }
    trunc_fn = trunc_map.get(granularity, TruncDay)

    qs = (
        Order.objects
        .filter(
            created_at__gte=dr.start,
            created_at__lte=dr.end,
            status__in=["completed", "paid", "shipped", "delivered"],
        )
        .annotate(period=trunc_fn("created_at"))
        .values("period")
        .annotate(gross=Sum("total_amount"), orders=Count("id"))
        .order_by("period")
    )

    result = []
    for row in qs:
        label = row["period"].strftime(
            "%Y-%m-%d %H:00" if granularity == "hour"
            else "%Y-%m-%d" if granularity in ("day", "week")
            else "%Y-%m"
        )
        result.append({
            "label":  label,
            "gross":  float(row["gross"] or 0),
            "orders": row["orders"],
        })
    return result


def get_revenue_by_category(dr: Optional[DateRange] = None, top_n: int = 10) -> List[Dict]:
    """
    Return revenue breakdown by product category.

    Returns:
        [{"category": "Electronics", "revenue": 8200.0, "orders": 34, "share_pct": 42.5}, ...]
    """
    if dr is None:
        dr = last_n_days(30)

    from shop.models import OrderItem  # noqa

    qs = (
        OrderItem.objects
        .filter(
            order__created_at__gte=dr.start,
            order__created_at__lte=dr.end,
            order__status__in=["completed", "paid", "shipped", "delivered"],
        )
        .values("product__category__name")
        .annotate(revenue=Sum(F("unit_price") * F("quantity")), orders=Count("order", distinct=True))
        .order_by("-revenue")[:top_n]
    )

    rows = list(qs)
    total = sum(r["revenue"] or 0 for r in rows)

    return [
        {
            "category":   row["product__category__name"] or "Uncategorised",
            "revenue":    float(row["revenue"] or 0),
            "orders":     row["orders"],
            "share_pct":  round(float(row["revenue"] or 0) / total * 100, 1) if total else 0,
        }
        for row in rows
    ]


# ============================================================================
# 3. ORDER ANALYTICS
# ============================================================================

def get_order_status_breakdown(dr: Optional[DateRange] = None) -> List[Dict]:
    """
    Return counts for each order status within the period.

    Returns:
        [{"status": "completed", "count": 120, "share_pct": 65.0}, ...]
    """
    if dr is None:
        dr = last_n_days(30)

    from shop.models import Order  # noqa

    rows = (
        Order.objects
        .filter(created_at__gte=dr.start, created_at__lte=dr.end)
        .values("status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    total = sum(r["count"] for r in rows)
    return [
        {
            "status":    row["status"],
            "count":     row["count"],
            "share_pct": round(row["count"] / total * 100, 1) if total else 0,
        }
        for row in rows
    ]


def get_average_fulfillment_time(dr: Optional[DateRange] = None) -> Dict:
    """
    Calculate average hours from order creation to dispatch/delivery.

    Returns:
        {
            "avg_to_dispatch_hours": float,
            "avg_to_delivery_hours": float,
            "sample_count": int,
        }
    """
    if dr is None:
        dr = last_n_days(30)

    from shop.models import Order  # noqa
    from django.db.models import DurationField

    qs = Order.objects.filter(
        created_at__gte=dr.start,
        created_at__lte=dr.end,
        dispatched_at__isnull=False,
    ).annotate(
        dispatch_duration=ExpressionWrapper(
            F("dispatched_at") - F("created_at"),
            output_field=DurationField()
        )
    )

    agg = qs.aggregate(avg_dispatch=Avg("dispatch_duration"), count=Count("id"))
    avg_dispatch = agg["avg_dispatch"]
    avg_dispatch_hrs = (avg_dispatch.total_seconds() / 3600) if avg_dispatch else None

    return {
        "avg_to_dispatch_hours": round(avg_dispatch_hrs, 1) if avg_dispatch_hrs else None,
        "sample_count": agg["count"],
    }


def get_order_geography(dr: Optional[DateRange] = None, top_n: int = 15) -> List[Dict]:
    """
    Return order counts grouped by shipping country and city.

    Returns:
        [{"country": "NG", "city": "Lagos", "count": 45, "revenue": 320000.0}, ...]
    """
    if dr is None:
        dr = last_n_days(30)

    from shop.models import Order  # noqa

    return list(
        Order.objects
        .filter(created_at__gte=dr.start, created_at__lte=dr.end)
        .values("shipping_country", "shipping_city")
        .annotate(count=Count("id"), revenue=Sum("total_amount"))
        .order_by("-count")[:top_n]
        .values("shipping_country", "shipping_city", "count", "revenue")
    )


def get_hourly_order_heatmap(dr: Optional[DateRange] = None) -> List[Dict]:
    """
    Return a 7×24 heatmap (weekday × hour) of order frequency.
    Useful for identifying peak trading hours.

    Returns:
        [{"weekday": 0, "hour": 9, "count": 23}, ...]   (weekday: 0=Mon, 6=Sun)
    """
    if dr is None:
        dr = last_n_days(30)

    from shop.models import Order  # noqa
    from django.db.models.functions import ExtractHour, ExtractWeekDay

    rows = (
        Order.objects
        .filter(created_at__gte=dr.start, created_at__lte=dr.end)
        .annotate(
            hour=ExtractHour("created_at"),
            weekday=ExtractWeekDay("created_at"),
        )
        .values("weekday", "hour")
        .annotate(count=Count("id"))
        .order_by("weekday", "hour")
    )
    return [{"weekday": r["weekday"], "hour": r["hour"], "count": r["count"]} for r in rows]


# ============================================================================
# 4. PRODUCT ANALYTICS
# ============================================================================

def get_top_selling_products(
    dr: Optional[DateRange] = None,
    top_n: int = 10,
    by: str = "revenue",  # "revenue" | "quantity"
) -> List[Dict]:
    """
    Return the best-performing products by revenue or units sold.

    Returns:
        [
            {
                "product_id": "...",
                "name": "...",
                "sku": "...",
                "revenue": 4200.0,
                "units_sold": 84,
                "order_count": 62,
            },
            ...
        ]
    """
    if dr is None:
        dr = last_n_days(30)

    from shop.models import OrderItem  # noqa

    order_field = "-revenue" if by == "revenue" else "-units_sold"

    rows = (
        OrderItem.objects
        .filter(
            order__created_at__gte=dr.start,
            order__created_at__lte=dr.end,
            order__status__in=["completed", "paid", "shipped", "delivered"],
        )
        .values("product__id", "product__name", "product__sku")
        .annotate(
            revenue=Sum(F("unit_price") * F("quantity")),
            units_sold=Sum("quantity"),
            order_count=Count("order", distinct=True),
        )
        .order_by(order_field)[:top_n]
    )

    return [
        {
            "product_id":  str(row["product__id"]),
            "name":        row["product__name"],
            "sku":         row["product__sku"] or "",
            "revenue":     float(row["revenue"] or 0),
            "units_sold":  row["units_sold"] or 0,
            "order_count": row["order_count"] or 0,
        }
        for row in rows
    ]


def get_low_stock_products(threshold: Optional[int] = None, top_n: int = 50) -> List[Dict]:
    """
    Return products with stock at or below the alert threshold.

    Args:
        threshold: Stock qty threshold. Falls back to store settings or 10.

    Returns:
        [{"product_id": ..., "name": ..., "sku": ..., "stock": 3, "reorder_point": 10}, ...]
    """
    if threshold is None:
        from .storefront_utils import get_store_settings  # noqa
        store = get_store_settings()
        threshold = getattr(store, "low_stock_threshold", 10) if store else 10

    from shop.models import Product  # noqa

    rows = (
        Product.objects
        .filter(stock_quantity__lte=threshold, is_active=True)
        .values("id", "name", "sku", "stock_quantity")
        .annotate(reorder_point=Value(threshold))
        .order_by("stock_quantity")[:top_n]
    )

    return [
        {
            "product_id":   str(r["id"]),
            "name":         r["name"],
            "sku":          r["sku"] or "",
            "stock":        r["stock_quantity"],
            "reorder_point":r["reorder_point"],
        }
        for r in rows
    ]


def get_out_of_stock_products(top_n: int = 100) -> List[Dict]:
    """Return products currently out of stock."""
    from shop.models import Product  # noqa
    return list(
        Product.objects
        .filter(stock_quantity__lte=0, is_active=True)
        .values("id", "name", "sku", "stock_quantity")
        .order_by("name")[:top_n]
    )


def get_product_conversion_rate(dr: Optional[DateRange] = None, top_n: int = 20) -> List[Dict]:
    """
    Estimate product conversion rates (views → orders).
    Requires a ProductView tracking model.

    Returns:
        [{"product_id": ..., "views": 300, "purchases": 45, "conversion_pct": 15.0}, ...]
    """
    if dr is None:
        dr = last_n_days(30)

    try:
        from shop.models import ProductView, OrderItem  # noqa

        views = dict(
            ProductView.objects
            .filter(viewed_at__gte=dr.start, viewed_at__lte=dr.end)
            .values("product_id")
            .annotate(cnt=Count("id"))
            .values_list("product_id", "cnt")
        )

        purchases = dict(
            OrderItem.objects
            .filter(
                order__created_at__gte=dr.start,
                order__created_at__lte=dr.end,
                order__status__in=["completed", "paid", "shipped", "delivered"],
            )
            .values("product_id")
            .annotate(cnt=Sum("quantity"))
            .values_list("product_id", "cnt")
        )

        from shop.models import Product  # noqa
        products = Product.objects.filter(
            id__in=set(list(views.keys()) + list(purchases.keys()))
        ).values("id", "name")

        result = []
        for p in products:
            pid = p["id"]
            v = views.get(pid, 0)
            b = purchases.get(pid, 0)
            result.append({
                "product_id":      str(pid),
                "name":            p["name"],
                "views":           v,
                "purchases":       b,
                "conversion_pct":  round(b / v * 100, 2) if v else 0,
            })

        return sorted(result, key=lambda x: -x["conversion_pct"])[:top_n]

    except Exception as exc:
        logger.warning("Product conversion query failed: %s", exc)
        return []


def get_dead_stock_products(
    days_no_sales: int = 60,
    top_n: int = 30,
) -> List[Dict]:
    """
    Products that have had no sales in the last N days and have stock > 0.
    Useful for identifying clearance candidates.

    Returns:
        [{"product_id": ..., "name": ..., "stock": 45, "last_sold": "2024-03-12"}, ...]
    """
    from shop.models import Product, OrderItem  # noqa

    cutoff = timezone.now() - timedelta(days=days_no_sales)

    recently_sold_ids = set(
        OrderItem.objects
        .filter(order__created_at__gte=cutoff)
        .values_list("product_id", flat=True)
    )

    qs = (
        Product.objects
        .filter(is_active=True, stock_quantity__gt=0)
        .exclude(id__in=recently_sold_ids)
        .values("id", "name", "sku", "stock_quantity", "created_at")
        .order_by("-stock_quantity")[:top_n]
    )

    return [
        {
            "product_id": str(r["id"]),
            "name":       r["name"],
            "sku":        r["sku"] or "",
            "stock":      r["stock_quantity"],
            "added":      r["created_at"].date().isoformat() if r["created_at"] else None,
        }
        for r in qs
    ]


# ============================================================================
# 5. CUSTOMER ANALYTICS
# ============================================================================

def get_customer_summary(dr: Optional[DateRange] = None) -> Dict:
    """
    Return high-level customer KPIs.

    Returns:
        {
            "total_customers": int,
            "new_customers":   int,
            "returning_customers": int,
            "returning_rate_pct": float,
            "avg_orders_per_customer": float,
        }
    """
    if dr is None:
        dr = last_n_days(30)

    from django.contrib.auth import get_user_model
    from shop.models import Order  # noqa
    User = get_user_model()

    total_customers = User.objects.filter(is_staff=False).count()

    new_customers = User.objects.filter(
        date_joined__gte=dr.start,
        date_joined__lte=dr.end,
        is_staff=False,
    ).count()

    # Customers who ordered more than once in history
    returning = (
        Order.objects
        .filter(status__in=["completed", "paid", "shipped", "delivered"])
        .values("customer_id")
        .annotate(cnt=Count("id"))
        .filter(cnt__gt=1)
        .count()
    )

    # Avg orders per customer within period
    orders_in_period = Order.objects.filter(
        created_at__gte=dr.start,
        created_at__lte=dr.end,
        status__in=["completed", "paid", "shipped", "delivered"],
        customer_id__isnull=False,
    )
    period_order_count = orders_in_period.count()
    period_customer_count = orders_in_period.values("customer_id").distinct().count()
    avg_orders = round(period_order_count / period_customer_count, 2) if period_customer_count else 0

    return {
        "total_customers":         total_customers,
        "new_customers":           new_customers,
        "returning_customers":     returning,
        "returning_rate_pct":      round(returning / total_customers * 100, 1) if total_customers else 0,
        "avg_orders_per_customer": avg_orders,
    }


def get_customer_ltv(top_n: int = 20) -> List[Dict]:
    """
    Return the top customers by lifetime value (total spend).

    Returns:
        [{"customer_id": ..., "email": ..., "total_spend": ..., "order_count": ...}, ...]
    """
    from django.contrib.auth import get_user_model
    from shop.models import Order  # noqa
    User = get_user_model()

    rows = (
        Order.objects
        .filter(status__in=["completed", "paid", "shipped", "delivered"])
        .values("customer__id", "customer__email")
        .annotate(total_spend=Sum("total_amount"), order_count=Count("id"))
        .order_by("-total_spend")[:top_n]
    )

    return [
        {
            "customer_id": str(row["customer__id"]),
            "email":       row["customer__email"],
            "total_spend": float(row["total_spend"] or 0),
            "order_count": row["order_count"],
            "aov":         round(float(row["total_spend"] or 0) / row["order_count"], 2) if row["order_count"] else 0,
        }
        for row in rows
    ]


def get_new_customers_over_time(
    dr: Optional[DateRange] = None,
    granularity: str = "day",
) -> List[Dict]:
    """Return new customer registrations as a time series."""
    if dr is None:
        dr = last_n_days(30)

    from django.contrib.auth import get_user_model
    User = get_user_model()

    trunc_map = {"day": TruncDay, "week": TruncWeek, "month": TruncMonth}
    trunc_fn = trunc_map.get(granularity, TruncDay)

    rows = (
        User.objects
        .filter(date_joined__gte=dr.start, date_joined__lte=dr.end, is_staff=False)
        .annotate(period=trunc_fn("date_joined"))
        .values("period")
        .annotate(count=Count("id"))
        .order_by("period")
    )

    return [
        {
            "label": row["period"].strftime("%Y-%m-%d" if granularity != "month" else "%Y-%m"),
            "count": row["count"],
        }
        for row in rows
    ]


def get_customer_cohort_retention(months: int = 6) -> List[Dict]:
    """
    Simple cohort retention: for each acquisition month, how many customers
    placed at least one order in subsequent months.

    Returns:
        [
            {
                "cohort_month": "2024-01",
                "cohort_size": 120,
                "month_1_retention": 45,
                "month_2_retention": 30,
                ...
            },
            ...
        ]
    """
    from django.contrib.auth import get_user_model
    from shop.models import Order  # noqa
    User = get_user_model()

    now   = timezone.now()
    result = []

    for i in range(months, 0, -1):
        cohort_start = (now - timedelta(days=30 * i)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        cohort_end = (cohort_start + timedelta(days=32)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ) - timedelta(seconds=1)

        cohort_users = set(
            User.objects.filter(
                date_joined__gte=cohort_start,
                date_joined__lte=cohort_end,
                is_staff=False,
            ).values_list("id", flat=True)
        )

        if not cohort_users:
            continue

        retention = {"cohort_month": cohort_start.strftime("%Y-%m"), "cohort_size": len(cohort_users)}

        for j in range(1, min(i + 1, months + 1)):
            month_start = cohort_end + timedelta(days=1) + timedelta(days=30 * (j - 1))
            month_end   = (month_start + timedelta(days=32)).replace(day=1) - timedelta(seconds=1)
            retained = Order.objects.filter(
                customer_id__in=cohort_users,
                created_at__gte=month_start,
                created_at__lte=month_end,
            ).values("customer_id").distinct().count()
            retention[f"month_{j}_retention"] = retained

        result.append(retention)

    return result


# ============================================================================
# 6. INVENTORY HEALTH
# ============================================================================

def get_inventory_health_summary() -> Dict:
    """
    Return a snapshot of overall inventory health.

    Returns:
        {
            "total_skus":            int,
            "in_stock_count":        int,
            "low_stock_count":       int,
            "out_of_stock_count":    int,
            "total_stock_value":     Decimal,
            "out_of_stock_pct":      float,
        }
    """
    from shop.models import Product  # noqa
    from .storefront_utils import get_store_settings  # noqa
    store = get_store_settings()
    threshold = getattr(store, "low_stock_threshold", 10) if store else 10

    agg = Product.objects.filter(is_active=True).aggregate(
        total=Count("id"),
        in_stock=Count("id", filter=Q(stock_quantity__gt=threshold)),
        low_stock=Count("id", filter=Q(stock_quantity__gt=0, stock_quantity__lte=threshold)),
        out_of_stock=Count("id", filter=Q(stock_quantity__lte=0)),
        stock_value=Sum(F("cost_price") * F("stock_quantity")),
    )

    total = agg["total"] or 1

    return {
        "total_skus":         agg["total"] or 0,
        "in_stock_count":     agg["in_stock"] or 0,
        "low_stock_count":    agg["low_stock"] or 0,
        "out_of_stock_count": agg["out_of_stock"] or 0,
        "total_stock_value":  agg["stock_value"] or Decimal("0"),
        "out_of_stock_pct":   round((agg["out_of_stock"] or 0) / total * 100, 1),
    }


def get_stock_turnover_rate(dr: Optional[DateRange] = None, top_n: int = 20) -> List[Dict]:
    """
    Calculate stock turnover rate (units sold / avg stock) per product.
    High turnover = fast-moving; low = slow-moving.

    Returns:
        [{"product_id": ..., "name": ..., "units_sold": 90, "avg_stock": 30, "turnover": 3.0}, ...]
    """
    if dr is None:
        dr = last_n_days(30)

    from shop.models import OrderItem, Product  # noqa

    sold = dict(
        OrderItem.objects
        .filter(order__created_at__gte=dr.start, order__created_at__lte=dr.end)
        .values("product_id")
        .annotate(total_sold=Sum("quantity"))
        .values_list("product_id", "total_sold")
    )

    products = Product.objects.filter(id__in=sold.keys()).values("id", "name", "stock_quantity")

    result = []
    for p in products:
        pid  = p["id"]
        units = sold.get(pid, 0)
        stock = max(p["stock_quantity"] or 1, 1)
        result.append({
            "product_id": str(pid),
            "name":       p["name"],
            "units_sold": units,
            "avg_stock":  stock,
            "turnover":   round(units / stock, 2),
        })

    return sorted(result, key=lambda x: -x["turnover"])[:top_n]


# ============================================================================
# 7. MARKETING ANALYTICS
# ============================================================================

def get_coupon_usage_summary(dr: Optional[DateRange] = None) -> List[Dict]:
    """
    Return coupon performance stats.

    Returns:
        [{"code": "SAVE20", "uses": 45, "total_discount": 3400.0, "revenue_generated": 17000.0}, ...]
    """
    if dr is None:
        dr = last_n_days(30)

    try:
        from shop.models import Order  # noqa

        rows = (
            Order.objects
            .filter(
                created_at__gte=dr.start,
                created_at__lte=dr.end,
                coupon_code__isnull=False,
            )
            .exclude(coupon_code="")
            .values("coupon_code")
            .annotate(
                uses=Count("id"),
                total_discount=Sum("discount_amount"),
                revenue=Sum("total_amount"),
            )
            .order_by("-uses")
        )

        return [
            {
                "code":               row["coupon_code"],
                "uses":               row["uses"],
                "total_discount":     float(row["total_discount"] or 0),
                "revenue_generated":  float(row["revenue"] or 0),
            }
            for row in rows
        ]
    except Exception as exc:
        logger.warning("Coupon usage query failed: %s", exc)
        return []


def get_abandoned_cart_stats(dr: Optional[DateRange] = None) -> Dict:
    """
    Return abandoned cart recovery stats.

    Returns:
        {"abandoned_count": 145, "recovered_count": 23, "recovery_rate_pct": 15.9, "lost_revenue": 4300.0}
    """
    if dr is None:
        dr = last_n_days(30)

    try:
        from shop.models import AbandonedCart  # noqa
        agg = AbandonedCart.objects.filter(
            created_at__gte=dr.start, created_at__lte=dr.end
        ).aggregate(
            total=Count("id"),
            recovered=Count("id", filter=Q(is_recovered=True)),
            lost_value=Sum("cart_value", filter=Q(is_recovered=False)),
        )
        total = agg["total"] or 0
        recovered = agg["recovered"] or 0
        return {
            "abandoned_count":    total,
            "recovered_count":    recovered,
            "recovery_rate_pct":  round(recovered / total * 100, 1) if total else 0,
            "lost_revenue":       float(agg["lost_value"] or 0),
        }
    except Exception as exc:
        logger.warning("Abandoned cart query failed: %s", exc)
        return {}


# ============================================================================
# 8. STORE HEALTH KPIs
# ============================================================================

def get_store_health(dr: Optional[DateRange] = None) -> Dict:
    """
    Return a single comprehensive snapshot of store health.
    This is the primary function called by the dashboard home view.

    All values are returned as plain Python primitives (JSON-serializable).
    Cached for 5 minutes.
    """
    if dr is None:
        dr = last_n_days(30)

    key = _cache_key("store_health", dr.start.date(), dr.end.date())
    cached = cache.get(key)
    if cached:
        return cached

    revenue     = get_revenue_summary(dr)
    order_statuses = get_order_status_breakdown(dr)
    inventory   = get_inventory_health_summary()
    customers   = get_customer_summary(dr)
    top_products = get_top_selling_products(dr, top_n=5)

    result = {
        "period":          f"{dr.start.date()} → {dr.end.date()}",
        "revenue":         revenue,
        "order_statuses":  order_statuses,
        "inventory":       inventory,
        "customers":       customers,
        "top_products":    top_products,
        "generated_at":    timezone.now().isoformat(),
    }

    cache.set(key, result, 60 * 5)
    return result


# ============================================================================
# 9. COMPARISON UTILITIES
# ============================================================================

def pct_change(current: float, previous: float) -> Optional[float]:
    """
    Compute percentage change from previous to current.
    Returns None if previous is zero (avoid division by zero).
    """
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def build_kpi_card(label: str, current: float, previous: float,
                   prefix: str = "", suffix: str = "") -> Dict:
    """
    Build a standardised KPI card dict for the dashboard UI.

    Returns:
        {
            "label": "Gross Revenue",
            "value": "₦1,250,000",
            "raw_value": 1250000.0,
            "change_pct": 12.5,
            "trend": "up",   # "up" | "down" | "flat"
        }
    """
    change = pct_change(current, previous)
    trend  = "flat" if change is None or abs(change) < 0.1 else ("up" if change > 0 else "down")

    return {
        "label":      label,
        "value":      f"{prefix}{current:,.2f}{suffix}",
        "raw_value":  current,
        "change_pct": change,
        "trend":      trend,
    }


# ============================================================================
# 10. CHART DATA SERIALIZERS
# ============================================================================

def to_line_chart_data(
    series: List[Dict],
    label_key: str = "label",
    value_key: str = "value",
    dataset_label: str = "Value",
    color: str = "#2563EB",
) -> Dict:
    """
    Convert a flat list of {label, value} dicts → Chart.js line chart config.

    Returns a dict that can be JSON-dumped and passed straight to Chart.js.
    """
    return {
        "labels": [r[label_key] for r in series],
        "datasets": [
            {
                "label":           dataset_label,
                "data":            [r[value_key] for r in series],
                "borderColor":     color,
                "backgroundColor": color + "1A",  # 10% opacity fill
                "tension":         0.4,
                "fill":            True,
            }
        ],
    }


def to_bar_chart_data(
    series: List[Dict],
    label_key: str = "label",
    value_key: str = "value",
    dataset_label: str = "Value",
    color: str = "#2563EB",
) -> Dict:
    return {
        "labels": [r[label_key] for r in series],
        "datasets": [
            {
                "label":           dataset_label,
                "data":            [r[value_key] for r in series],
                "backgroundColor": color,
                "borderRadius":    4,
            }
        ],
    }


def to_doughnut_chart_data(
    series: List[Dict],
    label_key: str = "label",
    value_key: str = "value",
    colors: Optional[List[str]] = None,
) -> Dict:
    _DEFAULT_COLORS = [
        "#2563EB", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6",
        "#06B6D4", "#F97316", "#EC4899", "#14B8A6", "#84CC16",
    ]
    colors = colors or _DEFAULT_COLORS
    return {
        "labels":   [r[label_key] for r in series],
        "datasets": [
            {
                "data":            [r[value_key] for r in series],
                "backgroundColor": colors[:len(series)],
                "borderWidth":     2,
                "hoverOffset":     4,
            }
        ],
    }


def revenue_chart_data(dr: Optional[DateRange] = None, granularity: str = "day") -> Dict:
    """
    Ready-to-use Chart.js data dict for the revenue over time chart.
    """
    raw = get_revenue_over_time(dr, granularity)
    return to_line_chart_data(
        [{"label": r["label"], "value": r["gross"]} for r in raw],
        dataset_label="Revenue",
        color="#2563EB",
    )


def order_status_chart_data(dr: Optional[DateRange] = None) -> Dict:
    """Ready-to-use Chart.js doughnut data for order status distribution."""
    raw = get_order_status_breakdown(dr)
    return to_doughnut_chart_data(
        [{"label": r["status"].title(), "value": r["count"]} for r in raw]
    )


def category_revenue_chart_data(dr: Optional[DateRange] = None) -> Dict:
    """Ready-to-use Chart.js bar data for revenue by category."""
    raw = get_revenue_by_category(dr)
    return to_bar_chart_data(
        [{"label": r["category"], "value": r["revenue"]} for r in raw],
        dataset_label="Revenue",
        color="#10B981",
    )


# ============================================================================
# 11. EXPORT UTILITIES
# ============================================================================

def export_orders_csv(dr: Optional[DateRange] = None) -> io.StringIO:
    """
    Export orders to a CSV StringIO buffer.

    Usage in a view:
        buf = export_orders_csv(parse_period("30d"))
        response = HttpResponse(buf.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="orders.csv"'
        return response
    """
    if dr is None:
        dr = last_n_days(30)

    from shop.models import Order  # noqa

    qs = Order.objects.filter(
        created_at__gte=dr.start, created_at__lte=dr.end
    ).select_related("customer").order_by("-created_at")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Order ID", "Date", "Customer Email", "Status",
        "Subtotal", "Discount", "Tax", "Shipping", "Total",
        "Payment Method", "Shipping Method",
    ])

    for order in qs:
        writer.writerow([
            str(order.id),
            order.created_at.strftime("%Y-%m-%d %H:%M"),
            getattr(order.customer, "email", "guest"),
            order.status,
            order.subtotal,
            getattr(order, "discount_amount", 0),
            getattr(order, "tax_amount", 0),
            getattr(order, "shipping_amount", 0),
            order.total_amount,
            getattr(order, "payment_method", ""),
            getattr(order, "shipping_method", ""),
        ])

    buf.seek(0)
    return buf


def export_products_csv(include_out_of_stock: bool = True) -> io.StringIO:
    """Export product inventory to CSV."""
    from shop.models import Product  # noqa

    qs = Product.objects.filter(is_active=True).order_by("name")
    if not include_out_of_stock:
        qs = qs.filter(stock_quantity__gt=0)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Product ID", "Name", "SKU", "Price", "Stock", "Category", "Status"])

    for p in qs:
        writer.writerow([
            str(p.id),
            p.name,
            getattr(p, "sku", ""),
            p.price,
            p.stock_quantity,
            getattr(getattr(p, "category", None), "name", ""),
            "Active" if p.is_active else "Inactive",
        ])

    buf.seek(0)
    return buf


def export_customers_csv(dr: Optional[DateRange] = None) -> io.StringIO:
    """Export customer list with LTV to CSV."""
    from django.contrib.auth import get_user_model
    from shop.models import Order  # noqa
    User = get_user_model()

    ltv_map = dict(
        Order.objects
        .filter(status__in=["completed", "paid", "shipped", "delivered"])
        .values("customer_id")
        .annotate(total=Sum("total_amount"), cnt=Count("id"))
        .values_list("customer_id", "total")
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Customer ID", "Email", "Date Joined", "Total Spend", "Order Count"])

    for user in User.objects.filter(is_staff=False).order_by("-date_joined"):
        writer.writerow([
            str(user.id),
            user.email,
            user.date_joined.strftime("%Y-%m-%d"),
            float(ltv_map.get(user.id, 0)),
            "-",  # order count requires extra query; extend as needed
        ])

    buf.seek(0)
    return buf


# ============================================================================
# 12. NOTIFICATION / ALERT RULES
# ============================================================================

_ALERT_LEVELS = ("info", "warning", "critical")


def _alert(level: str, code: str, message: str, data: Optional[Dict] = None) -> Dict:
    return {"level": level, "code": code, "message": message, "data": data or {}}


def generate_dashboard_alerts() -> List[Dict]:
    """
    Scan current store state and return a list of actionable alert dicts.

    Checks:
    - Out-of-stock products
    - Low stock products
    - Pending orders older than 48 hours
    - Failed payments (if model exists)
    - Maintenance mode active
    - No active payment gateway

    Returns:
        [{"level": "warning", "code": "LOW_STOCK", "message": "...", "data": {...}}, ...]
    """
    alerts: List[Dict] = []

    # ── Maintenance mode ────────────────────────────────────────────────────
    from .storefront_utils import get_store_settings, is_maintenance_mode  # noqa
    if is_maintenance_mode():
        alerts.append(_alert("warning", "MAINTENANCE_MODE", "Store is currently in maintenance mode."))

    # ── Inventory alerts ────────────────────────────────────────────────────
    try:
        health = get_inventory_health_summary()
        if health["out_of_stock_count"] > 0:
            alerts.append(_alert(
                "critical", "OUT_OF_STOCK",
                f"{health['out_of_stock_count']} product(s) are out of stock.",
                {"count": health["out_of_stock_count"]},
            ))
        if health["low_stock_count"] > 0:
            alerts.append(_alert(
                "warning", "LOW_STOCK",
                f"{health['low_stock_count']} product(s) are running low on stock.",
                {"count": health["low_stock_count"]},
            ))
    except Exception as exc:
        logger.debug("Inventory alert check failed: %s", exc)

    # ── Stale pending orders ─────────────────────────────────────────────────
    try:
        from shop.models import Order  # noqa
        cutoff = timezone.now() - timedelta(hours=48)
        stale_count = Order.objects.filter(status="pending", created_at__lte=cutoff).count()
        if stale_count:
            alerts.append(_alert(
                "warning", "STALE_PENDING_ORDERS",
                f"{stale_count} order(s) have been pending for more than 48 hours.",
                {"count": stale_count},
            ))
    except Exception:
        pass

    return alerts


# ============================================================================
# 13. DASHBOARD HOME AGGREGATOR
# ============================================================================

def get_dashboard_home_data(period: str = "30d") -> Dict:
    """
    Master aggregation function for the dashboard home page.
    Returns all data needed to render KPI cards, charts, and tables in one call.

    Args:
        period: Shorthand period string (see parse_period).

    Returns a JSON-serialisable dict:
        {
            "period": "2024-01-01 → 2024-01-31",
            "kpi_cards": [...],
            "revenue_chart": {...},
            "order_status_chart": {...},
            "category_chart": {...},
            "top_products": [...],
            "low_stock": [...],
            "recent_customers": [...],
            "alerts": [...],
            "customer_summary": {...},
            "inventory_summary": {...},
        }
    """
    dr = parse_period(period)
    prev_dr = dr.previous_period()

    key = _cache_key("dashboard_home", period)
    cached = cache.get(key)
    if cached:
        return cached

    # Revenue KPIs
    rev_curr = get_revenue_summary(dr)
    rev_prev = get_revenue_summary(prev_dr)

    kpi_cards = [
        build_kpi_card(
            "Gross Revenue",
            float(rev_curr["gross_revenue"]),
            float(rev_prev["gross_revenue"]),
            prefix="",
        ),
        build_kpi_card(
            "Net Revenue",
            float(rev_curr["net_revenue"]),
            float(rev_prev["net_revenue"]),
        ),
        build_kpi_card(
            "Orders",
            float(rev_curr["order_count"]),
            float(rev_prev["order_count"]),
        ),
        build_kpi_card(
            "Avg Order Value",
            float(rev_curr["aov"]),
            float(rev_prev["aov"]),
        ),
    ]

    result = {
        "period":              f"{dr.start.date()} → {dr.end.date()}",
        "kpi_cards":           kpi_cards,
        "revenue_chart":       revenue_chart_data(dr),
        "order_status_chart":  order_status_chart_data(dr),
        "category_chart":      category_revenue_chart_data(dr),
        "top_products":        get_top_selling_products(dr, top_n=10),
        "low_stock":           get_low_stock_products(top_n=10),
        "customer_summary":    get_customer_summary(dr),
        "inventory_summary":   get_inventory_health_summary(),
        "alerts":              generate_dashboard_alerts(),
        "generated_at":        timezone.now().isoformat(),
    }

    cache.set(key, result, 60 * 5)  # 5-minute cache
    return result


# ============================================================================
# 14. CONVENIENCE VIEW HELPERS
# ============================================================================

def get_analytics_overview(period: str = "30d") -> Dict:
    """
    Lightweight analytics overview used by analytics summary widgets.
    Returns only the essential metrics without chart data.
    """
    dr   = parse_period(period)
    rev  = get_revenue_summary(dr)
    cust = get_customer_summary(dr)
    inv  = get_inventory_health_summary()

    return {
        "period":          period,
        "gross_revenue":   float(rev["gross_revenue"]),
        "net_revenue":     float(rev["net_revenue"]),
        "order_count":     rev["order_count"],
        "aov":             float(rev["aov"]),
        "new_customers":   cust["new_customers"],
        "total_customers": cust["total_customers"],
        "returning_rate":  cust["returning_rate_pct"],
        "out_of_stock":    inv["out_of_stock_count"],
        "low_stock":       inv["low_stock_count"],
    }


def get_product_analytics_page(period: str = "30d", page_size: int = 20) -> Dict:
    """
    Aggregate all product analytics for the products analytics dashboard page.
    """
    dr = parse_period(period)
    return {
        "period":            f"{dr.start.date()} → {dr.end.date()}",
        "top_by_revenue":    get_top_selling_products(dr, top_n=page_size, by="revenue"),
        "top_by_quantity":   get_top_selling_products(dr, top_n=page_size, by="quantity"),
        "low_stock":         get_low_stock_products(top_n=page_size),
        "out_of_stock":      get_out_of_stock_products(top_n=page_size),
        "dead_stock":        get_dead_stock_products(top_n=page_size),
        "inventory_health":  get_inventory_health_summary(),
        "turnover":          get_stock_turnover_rate(dr, top_n=page_size),
        "category_revenue":  get_revenue_by_category(dr, top_n=10),
    }


def get_customer_analytics_page(period: str = "30d") -> Dict:
    """
    Aggregate all customer analytics for the customer analytics dashboard page.
    """
    dr = parse_period(period)
    return {
        "period":             f"{dr.start.date()} → {dr.end.date()}",
        "summary":            get_customer_summary(dr),
        "top_by_ltv":         get_customer_ltv(top_n=20),
        "new_over_time":      get_new_customers_over_time(dr),
        "cohort_retention":   get_customer_cohort_retention(months=6),
        "new_chart":          to_bar_chart_data(
                                  get_new_customers_over_time(dr),
                                  label_key="label",
                                  value_key="count",
                                  dataset_label="New Customers",
                                  color="#10B981",
                              ),
    }


def get_order_analytics_page(period: str = "30d") -> Dict:
    """
    Aggregate all order analytics for the orders analytics dashboard page.
    """
    dr = parse_period(period)
    rev = get_revenue_over_time(dr)
    return {
        "period":          f"{dr.start.date()} → {dr.end.date()}",
        "revenue_summary": get_revenue_summary(dr),
        "status_breakdown":get_order_status_breakdown(dr),
        "fulfillment":     get_average_fulfillment_time(dr),
        "geography":       get_order_geography(dr),
        "heatmap":         get_hourly_order_heatmap(dr),
        "revenue_chart":   to_line_chart_data(
                               [{"label": r["label"], "value": r["gross"]} for r in rev],
                               dataset_label="Revenue",
                           ),
        "order_chart":     to_bar_chart_data(
                               [{"label": r["label"], "value": r["orders"]} for r in rev],
                               dataset_label="Orders",
                               color="#8B5CF6",
                           ),
    }
