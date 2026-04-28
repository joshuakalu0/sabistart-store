"""
orders/utils/dashboard.py
=========================
High-level dashboard aggregation functions.
Each function returns a ready-to-render dict for a specific
dashboard widget or panel — KPI cards, attention queues,
comparison blocks, and fulfillment queues.

These are the outermost layer — they call analytics.py
and orders/models directly, then package results for views.
"""

import logging
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .analytics import (
    get_average_order_value,
    get_orders_over_time,
    get_revenue_over_time,
    get_return_rate_stats,
    get_sales_by_channel,
)

logger = logging.getLogger("orders.dashboard")


# ─────────────────────────────────────────────────────────────
# SECTION 1 — KPI CARDS
# ─────────────────────────────────────────────────────────────

def get_dashboard_kpis(
    period_days: int = 30,
    compare: bool = True,
) -> dict:
    """
    Calculate all top-level KPI cards for the main dashboard.

    Compares current period vs the same-length previous period
    to produce change percentages and trend arrows.

    Args:
        period_days: Number of days in the current period.
        compare: Whether to compute comparison vs previous period.

    Returns:
        dict with keys: revenue, orders, aov, new_customers,
        conversion_rate, return_rate, each with:
          {"value", "previous", "change_pct", "trend": "up|down|flat"}
    """
    now = timezone.now()
    period_end = now
    period_start = now - timezone.timedelta(days=period_days)
    prev_end = period_start
    prev_start = prev_end - timezone.timedelta(days=period_days)

    from orders.models import Order, Cart

    # ── Revenue ──
    current_revenue = (
        Order.objects.filter(
            financial_status__in=["paid", "partially_refunded"],
            is_test=False,
            placed_at__gte=period_start,
            placed_at__lte=period_end,
        ).aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
    )
    prev_revenue = (
        Order.objects.filter(
            financial_status__in=["paid", "partially_refunded"],
            is_test=False,
            placed_at__gte=prev_start,
            placed_at__lte=prev_end,
        ).aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
        if compare else Decimal("0.00")
    )

    # ── Orders ──
    current_orders = Order.objects.filter(
        is_test=False,
        placed_at__gte=period_start,
        placed_at__lte=period_end,
    ).count()
    prev_orders = (
        Order.objects.filter(
            is_test=False,
            placed_at__gte=prev_start,
            placed_at__lte=prev_end,
        ).count() if compare else 0
    )

    # ── AOV ──
    current_aov = get_average_order_value(period_start, period_end)
    prev_aov = get_average_order_value(prev_start, prev_end) if compare else Decimal("0.00")

    # ── New customers ──
    from accounts.models import Customer
    try:
        current_new_customers = Customer.objects.filter(
            created_at__gte=period_start,
            created_at__lte=period_end,
        ).count()
        prev_new_customers = (
            Customer.objects.filter(
                created_at__gte=prev_start,
                created_at__lte=prev_end,
            ).count() if compare else 0
        )
    except Exception:
        current_new_customers = 0
        prev_new_customers = 0

    # ── Conversion rate ──
    total_carts = Cart.objects.filter(
        created_at__gte=period_start, created_at__lte=period_end
    ).count()
    converted_carts = Cart.objects.filter(
        created_at__gte=period_start,
        created_at__lte=period_end,
        status=Cart.CartStatus.CONVERTED,
    ).count()
    current_conversion = (
        round(converted_carts / total_carts * 100, 2) if total_carts > 0 else 0.0
    )

    prev_total_carts = Cart.objects.filter(
        created_at__gte=prev_start, created_at__lte=prev_end
    ).count() if compare else 0
    prev_converted = Cart.objects.filter(
        created_at__gte=prev_start,
        created_at__lte=prev_end,
        status=Cart.CartStatus.CONVERTED,
    ).count() if compare else 0
    prev_conversion = (
        round(prev_converted / prev_total_carts * 100, 2) if prev_total_carts > 0 else 0.0
    )

    # ── Return rate ──
    return_stats = get_return_rate_stats(period_start, period_end)
    current_return_rate = return_stats["return_rate"]

    def _kpi_block(current, previous, format_as="number"):
        if compare and previous and previous != 0:
            change_pct = round((float(current) - float(previous)) / float(previous) * 100, 1)
        else:
            change_pct = 0.0
        trend = "up" if change_pct > 0 else "down" if change_pct < 0 else "flat"
        return {
            "value": current,
            "previous": previous,
            "change_pct": change_pct,
            "trend": trend,
            "format": format_as,
        }

    return {
        "period_days": period_days,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "revenue": _kpi_block(current_revenue, prev_revenue, "currency"),
        "orders": _kpi_block(current_orders, prev_orders, "integer"),
        "aov": _kpi_block(current_aov, prev_aov, "currency"),
        "new_customers": _kpi_block(current_new_customers, prev_new_customers, "integer"),
        "conversion_rate": _kpi_block(current_conversion, prev_conversion, "percentage"),
        "return_rate": _kpi_block(current_return_rate, 0, "percentage"),
    }


# ─────────────────────────────────────────────────────────────
# SECTION 2 — TODAY'S STATS (Real-time panel)
# ─────────────────────────────────────────────────────────────

def get_todays_stats() -> dict:
    """
    Real-time stats for today (midnight → now).
    Used for the live header stats bar on the dashboard.

    Returns:
        dict: {
            "revenue_today", "orders_today", "units_sold_today",
            "new_customers_today", "carts_active_now",
            "pending_fulfillments", "open_returns"
        }
    """
    from orders.models import Order, Cart, Return

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    now = timezone.now()

    revenue_today = (
        Order.objects.filter(
            financial_status__in=["paid", "partially_refunded"],
            is_test=False,
            placed_at__gte=today_start,
        ).aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
    )
    orders_today = Order.objects.filter(
        is_test=False, placed_at__gte=today_start
    ).count()

    from orders.models import OrderItem
    units_today = (
        OrderItem.objects.filter(
            order__is_test=False,
            order__placed_at__gte=today_start,
        ).aggregate(total=Sum("quantity"))["total"] or 0
    )

    try:
        from accounts.models import Customer
        new_customers_today = Customer.objects.filter(
            created_at__gte=today_start
        ).count()
    except Exception:
        new_customers_today = 0

    carts_active = Cart.objects.filter(
        status=Cart.CartStatus.ACTIVE,
        last_activity_at__gte=now - timezone.timedelta(minutes=30),
    ).count()

    pending_fulfillments = Order.objects.filter(
        status__in=["confirmed", "processing"],
        fulfillment_status__in=["unfulfilled", "partially_fulfilled"],
        is_test=False,
    ).count()

    open_returns = Return.objects.filter(
        status__in=[
            "requested", "pending_review", "approved",
            "in_transit", "received", "inspecting",
        ]
    ).count()

    return {
        "revenue_today": revenue_today,
        "orders_today": orders_today,
        "units_sold_today": units_today,
        "new_customers_today": new_customers_today,
        "carts_active_now": carts_active,
        "pending_fulfillments": pending_fulfillments,
        "open_returns": open_returns,
        "generated_at": now.isoformat(),
    }


# ─────────────────────────────────────────────────────────────
# SECTION 3 — RECENT ORDERS
# ─────────────────────────────────────────────────────────────

def get_recent_orders(limit: int = 20) -> list:
    """
    Fetch the most recent orders for the dashboard activity feed.

    Returns:
        list[dict]: Lightweight order summaries for the table.
    """
    from orders.models import Order

    orders = (
        Order.objects
        .filter(is_test=False)
        .select_related("customer")
        .prefetch_related("items")
        .order_by("-placed_at")[:limit]
    )

    return [
        {
            "order_number": o.order_number,
            "order_id": str(o.id),
            "customer_name": o.customer_name,
            "customer_email": o.customer_email,
            "status": o.status,
            "financial_status": o.financial_status,
            "fulfillment_status": o.fulfillment_status,
            "total_price": o.total_price,
            "currency": o.currency,
            "item_count": o.total_items,
            "placed_at": o.placed_at.isoformat(),
            "source": o.source,
            "risk_level": o.risk_level,
        }
        for o in orders
    ]


# ─────────────────────────────────────────────────────────────
# SECTION 4 — ORDERS NEEDING ATTENTION
# ─────────────────────────────────────────────────────────────

def get_orders_needing_attention() -> dict:
    """
    Identify orders that require staff action, grouped by issue type.
    This powers the 'Action Required' widget on the dashboard.

    Returns:
        dict: {
            "fraud_review": [orders],
            "payment_failed": [orders],
            "unfulfilled_over_sla": [orders],
            "stuck_in_transit": [orders],
            "manual_review_required": [orders],
            "totals": {issue_type: count}
        }
    """
    from orders.models import Order, Fulfillment

    now = timezone.now()
    sla_cutoff = now - timezone.timedelta(days=3)
    transit_cutoff = now - timezone.timedelta(days=7)

    base_qs = Order.objects.filter(is_test=False)

    # ── Fraud review ──
    fraud_orders = list(
        base_qs.filter(
            status=Order.OrderStatus.FRAUD_REVIEW
        ).values(
            "order_number", "customer_email", "total_price",
            "risk_score", "placed_at"
        ).order_by("-placed_at")[:20]
    )

    # ── Payment failed ──
    payment_failed = list(
        base_qs.filter(
            financial_status=Order.FinancialStatus.FAILED
        ).values(
            "order_number", "customer_email", "total_price", "placed_at"
        ).order_by("-placed_at")[:20]
    )

    # ── Confirmed + unfulfilled past SLA ──
    unfulfilled_sla = list(
        base_qs.filter(
            status__in=[Order.OrderStatus.CONFIRMED, Order.OrderStatus.PROCESSING],
            fulfillment_status=Order.FulfillmentStatus.UNFULFILLED,
            confirmed_at__lt=sla_cutoff,
            confirmed_at__isnull=False,
        ).values(
            "order_number", "customer_email", "total_price",
            "confirmed_at", "fulfillment_status"
        ).order_by("confirmed_at")[:20]
    )

    # ── Stuck in transit ──
    stuck_fulfillment_order_ids = list(
        Fulfillment.objects.filter(
            status=Fulfillment.FulfillmentStatus.IN_TRANSIT,
            shipped_at__lt=transit_cutoff,
        ).values_list("order_id", flat=True).distinct()
    )
    stuck_transit = list(
        base_qs.filter(
            id__in=stuck_fulfillment_order_ids
        ).values(
            "order_number", "customer_email", "total_price",
            "fulfillment_status", "placed_at"
        )[:20]
    )

    # ── Manual review flagged ──
    manual_review = list(
        base_qs.filter(
            requires_manual_review=True,
            status__in=[
                Order.OrderStatus.PENDING,
                Order.OrderStatus.CONFIRMED,
                Order.OrderStatus.ON_HOLD,
            ],
        ).values(
            "order_number", "customer_email", "total_price",
            "risk_level", "placed_at"
        ).order_by("-placed_at")[:20]
    )

    return {
        "fraud_review": fraud_orders,
        "payment_failed": payment_failed,
        "unfulfilled_over_sla": unfulfilled_sla,
        "stuck_in_transit": stuck_transit,
        "manual_review_required": manual_review,
        "totals": {
            "fraud_review": len(fraud_orders),
            "payment_failed": len(payment_failed),
            "unfulfilled_over_sla": len(unfulfilled_sla),
            "stuck_in_transit": len(stuck_transit),
            "manual_review_required": len(manual_review),
            "total": (
                len(fraud_orders) + len(payment_failed) +
                len(unfulfilled_sla) + len(stuck_transit) +
                len(manual_review)
            ),
        },
    }


# ─────────────────────────────────────────────────────────────
# SECTION 5 — FULFILLMENT QUEUE
# ─────────────────────────────────────────────────────────────

def get_order_fulfillment_queue(
    location=None,
    priority: str = "oldest_first",
    page: int = 1,
    page_size: int = 25,
) -> dict:
    """
    Staff fulfillment queue — orders ready to be packed and shipped.
    Used to render the pick/pack/ship workflow.

    Args:
        location: Filter by inventory location.
        priority: "oldest_first" | "highest_value" | "express_only"
        page: Page number.
        page_size: Items per page.

    Returns:
        dict with orders list and metadata.
    """
    from orders.models import Order
    import math

    qs = Order.objects.filter(
        status__in=[Order.OrderStatus.CONFIRMED, Order.OrderStatus.PROCESSING],
        fulfillment_status__in=[
            Order.FulfillmentStatus.UNFULFILLED,
            Order.FulfillmentStatus.PARTIALLY_FULFILLED,
        ],
        financial_status__in=[Order.FinancialStatus.PAID, Order.FinancialStatus.PARTIALLY_PAID],
        is_test=False,
    ).prefetch_related("items__variant", "addresses")

    if location:
        qs = qs.filter(
            items__variant__inventory_levels__location=location
        ).distinct()

    order_map = {
        "oldest_first": "confirmed_at",
        "highest_value": "-total_price",
        "express_only": "confirmed_at",
    }
    qs = qs.order_by(order_map.get(priority, "confirmed_at"))

    if priority == "express_only":
        qs = qs.filter(
            tags__name__in=["express", "overnight", "priority"]
        )

    total = qs.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 1
    offset = (page - 1) * page_size

    orders_page = qs[offset: offset + page_size]

    queue_items = []
    for order in orders_page:
        shipping_addr = next(
            (a for a in order.addresses.all() if a.address_type == "shipping"), None
        )
        unfulfilled_lines = [
            {
                "sku": item.sku,
                "title": f"{item.product_title} / {item.variant_title}".strip(" /"),
                "quantity_needed": item.quantity_unfulfilled,
            }
            for item in order.items.all()
            if item.quantity_unfulfilled > 0
        ]

        queue_items.append({
            "order_id": str(order.id),
            "order_number": order.order_number,
            "placed_at": order.placed_at.isoformat(),
            "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
            "customer_name": order.customer_name,
            "customer_email": order.customer_email,
            "destination": f"{shipping_addr.city}, {shipping_addr.country}" if shipping_addr else "",
            "total_price": str(order.total_price),
            "currency": order.currency,
            "shipping_method": order.shipping_method_name,
            "fulfillment_status": order.fulfillment_status,
            "unfulfilled_lines": unfulfilled_lines,
            "total_items_needed": sum(l["quantity_needed"] for l in unfulfilled_lines),
            "has_risk": order.risk_level in ("medium", "high"),
            "tags": list(order.tags.values_list("name", flat=True)),
        })

    return {
        "queue": queue_items,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "location": str(location.id) if location else None,
        "priority": priority,
    }


# ─────────────────────────────────────────────────────────────
# SECTION 6 — PENDING RETURNS SUMMARY
# ─────────────────────────────────────────────────────────────

def get_pending_returns_summary() -> dict:
    """
    Returns summary for the returns management panel.

    Returns:
        dict: {
            "total_open", "awaiting_review", "awaiting_items",
            "awaiting_inspection", "awaiting_refund",
            "total_pending_refund_value",
            "recent_returns": [...]
        }
    """
    from orders.models import Return, Refund

    base = Return.objects.filter(
        status__in=[
            "requested", "pending_review", "approved",
            "label_generated", "in_transit", "received",
            "inspecting", "restocked", "partially_restocked",
            "refund_pending",
        ]
    )

    counts = base.values("status").annotate(count=Count("id"))
    status_map = {row["status"]: row["count"] for row in counts}

    pending_value = (
        Return.objects.filter(
            status="refund_pending",
            refund_amount__isnull=False,
        ).aggregate(total=Sum("refund_amount"))["total"] or Decimal("0.00")
    )

    recent = list(
        base.select_related("order")
        .order_by("-requested_at")[:10]
        .values(
            "return_number", "status", "reason",
            "order__order_number", "refund_amount", "requested_at"
        )
    )

    return {
        "total_open": base.count(),
        "awaiting_review": status_map.get("requested", 0) + status_map.get("pending_review", 0),
        "awaiting_items": status_map.get("approved", 0) + status_map.get("label_generated", 0),
        "in_transit": status_map.get("in_transit", 0),
        "awaiting_inspection": status_map.get("received", 0) + status_map.get("inspecting", 0),
        "awaiting_refund": status_map.get("refund_pending", 0),
        "total_pending_refund_value": pending_value,
        "recent_returns": recent,
    }


# ─────────────────────────────────────────────────────────────
# SECTION 7 — REVENUE COMPARISON
# ─────────────────────────────────────────────────────────────

def get_revenue_comparison(
    period_days: int = 30,
    granularity: str = "day",
) -> dict:
    """
    Side-by-side revenue series for current vs previous period.
    Used to render the main revenue chart with comparison overlay.

    Returns:
        dict: {
            "current": [{"period": str, "gross": Decimal, "net": Decimal}],
            "previous": [{"period": str, "gross": Decimal, "net": Decimal}],
            "current_total": Decimal,
            "previous_total": Decimal,
            "change_pct": float,
        }
    """
    now = timezone.now()
    current_end = now
    current_start = now - timezone.timedelta(days=period_days)
    prev_end = current_start
    prev_start = prev_end - timezone.timedelta(days=period_days)

    current_data = get_revenue_over_time(current_start, current_end, granularity)
    prev_data = get_revenue_over_time(prev_start, prev_end, granularity)

    change_pct = 0.0
    if prev_data["total_gross"] and prev_data["total_gross"] > 0:
        change_pct = round(
            float(current_data["total_gross"] - prev_data["total_gross"])
            / float(prev_data["total_gross"])
            * 100,
            1,
        )

    return {
        "current": current_data["series"],
        "previous": prev_data["series"],
        "current_total": current_data["total_gross"],
        "previous_total": prev_data["total_gross"],
        "current_net": current_data["total_net"],
        "previous_net": prev_data["total_net"],
        "change_pct": change_pct,
        "trend": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
    }


# ─────────────────────────────────────────────────────────────
# SECTION 8 — LOW STOCK + ORDER RISK
# ─────────────────────────────────────────────────────────────

def get_low_stock_order_risks() -> list:
    """
    Identify unfulfilled orders containing variants that are low
    or out of stock — a fulfillment risk that needs immediate attention.

    Returns:
        list[dict]: [
            {
                "order_number", "customer_email", "placed_at",
                "at_risk_items": [{"title", "sku", "needed", "available"}]
            }
        ]
    """
    from orders.models import Order, OrderItem

    at_risk = []

    unfulfilled_orders = (
        Order.objects.filter(
            status__in=["confirmed", "processing"],
            fulfillment_status__in=["unfulfilled", "partially_fulfilled"],
            is_test=False,
        )
        .prefetch_related("items__variant")
        .order_by("placed_at")[:50]
    )

    for order in unfulfilled_orders:
        risk_lines = []
        for item in order.items.all():
            variant = item.variant
            if not variant or not variant.track_inventory:
                continue
            needed = item.quantity_unfulfilled
            available = variant.available_quantity
            if available < needed:
                risk_lines.append({
                    "title": item.product_title,
                    "variant_title": item.variant_title,
                    "sku": item.sku,
                    "needed": needed,
                    "available": available,
                    "shortfall": needed - available,
                })

        if risk_lines:
            at_risk.append({
                "order_number": order.order_number,
                "order_id": str(order.id),
                "customer_email": order.customer_email,
                "placed_at": order.placed_at.isoformat(),
                "at_risk_items": risk_lines,
            })

    return at_risk
