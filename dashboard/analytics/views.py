from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from dashboard.decorators import dashboard_prefix_required
from dashboard.feature_marketplace.services import FeatureEntitlementEngine, require_feature
from dashboard.sidebar_utiles import main_sidebar

from .services import (
    build_bundle_for_page,
    build_drilldown_payload,
    build_export_urls,
    bundle_to_json,
    export_bundle,
    parse_analytics_window,
)


PAGE_CONFIG = {
    "overview": {
        "title": "Business Analytics",
        "subtitle": "Revenue, orders, customers, traffic, and low-stock pressure in one shared analytics surface.",
        "active_menu": "analytics_overview",
    },
    "orders": {
        "title": "Order Analytics",
        "subtitle": "Track order volume, status mix, refunds, and source performance.",
        "active_menu": "analytics_orders",
    },
    "products": {
        "title": "Product Analytics",
        "subtitle": "See which products are winning, stalling, and putting pressure on stock.",
        "active_menu": "analytics_products",
    },
    "inventory": {
        "title": "Inventory Analytics",
        "subtitle": "Monitor stock flow, low-stock risk, and branch-level inventory pressure.",
        "active_menu": "analytics_inventory",
    },
    "customers": {
        "title": "Customer Analytics",
        "subtitle": "Follow customer growth, activity, engagement, and value concentration.",
        "active_menu": "analytics_customers",
    },
}


def _page_context(prefix: str, page_key: str, bundle: dict):
    config = PAGE_CONFIG[page_key]
    query_params = {
        "period": bundle["filters"]["period"],
        "start": bundle["filters"]["start"],
        "end": bundle["filters"]["end"],
    }
    if bundle["filters"]["compare"]:
        query_params["compare"] = "1"
    page_url = reverse(f"dashboard:analytics:{page_key}", kwargs={"prefix": prefix})
    bundle["export_urls"] = build_export_urls(page_url, query_params)
    engine = FeatureEntitlementEngine()
    return {
        "prefix": prefix,
        "page_key": page_key,
        "page_title": config["title"],
        "page_subtitle": config["subtitle"],
        "active_menu": config["active_menu"],
        "sidebar": main_sidebar(prefix, config["active_menu"]),
        "feature_access_map": engine.get_all_entitlements(),
        "analytics_bundle": bundle,
        "analytics_bundle_json": bundle_to_json(bundle),
        "analytics_nav": [
            {
                "key": key,
                "label": value["title"].replace(" Analytics", ""),
                "url": reverse(f"dashboard:analytics:{key}", kwargs={"prefix": prefix}),
                "active": key == page_key,
            }
            for key, value in PAGE_CONFIG.items()
        ],
    }


def _render_page(request, prefix: str, page_key: str):
    window = parse_analytics_window(request.GET)
    bundle = build_bundle_for_page(page_key, window)
    export_format = (request.GET.get("export") or "").strip().lower()
    if export_format:
        return export_bundle(bundle, export_format=export_format, filename_root=f"{page_key}-analytics", request=request)
    return render(request, "dashboard/analytics/page.html", _page_context(prefix, page_key, bundle))


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def overview(request, prefix):
    return _render_page(request, prefix, "overview")


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def orders(request, prefix):
    return _render_page(request, prefix, "orders")


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def products(request, prefix):
    return _render_page(request, prefix, "products")


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def inventory(request, prefix):
    return _render_page(request, prefix, "inventory")


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def customers(request, prefix):
    return _render_page(request, prefix, "customers")


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def data(request, prefix, page_key: str):
    window = parse_analytics_window(request.GET)
    bundle = build_bundle_for_page(page_key, window)
    return JsonResponse(bundle)


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def drilldown(request, prefix, page_key: str):
    payload = build_drilldown_payload(
        page_key,
        drill_dimension=(request.GET.get("drill_dimension") or "").strip(),
        drill_value=(request.GET.get("drill_value") or "").strip(),
    )
    return JsonResponse(payload)
