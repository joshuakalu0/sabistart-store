from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from dashboard.decorators import dashboard_prefix_required
from dashboard.feature_marketplace.services import require_feature
from dashboard.pricing.models import DiscountCode, DiscountUsage
from dashboard.pricing.utiles.analytics import (
    get_automatic_discount_performance,
    get_discount_performance,
    get_discount_usage_over_time,
    get_flash_sale_performance,
    get_top_discount_codes,
)
from dashboard.pricing.utiles.dashboard import get_pricing_health_checks
from dashboard.sidebar_utiles import main_sidebar
from public.cart.models import Order, OrderDiscount, OrderItem


def _parse_window(request):
    end_date = request.GET.get("end") or timezone.localdate().isoformat()
    start_date = request.GET.get("start")
    if not start_date:
        start_date = (timezone.localdate() - timezone.timedelta(days=29)).isoformat()
    start = timezone.datetime.fromisoformat(start_date).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.get_current_timezone())
    end = timezone.datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.get_current_timezone())
    return start, end


def _money(value):
    return Decimal(value or 0).quantize(Decimal("0.01"))


def _kpi(label, value, fmt="number", helper=""):
    return {"label": label, "value": value, "format": fmt, "helper": helper}


def _build_pricing_analytics_bundle(start, end):
    discounted_orders = Order.objects.filter(
        placed_at__gte=start,
        placed_at__lte=end,
        discounts__isnull=False,
    ).distinct()
    all_orders = Order.objects.filter(
        placed_at__gte=start,
        placed_at__lte=end,
    )
    non_discounted_orders = all_orders.exclude(id__in=discounted_orders.values_list("id", flat=True))

    discount_perf = get_discount_performance(start, end)
    top_codes = get_top_discount_codes(start, end, limit=8)
    auto_perf = get_automatic_discount_performance(start, end)[:8]
    flash_perf = get_flash_sale_performance(start, end)[:6]
    trend = get_discount_usage_over_time(start, end, granularity="day")
    health_checks = get_pricing_health_checks()

    revenue_attributed = discounted_orders.aggregate(total=Sum("total_price"))["total"] or Decimal("0.00")
    avg_discounted_aov = discounted_orders.aggregate(avg=Avg("total_price"))["avg"] or Decimal("0.00")
    avg_regular_aov = non_discounted_orders.aggregate(avg=Avg("total_price"))["avg"] or Decimal("0.00")
    remaining_uses = sum(
        max(0, int(code.usage_limit or 0) - int(code.usage_count or 0))
        for code in DiscountCode.objects.filter(usage_limit__isnull=False)
    )

    top_products = list(
        OrderItem.objects.filter(
            order__placed_at__gte=start,
            order__placed_at__lte=end,
            total_discount__gt=0,
        )
        .values("product_title", "sku")
        .annotate(
            discounted_orders=Count("order", distinct=True),
            units=Sum("quantity"),
            discount_amount=Sum("total_discount"),
            revenue=Sum("total"),
        )
        .order_by("-discount_amount", "-units")[:10]
    )

    suspicious_by_ip = list(
        DiscountUsage.objects.filter(
            is_reversed=False,
            used_at__gte=start,
            used_at__lte=end,
            ip_address__isnull=False,
        )
        .exclude(ip_address="")
        .values("discount_code__code", "ip_address")
        .annotate(uses=Count("id"))
        .filter(uses__gte=3)
        .order_by("-uses")[:8]
    )
    suspicious_plus_alias = []
    plus_rows = DiscountUsage.objects.filter(
        is_reversed=False,
        used_at__gte=start,
        used_at__lte=end,
    ).exclude(customer_email="").values("discount_code__code", "customer_email")
    alias_counter = {}
    for row in plus_rows:
        email = (row["customer_email"] or "").lower()
        if "@" not in email or "+" not in email:
            continue
        local, domain = email.split("@", 1)
        alias_key = (row["discount_code__code"], f"{local.split('+', 1)[0]}@{domain}")
        alias_counter[alias_key] = alias_counter.get(alias_key, 0) + 1
    for (code, normalized_email), uses in sorted(alias_counter.items(), key=lambda item: item[1], reverse=True)[:8]:
        if uses >= 3:
            suspicious_plus_alias.append(
                {"discount_code__code": code, "normalized_email": normalized_email, "uses": uses}
            )

    usage_rows = list(
        DiscountUsage.objects.filter(
            is_reversed=False,
            used_at__gte=start,
            used_at__lte=end,
        )
        .values("discount_code__code", "discount_code__title")
        .annotate(
            uses=Count("id"),
            discount_amount=Sum("discount_amount"),
            avg_subtotal=Avg("order_subtotal_at_use"),
        )
        .order_by("-discount_amount", "-uses")
    )

    bundle = {
        "filters": {
            "start": start.date().isoformat(),
            "end": end.date().isoformat(),
            "label": f"{start.date().isoformat()} to {end.date().isoformat()}",
        },
        "kpis": [
            _kpi("Redemptions", discount_perf["total_uses"], "number", "Successful code redemptions in range"),
            _kpi("Discount Given", discount_perf["total_discount_amount"], "currency", "Unreversed discount value"),
            _kpi("Revenue Attributed", revenue_attributed, "currency", "Orders that carried at least one discount row"),
            _kpi("AOV With Discount", avg_discounted_aov, "currency", "Average order value for discounted orders"),
            _kpi("AOV Without Discount", avg_regular_aov, "currency", "Average order value for non-discounted orders"),
            _kpi("Remaining Uses", remaining_uses, "number", "Unused limited discount capacity"),
        ],
        "charts": {
            "usage_trend": {
                "title": "Discount Usage Over Time",
                "labels": [row["period"] for row in trend],
                "datasets": [
                    {"label": "Redemptions", "data": [row["uses"] for row in trend], "borderColor": "#2563eb", "backgroundColor": "rgba(37,99,235,0.16)", "fill": True},
                    {"label": "Discount Value", "data": [float(row["discount_amount"]) for row in trend], "borderColor": "#ea580c", "backgroundColor": "rgba(234,88,12,0.12)", "fill": False},
                ],
            },
            "top_codes": {
                "title": "Top Discount Codes",
                "labels": [row["code"] for row in top_codes],
                "datasets": [
                    {"label": "Discount Value", "data": [float(row["total_discount"]) for row in top_codes], "backgroundColor": "#0f766e"},
                ],
            },
            "top_products": {
                "title": "Top Discounted Products",
                "labels": [row["product_title"][:28] for row in top_products],
                "datasets": [
                    {"label": "Discount Value", "data": [float(row["discount_amount"] or 0) for row in top_products], "backgroundColor": "#7c3aed"},
                ],
            },
        },
        "tables": {
            "codes": top_codes,
            "automatic": auto_perf,
            "flash_sales": flash_perf,
            "products": top_products,
            "usage_rows": usage_rows,
        },
        "fraud_signals": {
            "ip_velocity": suspicious_by_ip,
            "plus_aliases": suspicious_plus_alias,
        },
        "health_checks": health_checks,
    }
    return bundle


def _csv_response(bundle, filename: str):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Section", "Label", "Value", "Extra"])
    for item in bundle["kpis"]:
        writer.writerow(["kpi", item["label"], item["value"], item["helper"]])
    for row in bundle["tables"]["codes"]:
        writer.writerow(["top_code", row["code"], row["total_discount"], row["uses"]])
    for row in bundle["tables"]["automatic"]:
        writer.writerow(["automatic_discount", row["title"], row["total_discount_in_period"], row["orders_in_period"]])
    for row in bundle["tables"]["products"]:
        writer.writerow(["top_product", row["product_title"], row["discount_amount"], row["units"]])
    for row in bundle["tables"]["flash_sales"]:
        writer.writerow(["flash_sale", row["name"], row["total_revenue_est"], row["units_sold_at_flash_price"]])
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def pricing_analytics(request, prefix):
    start, end = _parse_window(request)
    bundle = _build_pricing_analytics_bundle(start, end)
    return render(
        request,
        "dashboard/pricing/analytics.html",
        {
            "prefix": prefix,
            "page_title": "Pricing Analytics",
            "active_menu": "pricing_discounts",
            "sidebar": main_sidebar(prefix, "pricing_discounts"),
            "analytics_bundle": bundle,
            "analytics_json_url": reverse("dashboard:pricing:pricing_analytics_data", kwargs={"prefix": prefix}),
            "analytics_csv_url": reverse("dashboard:pricing:pricing_analytics_export_csv", kwargs={"prefix": prefix}),
        },
    )


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def pricing_analytics_data(request, prefix):
    start, end = _parse_window(request)
    return JsonResponse(_build_pricing_analytics_bundle(start, end))


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def pricing_analytics_export_csv(request, prefix):
    start, end = _parse_window(request)
    bundle = _build_pricing_analytics_bundle(start, end)
    return _csv_response(bundle, filename=f"pricing-analytics-{start.date().isoformat()}-{end.date().isoformat()}.csv")
