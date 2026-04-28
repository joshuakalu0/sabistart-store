from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode
from uuid import UUID

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Avg, Count, F, Q, Sum
from django.db.models import Model, QuerySet
from django.db.models.functions import ExtractHour, TruncDate, TruncMonth
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

from dashboard.payments_tenant.services.analytics import (
    get_dispute_analysis,
    get_gateway_performance,
    get_payment_method_breakdown,
    get_refund_analysis,
    get_revenue_over_time,
    get_transaction_funnel,
)
from dashboard.pos.models import InventoryAdjustment, POSPayment, POSTransaction, Store, StoreInventory
from public.cart.models import Order, OrderItem
from public.monitoring.models import PageVisit, VisitorSession
from public.product.models import Product, ProductVariant
from public.userauth.models import Customer, CustomerSession
from system.core.models import Shop
from system.feature_marketplace.models import FeatureEntitlementIndex
from system.system_pay.models import TenantPaymentSnapshot

try:
    from openpyxl import Workbook
except Exception:  # pragma: no cover - optional dependency
    Workbook = None


ANALYTICS_PERIODS = (
    ("today", "Today"),
    ("yesterday", "Yesterday"),
    ("7d", "Last 7 days"),
    ("30d", "Last 30 days"),
    ("90d", "Last 90 days"),
    ("this_month", "This month"),
    ("last_month", "Last month"),
    ("this_year", "This year"),
    ("custom", "Custom range"),
)

PERIOD_CHOICES = {key for key, _ in ANALYTICS_PERIODS}
DEFAULT_PERIOD = "30d"
CHART_COLORS = (
    ("#2563eb", "rgba(37, 99, 235, 0.16)"),
    ("#0f766e", "rgba(15, 118, 110, 0.16)"),
    ("#f59e0b", "rgba(245, 158, 11, 0.18)"),
    ("#dc2626", "rgba(220, 38, 38, 0.16)"),
    ("#7c3aed", "rgba(124, 58, 237, 0.16)"),
    ("#0891b2", "rgba(8, 145, 178, 0.16)"),
)


@dataclass(frozen=True)
class AnalyticsWindow:
    period: str
    start_date: date
    end_date: date
    compare: bool
    previous_start: date
    previous_end: date
    label: str
    previous_label: str

    @property
    def start(self):
        return timezone.make_aware(datetime.combine(self.start_date, time.min))

    @property
    def end(self):
        return timezone.make_aware(datetime.combine(self.end_date, time.max))

    @property
    def previous_start_dt(self):
        return timezone.make_aware(datetime.combine(self.previous_start, time.min))

    @property
    def previous_end_dt(self):
        return timezone.make_aware(datetime.combine(self.previous_end, time.max))


def _safe_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _safe_float(value: Any) -> float:
    return float(_safe_decimal(value))


def _safe_int(value: Any) -> int:
    return int(value or 0)


def _period_label(period: str, start_date: date, end_date: date) -> str:
    labels = dict(ANALYTICS_PERIODS)
    if period == "custom":
        return f"{start_date:%b %d, %Y} to {end_date:%b %d, %Y}"
    return labels.get(period, labels[DEFAULT_PERIOD])


def _calendar_month_bounds(source_date: date) -> tuple[date, date]:
    start_date = source_date.replace(day=1)
    if start_date.month == 12:
        next_month = start_date.replace(year=start_date.year + 1, month=1, day=1)
    else:
        next_month = start_date.replace(month=start_date.month + 1, day=1)
    return start_date, next_month - timedelta(days=1)


def parse_analytics_window(params) -> AnalyticsWindow:
    today = timezone.localdate()
    period = (params.get("period") or DEFAULT_PERIOD).strip().lower()
    if period not in PERIOD_CHOICES:
        period = DEFAULT_PERIOD

    start_date = today - timedelta(days=29)
    end_date = today

    if period == "today":
        start_date = end_date = today
    elif period == "yesterday":
        start_date = end_date = today - timedelta(days=1)
    elif period == "7d":
        start_date = today - timedelta(days=6)
    elif period == "30d":
        start_date = today - timedelta(days=29)
    elif period == "90d":
        start_date = today - timedelta(days=89)
    elif period == "this_month":
        start_date, end_date = _calendar_month_bounds(today)
        end_date = min(end_date, today)
    elif period == "last_month":
        last_month_anchor = today.replace(day=1) - timedelta(days=1)
        start_date, end_date = _calendar_month_bounds(last_month_anchor)
    elif period == "this_year":
        start_date = date(today.year, 1, 1)
        end_date = today
    elif period == "custom":
        try:
            start_date = datetime.fromisoformat(params.get("start", "")).date()
        except (TypeError, ValueError):
            start_date = today - timedelta(days=29)
        try:
            end_date = datetime.fromisoformat(params.get("end", "")).date()
        except (TypeError, ValueError):
            end_date = today

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    compare = str(params.get("compare", "")).lower() in {"1", "true", "yes", "on"}

    if period == "this_month":
        previous_anchor = start_date - timedelta(days=1)
        previous_start, previous_end = _calendar_month_bounds(previous_anchor)
    elif period == "last_month":
        previous_anchor = start_date - timedelta(days=1)
        previous_start, previous_end = _calendar_month_bounds(previous_anchor)
    elif period == "this_year":
        previous_start = date(start_date.year - 1, 1, 1)
        previous_end = date(start_date.year - 1, 12, 31)
    else:
        duration_days = (end_date - start_date).days + 1
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=duration_days - 1)

    return AnalyticsWindow(
        period=period,
        start_date=start_date,
        end_date=end_date,
        compare=compare,
        previous_start=previous_start,
        previous_end=previous_end,
        label=_period_label(period, start_date, end_date),
        previous_label=f"Previous: {previous_start:%b %d, %Y} to {previous_end:%b %d, %Y}",
    )


def window_context(window: AnalyticsWindow) -> dict[str, Any]:
    return {
        "period": window.period,
        "start": window.start_date.isoformat(),
        "end": window.end_date.isoformat(),
        "compare": window.compare,
        "label": window.label,
        "previous_label": window.previous_label,
        "period_options": [{"value": value, "label": label} for value, label in ANALYTICS_PERIODS],
    }


def _change(current: Any, previous: Any) -> float | None:
    current_decimal = _safe_decimal(current)
    previous_decimal = _safe_decimal(previous)
    if previous_decimal == 0:
        if current_decimal == 0:
            return 0.0
        return None
    return round(float((current_decimal - previous_decimal) / previous_decimal * Decimal("100")), 2)


def build_kpi(
    key: str,
    label: str,
    value: Any,
    *,
    format_type: str = "number",
    change_pct: float | None = None,
    helper: str = "",
    tone: str = "default",
):
    return {
        "key": key,
        "label": label,
        "value": _safe_float(value) if format_type in {"currency", "decimal"} else _safe_int(value) if format_type == "number" else value,
        "format": format_type,
        "change_pct": change_pct,
        "helper": helper,
        "tone": tone,
    }


def build_dataset(label: str, data: list[Any], *, color_index: int = 0, fill: bool = False):
    border_color, background_color = CHART_COLORS[color_index % len(CHART_COLORS)]
    return {
        "label": label,
        "data": [round(float(item or 0), 2) for item in data],
        "borderColor": border_color,
        "backgroundColor": background_color,
        "fill": fill,
        "tension": 0.35,
    }


def build_chart(
    key: str,
    title: str,
    labels: list[str],
    datasets: list[dict[str, Any]],
    *,
    active_type: str = "line",
    type_options: tuple[str, ...] | list[str] = ("line", "bar", "area"),
    subtitle: str = "",
    meta: dict[str, Any] | None = None,
):
    return {
        "key": key,
        "title": title,
        "subtitle": subtitle,
        "labels": labels,
        "datasets": datasets,
        "active_type": active_type,
        "type_options": list(type_options),
        "meta": meta or {},
    }


def _finalize_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    columns = bundle.get("table_columns", [])
    rows = bundle.get("table_rows", [])
    bundle["table_matrix"] = [[row.get(column, "") for column in columns] for row in rows]
    return bundle


def _json_safe(value: Any):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, QuerySet):
        return [_json_safe(item) for item in value]
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Model):
        return str(value)
    return value


def _build_daily_map(start_date: date, end_date: date, rows, *, value_key: str, count_key: str | None = None):
    by_day = {row["day"]: row for row in rows}
    labels = []
    values = []
    counts = []
    current = start_date
    while current <= end_date:
        labels.append(current.strftime("%b %d"))
        record = by_day.get(current, {})
        values.append(_safe_float(record.get(value_key)))
        if count_key:
            counts.append(_safe_int(record.get(count_key)))
        current += timedelta(days=1)
    return labels, values, counts


def _active_order_queryset(window: AnalyticsWindow):
    return Order.objects.filter(
        placed_at__gte=window.start,
        placed_at__lte=window.end,
        is_test=False,
    )


def _previous_order_queryset(window: AnalyticsWindow):
    return Order.objects.filter(
        placed_at__gte=window.previous_start_dt,
        placed_at__lte=window.previous_end_dt,
        is_test=False,
    )


def _customer_queryset(window: AnalyticsWindow):
    return Customer.objects.filter(created_at__gte=window.start, created_at__lte=window.end)


def _previous_customer_queryset(window: AnalyticsWindow):
    return Customer.objects.filter(created_at__gte=window.previous_start_dt, created_at__lte=window.previous_end_dt)


def _page_visit_queryset(window: AnalyticsWindow, *, source: str = ""):
    queryset = PageVisit.objects.filter(created_at__gte=window.start, created_at__lte=window.end)
    if source:
        queryset = queryset.filter(source=source)
    return queryset


def _previous_page_visit_queryset(window: AnalyticsWindow, *, source: str = ""):
    queryset = PageVisit.objects.filter(created_at__gte=window.previous_start_dt, created_at__lte=window.previous_end_dt)
    if source:
        queryset = queryset.filter(source=source)
    return queryset


def _pos_queryset(window: AnalyticsWindow, *, store: Store | None = None):
    queryset = POSTransaction.objects.filter(
        created_at__gte=window.start,
        created_at__lte=window.end,
        is_deleted=False,
        status="completed",
    )
    if store is not None:
        queryset = queryset.filter(store=store)
    return queryset


def _previous_pos_queryset(window: AnalyticsWindow, *, store: Store | None = None):
    queryset = POSTransaction.objects.filter(
        created_at__gte=window.previous_start_dt,
        created_at__lte=window.previous_end_dt,
        is_deleted=False,
        status="completed",
    )
    if store is not None:
        queryset = queryset.filter(store=store)
    return queryset


def build_overview_bundle(window: AnalyticsWindow) -> dict[str, Any]:
    current_orders = _active_order_queryset(window)
    previous_orders = _previous_order_queryset(window)
    current_customers = _customer_queryset(window)
    previous_customers = _previous_customer_queryset(window)
    current_visits = _page_visit_queryset(window)
    previous_visits = _previous_page_visit_queryset(window)

    current_revenue = current_orders.aggregate(total=Sum("total_paid"))["total"] or Decimal("0.00")
    previous_revenue = previous_orders.aggregate(total=Sum("total_paid"))["total"] or Decimal("0.00")
    current_order_count = current_orders.count()
    previous_order_count = previous_orders.count()
    current_customer_count = current_customers.count()
    previous_customer_count = previous_customers.count()
    current_sessions = current_visits.values("visitor_session_id").distinct().count()
    previous_sessions = previous_visits.values("visitor_session_id").distinct().count()
    low_stock_products = Product.objects.filter(
        is_active=True,
        status="published",
        product_type="simple",
        manage_stock=True,
        stock_quantity__lte=F("low_stock_threshold"),
    ).count()
    low_stock_inventory = StoreInventory.objects.filter(
        is_deleted=False,
        quantity__gt=0,
        quantity__lte=F("low_stock_threshold"),
    ).count()
    pos_today_total = _pos_queryset(
        AnalyticsWindow(
            period="today",
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
            compare=False,
            previous_start=timezone.localdate() - timedelta(days=1),
            previous_end=timezone.localdate() - timedelta(days=1),
            label="Today",
            previous_label="Yesterday",
        )
    ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")

    order_series = list(
        current_orders.annotate(day=TruncDate("placed_at"))
        .values("day")
        .annotate(revenue=Sum("total_paid"), orders=Count("id"))
        .order_by("day")
    )
    labels, revenue_values, order_values = _build_daily_map(
        window.start_date,
        window.end_date,
        order_series,
        value_key="revenue",
        count_key="orders",
    )

    traffic_series = list(
        current_visits.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(views=Count("id"))
        .order_by("day")
    )
    _, traffic_values, _ = _build_daily_map(
        window.start_date,
        window.end_date,
        traffic_series,
        value_key="views",
    )

    top_products = list(
        OrderItem.objects.filter(order__in=current_orders)
        .values("product_title")
        .annotate(units_sold=Sum("quantity"), revenue=Sum("total"))
        .order_by("-units_sold", "-revenue")[:8]
    )

    bundle = {
        "filters": window_context(window),
        "kpis": [
            build_kpi("revenue", "Total Revenue", current_revenue, format_type="currency", change_pct=_change(current_revenue, previous_revenue), helper=window.label),
            build_kpi("orders", "Orders", current_order_count, change_pct=_change(current_order_count, previous_order_count), helper=window.label),
            build_kpi("customers", "New Customers", current_customer_count, change_pct=_change(current_customer_count, previous_customer_count), helper=window.label),
            build_kpi("traffic", "Traffic Sessions", current_sessions, change_pct=_change(current_sessions, previous_sessions), helper=window.label),
            build_kpi("low_stock", "Low Stock Alerts", low_stock_products + low_stock_inventory, helper="Catalog + POS"),
            build_kpi("pos_today", "POS Today", pos_today_total, format_type="currency", helper=timezone.localdate().strftime("%b %d, %Y")),
        ],
        "charts": {
            "revenue_trend": build_chart(
                "revenue_trend",
                "Revenue Trend",
                labels,
                [build_dataset("Revenue", revenue_values, color_index=0, fill=True)],
                active_type="area",
                subtitle="Daily gross paid revenue for the selected period.",
            ),
            "order_trend": build_chart(
                "order_trend",
                "Order Volume",
                labels,
                [build_dataset("Orders", order_values, color_index=1)],
                active_type="bar",
                type_options=("bar", "line", "area"),
                subtitle="Daily order counts.",
            ),
            "traffic_trend": build_chart(
                "traffic_trend",
                "Traffic Trend",
                labels,
                [build_dataset("Page Views", traffic_values, color_index=5)],
                active_type="line",
                subtitle="Tracked page views across the period.",
            ),
            "top_products": build_chart(
                "top_products",
                "Top Products",
                [row["product_title"] for row in top_products],
                [build_dataset("Units Sold", [row["units_sold"] or 0 for row in top_products], color_index=2)],
                active_type="bar",
                type_options=("bar", "line"),
                subtitle="Best sellers from completed commerce orders.",
            ),
        },
        "comparison": {
            "revenue_change_pct": _change(current_revenue, previous_revenue),
            "order_change_pct": _change(current_order_count, previous_order_count),
            "customer_change_pct": _change(current_customer_count, previous_customer_count),
        },
        "table_title": "Top Products",
        "table_columns": ["Product", "Units Sold", "Revenue"],
        "table_rows": [
            {
                "Product": row["product_title"],
                "Units Sold": _safe_int(row["units_sold"]),
                "Revenue": round(_safe_float(row["revenue"]), 2),
            }
            for row in top_products
        ],
        "drilldown": {
            "supported_dimensions": ["month", "category"],
        },
    }
    return _finalize_bundle(bundle)


def build_orders_bundle(window: AnalyticsWindow) -> dict[str, Any]:
    current_orders = _active_order_queryset(window)
    previous_orders = _previous_order_queryset(window)

    current_aov = current_orders.aggregate(value=Avg("total_paid"))["value"] or Decimal("0.00")
    previous_aov = previous_orders.aggregate(value=Avg("total_paid"))["value"] or Decimal("0.00")
    refunded_count = current_orders.filter(
        financial_status__in=[Order.FinancialStatus.PARTIALLY_REFUNDED, Order.FinancialStatus.REFUNDED]
    ).count()

    daily_rows = list(
        current_orders.annotate(day=TruncDate("placed_at"))
        .values("day")
        .annotate(order_count=Count("id"), revenue=Sum("total_paid"), refunded=Sum("total_refunded"))
        .order_by("day")
    )
    labels, revenue_values, order_counts = _build_daily_map(
        window.start_date,
        window.end_date,
        daily_rows,
        value_key="revenue",
        count_key="order_count",
    )
    _, refund_values, _ = _build_daily_map(
        window.start_date,
        window.end_date,
        daily_rows,
        value_key="refunded",
    )

    status_rows = list(
        current_orders.values("status")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    source_rows = list(
        current_orders.values("source")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    table_rows = [
        {
            "Day": row["day"].strftime("%Y-%m-%d"),
            "Orders": _safe_int(row["order_count"]),
            "Revenue": round(_safe_float(row["revenue"]), 2),
            "Refunded": round(_safe_float(row["refunded"]), 2),
        }
        for row in daily_rows
    ]

    total_orders = current_orders.count()
    previous_total_orders = previous_orders.count()

    return {
        "filters": window_context(window),
        "kpis": [
            build_kpi("total_orders", "Total Orders", total_orders, change_pct=_change(total_orders, previous_total_orders), helper=window.label),
            build_kpi("pending_orders", "Pending", current_orders.filter(status=Order.OrderStatus.PENDING).count(), helper="Need confirmation"),
            build_kpi("completed_orders", "Completed", current_orders.filter(status=Order.OrderStatus.COMPLETED).count(), helper="Closed successfully"),
            build_kpi("cancelled_orders", "Cancelled", current_orders.filter(status=Order.OrderStatus.CANCELLED).count(), helper="Dropped orders"),
            build_kpi("refunded_orders", "Refunded", refunded_count, helper="Partial + full refunds"),
            build_kpi("aov", "Average Order Value", current_aov, format_type="currency", change_pct=_change(current_aov, previous_aov)),
        ],
        "charts": {
            "order_volume": build_chart(
                "order_volume",
                "Order Volume Trend",
                labels,
                [build_dataset("Orders", order_counts, color_index=0)],
                active_type="bar",
                type_options=("bar", "line", "area"),
            ),
            "order_revenue": build_chart(
                "order_revenue",
                "Revenue Trend",
                labels,
                [build_dataset("Revenue", revenue_values, color_index=1, fill=True)],
                active_type="area",
                subtitle="Paid order revenue over time.",
            ),
            "status_distribution": build_chart(
                "status_distribution",
                "Order Status Distribution",
                [row["status"].replace("_", " ").title() for row in status_rows],
                [build_dataset("Orders", [row["total"] for row in status_rows], color_index=2)],
                active_type="doughnut",
                type_options=("doughnut", "pie", "bar"),
            ),
            "refund_trend": build_chart(
                "refund_trend",
                "Refund Trend",
                labels,
                [build_dataset("Refund Amount", refund_values, color_index=3)],
                active_type="line",
                type_options=("line", "bar", "area"),
            ),
            "source_mix": build_chart(
                "source_mix",
                "Order Source Mix",
                [row["source"].title() for row in source_rows],
                [build_dataset("Orders", [row["total"] for row in source_rows], color_index=4)],
                active_type="pie",
                type_options=("pie", "doughnut", "bar"),
            ),
        },
        "comparison": {
            "total_orders_change_pct": _change(total_orders, previous_total_orders),
            "aov_change_pct": _change(current_aov, previous_aov),
        },
        "table_title": "Daily Order Breakdown",
        "table_columns": ["Day", "Orders", "Revenue", "Refunded"],
        "table_rows": table_rows,
        "drilldown": {"supported_dimensions": ["month"]},
    }


def build_products_bundle(window: AnalyticsWindow) -> dict[str, Any]:
    order_items = OrderItem.objects.filter(order__in=_active_order_queryset(window))
    top_products = list(
        order_items.values("product_title")
        .annotate(units_sold=Sum("quantity"), revenue=Sum("total"))
        .order_by("-units_sold", "-revenue")[:10]
    )
    category_rows = list(
        Product.objects.filter(is_active=True, status="published")
        .values("categories__name")
        .annotate(product_count=Count("id"), sales_total=Sum("sales_count"))
        .exclude(categories__name__isnull=True)
        .order_by("-sales_total", "-product_count")[:10]
    )
    stock_rows = list(
        Product.objects.filter(is_active=True, status="published", product_type="simple")
        .values("stock_status")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    low_performing_count = Product.objects.filter(
        is_active=True,
        status="published",
        sales_count__lte=1,
    ).count()
    out_of_stock_count = Product.objects.filter(
        is_active=True,
        status="published",
        stock_status="out_of_stock",
    ).count()
    top_product = top_products[0] if top_products else {}

    return {
        "filters": window_context(window),
        "kpis": [
            build_kpi("top_units", "Best Seller Units", top_product.get("units_sold", 0), helper=top_product.get("product_title", "No sales yet")),
            build_kpi("top_revenue", "Best Seller Revenue", top_product.get("revenue", 0), format_type="currency", helper=top_product.get("product_title", "No sales yet")),
            build_kpi("low_performing", "Low Performing", low_performing_count, helper="Products with 0-1 lifetime sales"),
            build_kpi("out_of_stock", "Out Of Stock", out_of_stock_count, helper="Published simple products"),
            build_kpi("catalog_size", "Published Products", Product.objects.filter(is_active=True, status="published").count(), helper="Live catalog"),
        ],
        "charts": {
            "top_product_sales": build_chart(
                "top_product_sales",
                "Top Selling Products",
                [row["product_title"] for row in top_products],
                [build_dataset("Units Sold", [row["units_sold"] for row in top_products], color_index=0)],
                active_type="bar",
                type_options=("bar", "line"),
            ),
            "product_revenue": build_chart(
                "product_revenue",
                "Top Product Revenue",
                [row["product_title"] for row in top_products],
                [build_dataset("Revenue", [row["revenue"] for row in top_products], color_index=1)],
                active_type="bar",
                type_options=("bar", "line"),
            ),
            "category_contribution": build_chart(
                "category_contribution",
                "Category Contribution",
                [row["categories__name"] for row in category_rows],
                [build_dataset("Sales Count", [row["sales_total"] or 0 for row in category_rows], color_index=2)],
                active_type="doughnut",
                type_options=("doughnut", "pie", "bar"),
            ),
            "stock_status": build_chart(
                "stock_status",
                "Stock Status Distribution",
                [row["stock_status"].replace("_", " ").title() for row in stock_rows],
                [build_dataset("Products", [row["total"] for row in stock_rows], color_index=3)],
                active_type="pie",
                type_options=("pie", "doughnut", "bar"),
            ),
        },
        "comparison": {},
        "table_title": "Top Product Performance",
        "table_columns": ["Product", "Units Sold", "Revenue"],
        "table_rows": [
            {
                "Product": row["product_title"],
                "Units Sold": _safe_int(row["units_sold"]),
                "Revenue": round(_safe_float(row["revenue"]), 2),
            }
            for row in top_products
        ],
        "drilldown": {"supported_dimensions": ["category"]},
    }


def build_inventory_bundle(window: AnalyticsWindow) -> dict[str, Any]:
    adjustments = InventoryAdjustment.objects.filter(
        created_at__gte=window.start,
        created_at__lte=window.end,
        store_inventory__is_deleted=False,
    ).select_related("store_inventory", "store_inventory__store")
    low_stock_items = list(
        StoreInventory.objects.filter(
            is_deleted=False,
            quantity__lte=F("low_stock_threshold"),
        )
        .select_related("store", "product", "catalog_item", "catalog_item__product", "catalog_item__variant")
        .order_by("store__name", "quantity")[:20]
    )
    valuation_rows = list(
        StoreInventory.objects.filter(is_deleted=False)
        .values("store__name")
        .annotate(
            total_units=Sum("quantity"),
            inventory_value=Sum(F("quantity") * F("store_selling_price")),
        )
        .order_by("-total_units")
    )
    if not valuation_rows:
        valuation_rows = [
            {
                "store__name": store.name,
                "total_units": store.inventory.filter(is_deleted=False).aggregate(total=Sum("quantity"))["total"] or 0,
                "inventory_value": 0,
            }
            for store in Store.objects.filter(is_deleted=False, is_active=True)[:10]
        ]

    adjustment_type_rows = list(
        adjustments.values("adjustment_type")
        .annotate(total=Count("id"), quantity_delta=Sum("quantity_change"))
        .order_by("-total")
    )
    adjustment_daily = list(
        adjustments.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(quantity_delta=Sum("quantity_change"))
        .order_by("day")
    )
    labels, quantity_values, _ = _build_daily_map(
        window.start_date,
        window.end_date,
        adjustment_daily,
        value_key="quantity_delta",
    )

    low_stock_count = len(low_stock_items)
    out_of_stock_count = StoreInventory.objects.filter(is_deleted=False, quantity__lte=0).count()
    stock_adjustments = adjustments.count()
    total_units = StoreInventory.objects.filter(is_deleted=False).aggregate(total=Sum("quantity"))["total"] or 0

    return {
        "filters": window_context(window),
        "kpis": [
            build_kpi("inventory_units", "Tracked Units", total_units, helper="POS place inventory"),
            build_kpi("low_stock_items", "Low Stock Items", low_stock_count, helper="Threshold reached"),
            build_kpi("out_of_stock_items", "Out Of Stock", out_of_stock_count, helper="Need replenishment"),
            build_kpi("stock_adjustments", "Adjustments", stock_adjustments, helper=window.label),
        ],
        "charts": {
            "stock_flow": build_chart(
                "stock_flow",
                "Stock Movement Over Time",
                labels,
                [build_dataset("Quantity Delta", quantity_values, color_index=0)],
                active_type="bar",
                type_options=("bar", "line", "area"),
            ),
            "adjustment_mix": build_chart(
                "adjustment_mix",
                "Adjustment Type Mix",
                [row["adjustment_type"].replace("_", " ").title() for row in adjustment_type_rows],
                [build_dataset("Events", [row["total"] for row in adjustment_type_rows], color_index=1)],
                active_type="doughnut",
                type_options=("doughnut", "pie", "bar"),
            ),
            "branch_valuation": build_chart(
                "branch_valuation",
                "Branch Inventory Units",
                [row["store__name"] for row in valuation_rows],
                [build_dataset("Units", [row["total_units"] or 0 for row in valuation_rows], color_index=2)],
                active_type="bar",
                type_options=("bar", "line"),
            ),
        },
        "comparison": {},
        "table_title": "Low Stock Inventory",
        "table_columns": ["Place", "Item", "Available Quantity", "Low Stock Threshold"],
        "table_rows": [
            {
                "Place": inventory.store.name,
                "Item": inventory.display_name,
                "Available Quantity": inventory.available_quantity,
                "Low Stock Threshold": inventory.low_stock_threshold,
            }
            for inventory in low_stock_items
        ],
        "drilldown": {"supported_dimensions": ["store"]},
    }


def build_customers_bundle(window: AnalyticsWindow) -> dict[str, Any]:
    current_customers = _customer_queryset(window)
    previous_customers = _previous_customer_queryset(window)
    active_customers = CustomerSession.objects.filter(
        last_active_at__gte=window.start,
        last_active_at__lte=window.end,
        is_active=True,
    ).values("customer_id").distinct().count()
    returning_customers = Customer.objects.filter(total_orders__gt=1, last_order_at__gte=window.start, last_order_at__lte=window.end).count()
    average_session = PageVisit.objects.filter(created_at__gte=window.start, created_at__lte=window.end).aggregate(
        avg=Avg("engaged_seconds")
    )["avg"] or 0

    registration_rows = list(
        current_customers.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )
    labels, registration_values, _ = _build_daily_map(
        window.start_date,
        window.end_date,
        registration_rows,
        value_key="total",
    )
    acquisition_rows = list(
        Customer.objects.exclude(acquisition_source="")
        .values("acquisition_source")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    tier_rows = list(
        Customer.objects.exclude(tier="")
        .values("tier")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    heatmap_rows = list(
        CustomerSession.objects.filter(last_active_at__gte=window.start, last_active_at__lte=window.end)
        .annotate(hour=ExtractHour("last_active_at"))
        .values("hour")
        .annotate(total=Count("id"))
        .order_by("hour")
    )
    heatmap_by_hour = {row["hour"]: row["total"] for row in heatmap_rows}
    heatmap_cells = [
        {
            "hour": hour,
            "label": f"{hour:02d}:00",
            "value": _safe_int(heatmap_by_hour.get(hour)),
        }
        for hour in range(24)
    ]
    max_heat = max((cell["value"] for cell in heatmap_cells), default=0) or 1
    for cell in heatmap_cells:
        cell["intensity"] = round(cell["value"] / max_heat, 2) if cell["value"] else 0

    top_customers = list(
        Customer.objects.filter(total_spent__gt=0)
        .order_by("-total_spent", "-total_orders")[:12]
    )

    return {
        "filters": window_context(window),
        "kpis": [
            build_kpi("new_customers", "New Customers", current_customers.count(), change_pct=_change(current_customers.count(), previous_customers.count()), helper=window.label),
            build_kpi("active_customers", "Active Customers", active_customers, helper="Seen in selected period"),
            build_kpi("returning_customers", "Returning Customers", returning_customers, helper="More than one order"),
            build_kpi("avg_session", "Avg Engagement", average_session, format_type="decimal", helper="Seconds per tracked page visit"),
        ],
        "charts": {
            "registration_trend": build_chart(
                "registration_trend",
                "Registration Trend",
                labels,
                [build_dataset("Customers", registration_values, color_index=0)],
                active_type="line",
                type_options=("line", "bar", "area"),
            ),
            "acquisition_mix": build_chart(
                "acquisition_mix",
                "Acquisition Mix",
                [row["acquisition_source"].replace("_", " ").title() for row in acquisition_rows],
                [build_dataset("Customers", [row["total"] for row in acquisition_rows], color_index=1)],
                active_type="pie",
                type_options=("pie", "doughnut", "bar"),
            ),
            "tier_distribution": build_chart(
                "tier_distribution",
                "Customer Tier Distribution",
                [row["tier"].title() for row in tier_rows],
                [build_dataset("Customers", [row["total"] for row in tier_rows], color_index=2)],
                active_type="doughnut",
                type_options=("doughnut", "pie", "bar"),
            ),
            "login_heatmap": build_chart(
                "login_heatmap",
                "Hourly Activity",
                [cell["label"] for cell in heatmap_cells],
                [build_dataset("Sessions", [cell["value"] for cell in heatmap_cells], color_index=4)],
                active_type="heatmap",
                type_options=("heatmap", "bar", "line"),
                meta={"heatmap_cells": heatmap_cells},
            ),
        },
        "comparison": {
            "new_customer_change_pct": _change(current_customers.count(), previous_customers.count()),
        },
        "table_title": "Top Customers",
        "table_columns": ["Customer", "Total Orders", "Total Spent", "Last Order"],
        "table_rows": [
            {
                "Customer": customer.display_name if hasattr(customer, "display_name") else f"Customer {customer.pk}",
                "Total Orders": customer.total_orders,
                "Total Spent": round(_safe_float(customer.total_spent), 2),
                "Last Order": customer.last_order_at.strftime("%Y-%m-%d %H:%M") if customer.last_order_at else "-",
            }
            for customer in top_customers
        ],
        "drilldown": {"supported_dimensions": ["tier", "acquisition_source"]},
    }


def build_monitoring_bundle(window: AnalyticsWindow, *, source: str = "") -> dict[str, Any]:
    visits = _page_visit_queryset(window, source=source)
    sessions = VisitorSession.objects.filter(last_seen_at__gte=window.start, last_seen_at__lte=window.end)
    if source:
        sessions = sessions.filter(source=source)
    totals = visits.aggregate(
        avg_server=Avg("server_duration_ms"),
        avg_client=Avg("client_duration_ms"),
        avg_engaged=Avg("engaged_seconds"),
    )
    daily_rows = list(
        visits.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(views=Count("id"), sessions=Count("visitor_session", distinct=True))
        .order_by("day")
    )
    labels, view_values, session_values = _build_daily_map(
        window.start_date,
        window.end_date,
        daily_rows,
        value_key="views",
        count_key="sessions",
    )
    source_rows = list(
        visits.values("source")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    top_pages = list(
        visits.values("path")
        .annotate(
            views=Count("id"),
            sessions=Count("visitor_session", distinct=True),
            avg_server=Avg("server_duration_ms"),
            avg_engaged=Avg("engaged_seconds"),
        )
        .order_by("-views")[:15]
    )
    top_referrers = list(
        visits.exclude(referrer="")
        .values("referrer")
        .annotate(views=Count("id"))
        .order_by("-views", "referrer")[:10]
    )
    recent_visits = list(visits.order_by("-created_at")[:20])
    active_sessions = list(sessions.order_by("-last_seen_at")[:20])
    return _finalize_bundle({
        "filters": window_context(window),
        "kpis": [
            build_kpi("page_views", "Page Views", visits.count(), helper=window.label),
            build_kpi("sessions", "Sessions", sessions.count(), helper=window.label),
            build_kpi("known_users", "Known Users", sessions.exclude(user_identifier="").values("user_identifier").distinct().count(), helper="Distinct identified visitors"),
            build_kpi("avg_server", "Avg Server", totals["avg_server"] or 0, format_type="decimal", helper="Milliseconds"),
            build_kpi("avg_engagement", "Avg Engagement", totals["avg_engaged"] or 0, format_type="decimal", helper="Seconds"),
        ],
        "charts": {
            "visit_trend": build_chart(
                "visit_trend",
                "Visit Trend",
                labels,
                [
                    build_dataset("Views", view_values, color_index=0, fill=True),
                    build_dataset("Sessions", session_values, color_index=1),
                ],
                active_type="area",
                type_options=("area", "line", "bar"),
            ),
            "source_mix": build_chart(
                "source_mix",
                "Source Breakdown",
                [row["source"].title() for row in source_rows],
                [build_dataset("Views", [row["total"] for row in source_rows], color_index=2)],
                active_type="doughnut",
                type_options=("doughnut", "pie", "bar"),
            ),
        },
        "comparison": {},
        "table_title": "Top Pages",
        "table_columns": ["Path", "Views", "Sessions", "Avg Server", "Avg Engagement"],
        "table_rows": [
            {
                "Path": row["path"],
                "Views": _safe_int(row["views"]),
                "Sessions": _safe_int(row["sessions"]),
                "Avg Server": round(_safe_float(row["avg_server"]), 2),
                "Avg Engagement": round(_safe_float(row["avg_engaged"]), 2),
            }
            for row in top_pages
        ],
        "drilldown": {"supported_dimensions": ["path", "source"]},
        "top_referrers": top_referrers,
        "recent_visits": recent_visits,
        "active_sessions": active_sessions,
    })


def build_payments_bundle(profile, window: AnalyticsWindow) -> dict[str, Any]:
    revenue_series = get_revenue_over_time(profile, window.start, window.end)
    funnel = get_transaction_funnel(profile, window.start, window.end)
    gateway_performance = get_gateway_performance(profile, window.start, window.end)
    payment_methods = get_payment_method_breakdown(profile, window.start, window.end)
    refund_analysis = get_refund_analysis(profile, window.start, window.end)
    dispute_analysis = get_dispute_analysis(profile, window.start, window.end)

    return _finalize_bundle({
        "filters": window_context(window),
        "kpis": [
            build_kpi("gross_revenue", "Gross Revenue", sum(item["gross"] for item in revenue_series), format_type="currency", helper=window.label),
            build_kpi("net_revenue", "Net Revenue", sum(item["net"] for item in revenue_series), format_type="currency", helper=window.label),
            build_kpi("refund_volume", "Refund Volume", refund_analysis["total_refunded"], format_type="currency", helper=f"{refund_analysis['total_refunds']} refunds"),
            build_kpi("dispute_count", "Disputes", dispute_analysis["total_disputes"], helper=f"{dispute_analysis['win_rate_pct']}% win rate"),
        ],
        "charts": {
            "revenue": build_chart(
                "revenue",
                "Revenue Over Time",
                [item["period"] for item in revenue_series],
                [
                    build_dataset("Gross", [item["gross"] for item in revenue_series], color_index=0, fill=True),
                    build_dataset("Commission", [item["commission"] for item in revenue_series], color_index=2),
                    build_dataset("Net", [item["net"] for item in revenue_series], color_index=1),
                ],
                active_type="area",
                type_options=("area", "line", "bar"),
            ),
            "funnel": build_chart(
                "funnel",
                "Checkout Funnel",
                [item["stage"] for item in funnel],
                [build_dataset("Count", [item["count"] for item in funnel], color_index=3)],
                active_type="funnel",
                type_options=("funnel", "bar"),
            ),
            "gateway_performance": build_chart(
                "gateway_performance",
                "Gateway Success Rate",
                [item["gateway_provider"] for item in gateway_performance],
                [build_dataset("Success Rate %", [item["success_rate"] for item in gateway_performance], color_index=4)],
                active_type="bar",
                type_options=("bar", "line"),
            ),
            "payment_method_mix": build_chart(
                "payment_method_mix",
                "Payment Method Mix",
                [item["payment_method"] for item in payment_methods],
                [build_dataset("Volume", [item["volume"] for item in payment_methods], color_index=5)],
                active_type="doughnut",
                type_options=("doughnut", "pie", "bar"),
            ),
        },
        "comparison": {
            "refund_rate_pct": refund_analysis["refund_rate_pct"],
            "dispute_win_rate_pct": dispute_analysis["win_rate_pct"],
        },
        "table_title": "Gateway Performance",
        "table_columns": ["Gateway", "Attempts", "Success Rate", "Gross Volume", "Net Volume"],
        "table_rows": [
            {
                "Gateway": item["gateway_provider"],
                "Attempts": item["total_attempts"],
                "Success Rate": item["success_rate"],
                "Gross Volume": round(_safe_float(item["gross_volume"]), 2),
                "Net Volume": round(_safe_float(item["net_volume"]), 2),
            }
            for item in gateway_performance
        ],
        "drilldown": {"supported_dimensions": ["gateway_provider"]},
        "refund_analysis": refund_analysis,
        "dispute_analysis": dispute_analysis,
    })


def build_pos_dashboard_bundle(window: AnalyticsWindow, *, selected_store: Store | None = None) -> dict[str, Any]:
    transactions = _pos_queryset(window, store=selected_store)
    daily_rows = list(
        transactions.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("total_amount"), count=Count("id"))
        .order_by("day")
    )
    labels, daily_sales, daily_counts = _build_daily_map(
        window.start_date,
        window.end_date,
        daily_rows,
        value_key="total",
        count_key="count",
    )
    outlet_rows = list(
        _pos_queryset(window)
        .values("store__name")
        .annotate(total=Sum("total_amount"), count=Count("id"))
        .order_by("-total")[:8]
    )
    payment_rows = list(
        POSPayment.objects.filter(transaction__in=transactions)
        .values("payment_method")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )
    cashier_rows = list(
        transactions.values("cashier__first_name", "cashier__last_name")
        .annotate(total=Sum("total_amount"), count=Count("id"))
        .order_by("-total")[:8]
    )
    hourly_rows = list(
        transactions.annotate(hour=ExtractHour("created_at"))
        .values("hour")
        .annotate(total=Count("id"))
        .order_by("hour")
    )
    hour_map = {row["hour"]: row["total"] for row in hourly_rows}
    heatmap_cells = [
        {"hour": hour, "label": f"{hour:02d}:00", "value": _safe_int(hour_map.get(hour))}
        for hour in range(24)
    ]
    max_heat = max((cell["value"] for cell in heatmap_cells), default=0) or 1
    for cell in heatmap_cells:
        cell["intensity"] = round(cell["value"] / max_heat, 2) if cell["value"] else 0

    return {
        "filters": window_context(window),
        "charts": {
            "daily_sales": build_chart(
                "daily_sales",
                "Daily POS Sales",
                labels,
                [
                    build_dataset("Revenue", daily_sales, color_index=0, fill=True),
                    build_dataset("Transactions", daily_counts, color_index=1),
                ],
                active_type="area",
                type_options=("area", "line", "bar"),
            ),
            "outlet_sales": build_chart(
                "outlet_sales",
                "Outlet Performance",
                [row["store__name"] for row in outlet_rows],
                [build_dataset("Revenue", [row["total"] for row in outlet_rows], color_index=2)],
                active_type="bar",
                type_options=("bar", "line"),
            ),
            "payment_mix": build_chart(
                "payment_mix",
                "Payment Method Mix",
                [row["payment_method"].replace("_", " ").title() for row in payment_rows],
                [build_dataset("Amount", [row["total"] for row in payment_rows], color_index=3)],
                active_type="doughnut",
                type_options=("doughnut", "pie", "bar"),
            ),
            "cashier_sales": build_chart(
                "cashier_sales",
                "Cashier Comparison",
                [f"{row['cashier__first_name']} {row['cashier__last_name']}".strip() for row in cashier_rows],
                [build_dataset("Revenue", [row["total"] for row in cashier_rows], color_index=4)],
                active_type="bar",
                type_options=("bar", "line"),
            ),
            "hourly_activity": build_chart(
                "hourly_activity",
                "Hourly Activity",
                [cell["label"] for cell in heatmap_cells],
                [build_dataset("Transactions", [cell["value"] for cell in heatmap_cells], color_index=5)],
                active_type="heatmap",
                type_options=("heatmap", "bar", "line"),
                meta={"heatmap_cells": heatmap_cells},
            ),
        },
    }


def build_platform_dashboard_bundle() -> dict[str, Any]:
    shops = Shop.objects.all()
    current_month_start = timezone.localdate().replace(day=1)
    tenant_growth_rows = list(
        shops.annotate(month=TruncMonth("created_on"))
        .values("month")
        .annotate(total=Count("schema_name"))
        .order_by("month")
    )
    labels = [row["month"].strftime("%b %Y") for row in tenant_growth_rows if row["month"]]
    tenant_counts = [row["total"] for row in tenant_growth_rows]
    feature_rows = list(
        FeatureEntitlementIndex.objects.values("feature_name")
        .annotate(total=Count("schema_name", distinct=True))
        .order_by("-total")[:8]
    )
    snapshot_rows = TenantPaymentSnapshot.objects.all()
    platform_payment_volume = snapshot_rows.aggregate(total=Sum("total_transaction_volume"))["total"] or Decimal("0.00")
    active_stores = snapshot_rows.filter(account_status__iexact="active").count()
    public_traffic = PageVisit.objects.filter(schema_name="public", created_at__gte=timezone.now() - timedelta(days=30)).count()

    return {
        "kpis": [
            build_kpi("tenants", "Total Stores", shops.count(), helper="All tenant schemas"),
            build_kpi("active_stores", "Active Stores", active_stores, helper="From payment snapshots"),
            build_kpi("payment_volume", "Platform Payment Volume", platform_payment_volume, format_type="currency", helper="Projected tenant volume"),
            build_kpi("public_traffic", "Platform Traffic", public_traffic, helper="Public schema page visits (30d)"),
        ],
        "charts": {
            "tenant_growth": build_chart(
                "tenant_growth",
                "Tenant Growth",
                labels,
                [build_dataset("Stores", tenant_counts, color_index=0, fill=True)],
                active_type="area",
                type_options=("area", "line", "bar"),
            ),
            "feature_adoption": build_chart(
                "feature_adoption",
                "Feature Adoption",
                [row["feature_name"] or row["feature_name"] for row in feature_rows],
                [build_dataset("Stores", [row["total"] for row in feature_rows], color_index=1)],
                active_type="bar",
                type_options=("bar", "line"),
            ),
        },
        "as_of_label": current_month_start.strftime("%b %Y"),
    }


def build_bundle_for_page(page_key: str, window: AnalyticsWindow) -> dict[str, Any]:
    builders = {
        "overview": build_overview_bundle,
        "orders": build_orders_bundle,
        "products": build_products_bundle,
        "inventory": build_inventory_bundle,
        "customers": build_customers_bundle,
    }
    if page_key not in builders:
        raise KeyError(f"Unknown analytics page: {page_key}")
    bundle = builders[page_key](window)
    bundle["page_key"] = page_key
    return _finalize_bundle(bundle)


def build_drilldown_payload(page_key: str, *, drill_dimension: str, drill_value: str) -> dict[str, Any]:
    if page_key == "products" and drill_dimension == "category":
        products = (
            Product.objects.filter(categories__name=drill_value, is_active=True, status="published")
            .distinct()
            .order_by("-sales_count", "name")[:20]
        )
        rows = [
            {
                "Product": product.name,
                "Sales Count": product.sales_count,
                "Stock": product.stock_quantity,
                "Status": product.stock_status,
            }
            for product in products
        ]
        return {"title": f"Products in {drill_value}", "columns": ["Product", "Sales Count", "Stock", "Status"], "rows": rows}
    if page_key == "inventory" and drill_dimension == "store":
        items = (
            StoreInventory.objects.filter(store_id=drill_value, is_deleted=False)
            .select_related("store", "product", "catalog_item", "catalog_item__product", "catalog_item__variant")
            .order_by("quantity", "created_at")[:20]
        )
        rows = [
            {
                "Item": item.display_name,
                "Quantity": item.quantity,
                "Available": item.available_quantity,
                "Threshold": item.low_stock_threshold,
            }
            for item in items
        ]
        return {"title": "Store Inventory Drilldown", "columns": ["Item", "Quantity", "Available", "Threshold"], "rows": rows}
    if page_key == "orders" and drill_dimension == "month":
        try:
            selected_month = datetime.strptime(drill_value, "%Y-%m").date()
        except ValueError:
            return {"title": "Invalid drilldown request", "columns": [], "rows": []}
        month_start, month_end = _calendar_month_bounds(selected_month)
        rows = list(
            Order.objects.filter(placed_at__date__gte=month_start, placed_at__date__lte=month_end, is_test=False)
            .annotate(day=TruncDate("placed_at"))
            .values("day")
            .annotate(orders=Count("id"), revenue=Sum("total_paid"))
            .order_by("day")
        )
        return {
            "title": f"Daily Orders for {selected_month:%b %Y}",
            "columns": ["Day", "Orders", "Revenue"],
            "rows": [
                {
                    "Day": row["day"].strftime("%Y-%m-%d"),
                    "Orders": _safe_int(row["orders"]),
                    "Revenue": round(_safe_float(row["revenue"]), 2),
                }
                for row in rows
            ],
        }
    return {"title": "No drilldown available", "columns": [], "rows": []}


def bundle_to_json(bundle: dict[str, Any]) -> str:
    return json.dumps(_json_safe(bundle), cls=DjangoJSONEncoder)


def build_export_urls(base_path: str, params) -> dict[str, str]:
    query_items = {key: value for key, value in params.items() if value not in (None, "", False)}
    urls = {}
    for fmt in ("csv", "xlsx", "pdf"):
        query = query_items.copy()
        query["export"] = fmt
        encoded = urlencode(query)
        urls[fmt] = f"{base_path}?{encoded}" if encoded else base_path
    return urls


def export_bundle(bundle: dict[str, Any], *, export_format: str, filename_root: str, request=None) -> HttpResponse:
    export_format = export_format.lower()
    if export_format == "csv":
        return _export_csv(bundle, filename_root)
    if export_format == "xlsx":
        return _export_xlsx(bundle, filename_root)
    if export_format == "pdf":
        return _export_pdf(bundle, filename_root, request=request)
    raise ValueError(f"Unsupported export format: {export_format}")


def _export_csv(bundle: dict[str, Any], filename_root: str) -> HttpResponse:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["KPI", "Value"])
    for kpi in bundle.get("kpis", []):
        writer.writerow([kpi["label"], kpi["value"]])
    writer.writerow([])
    columns = bundle.get("table_columns", [])
    rows = bundle.get("table_rows", [])
    if columns:
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(column, "") for column in columns])
    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename_root}.csv"'
    return response


def _export_xlsx(bundle: dict[str, Any], filename_root: str) -> HttpResponse:
    if Workbook is None:
        return _export_csv(bundle, filename_root)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Analytics"
    worksheet.append(["KPI", "Value"])
    for kpi in bundle.get("kpis", []):
        worksheet.append([kpi["label"], kpi["value"]])
    worksheet.append([])
    columns = bundle.get("table_columns", [])
    rows = bundle.get("table_rows", [])
    if columns:
        worksheet.append(columns)
        for row in rows:
            worksheet.append([row.get(column, "") for column in columns])
    output = io.BytesIO()
    workbook.save(output)
    response = HttpResponse(
        output.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename_root}.xlsx"'
    return response


def _export_pdf(bundle: dict[str, Any], filename_root: str, *, request=None) -> HttpResponse:
    try:
        from xhtml2pdf import pisa
    except Exception:
        html = render_to_string("dashboard/analytics/export_pdf.html", {"bundle": bundle, "pdf_unavailable": True}, request=request)
        return HttpResponse(html)
    html = render_to_string("dashboard/analytics/export_pdf.html", {"bundle": bundle}, request=request)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename_root}.pdf"'
    pisa.CreatePDF(html, dest=response)
    return response
