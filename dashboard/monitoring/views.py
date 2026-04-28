from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from dashboard.analytics.services import build_export_urls, build_monitoring_bundle, bundle_to_json, export_bundle, parse_analytics_window
from dashboard.decorators import dashboard_prefix_required
from dashboard.feature_marketplace.services import FeatureEntitlementEngine, require_feature
from dashboard.sidebar_utiles import main_sidebar
from public.monitoring.models import VisitorSession


ALLOWED_WINDOWS = (7, 14, 30, 90)
ALLOWED_SOURCES = {
    "",
    VisitorSession.Source.STOREFRONT,
    VisitorSession.Source.DASHBOARD,
}
SOURCE_LABELS = {
    "": "All sources",
    VisitorSession.Source.STOREFRONT: "Storefront only",
    VisitorSession.Source.DASHBOARD: "Dashboard only",
}


def _parse_days(raw_value: str) -> int:
    try:
        candidate = int(raw_value or 14)
    except (TypeError, ValueError):
        return 14
    return candidate if candidate in ALLOWED_WINDOWS else 14


def _parse_source(raw_value: str) -> str:
    candidate = (raw_value or "").strip().lower()
    return candidate if candidate in ALLOWED_SOURCES else ""


def _build_page_context(prefix: str, page_title: str, active_menu: str, *, monitoring_bundle: dict, **extra):
    engine = FeatureEntitlementEngine()
    query_params = {
        "period": monitoring_bundle["filters"]["period"],
        "start": monitoring_bundle["filters"]["start"],
        "end": monitoring_bundle["filters"]["end"],
    }
    if monitoring_bundle["filters"]["compare"]:
        query_params["compare"] = "1"
    if extra.get("selected_source"):
        query_params["source"] = extra["selected_source"]
    page_route = {
        "monitoring_overview": "dashboard:monitoring:overview",
        "monitoring_pages": "dashboard:monitoring:pages",
        "monitoring_sessions": "dashboard:monitoring:sessions",
    }[active_menu]
    context = {
        "prefix": prefix,
        "page_title": page_title,
        "active_menu": active_menu,
        "sidebar": main_sidebar(prefix, active_menu),
        "feature_access_map": engine.get_all_entitlements(),
        "source_options": [
            {"value": "", "label": SOURCE_LABELS[""]},
            {"value": VisitorSession.Source.STOREFRONT, "label": SOURCE_LABELS[VisitorSession.Source.STOREFRONT]},
            {"value": VisitorSession.Source.DASHBOARD, "label": SOURCE_LABELS[VisitorSession.Source.DASHBOARD]},
        ],
        "monitoring_bundle": monitoring_bundle,
        "monitoring_bundle_json": bundle_to_json(monitoring_bundle),
        "monitoring_export_urls": build_export_urls(
            extra.get("page_url") or "",
            query_params,
        ),
        "page_url": extra.get("page_url"),
    }
    context.update(extra)
    return context


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def overview(request, prefix):
    window = parse_analytics_window(request.GET)
    source = _parse_source(request.GET.get("source"))
    bundle = build_monitoring_bundle(window, source=source)
    export_format = (request.GET.get("export") or "").strip().lower()
    if export_format:
        return export_bundle(bundle, export_format=export_format, filename_root="monitoring-overview", request=request)
    context = _build_page_context(
        prefix,
        "Traffic Analytics",
        "monitoring_overview",
        monitoring_bundle=bundle,
        selected_source=source,
        selected_source_label=SOURCE_LABELS[source],
        page_url=request.path,
    )
    return render(request, "dashboard/monitoring/overview.html", context)


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def pages(request, prefix):
    window = parse_analytics_window(request.GET)
    source = _parse_source(request.GET.get("source"))
    bundle = build_monitoring_bundle(window, source=source)
    export_format = (request.GET.get("export") or "").strip().lower()
    if export_format:
        return export_bundle(bundle, export_format=export_format, filename_root="monitoring-pages", request=request)
    context = _build_page_context(
        prefix,
        "Top Pages",
        "monitoring_pages",
        monitoring_bundle=bundle,
        selected_source=source,
        selected_source_label=SOURCE_LABELS[source],
        page_url=request.path,
    )
    return render(request, "dashboard/monitoring/pages.html", context)


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def sessions(request, prefix):
    window = parse_analytics_window(request.GET)
    source = _parse_source(request.GET.get("source"))
    bundle = build_monitoring_bundle(window, source=source)
    export_format = (request.GET.get("export") or "").strip().lower()
    if export_format:
        return export_bundle(bundle, export_format=export_format, filename_root="monitoring-sessions", request=request)
    context = _build_page_context(
        prefix,
        "Visitor Sessions",
        "monitoring_sessions",
        monitoring_bundle=bundle,
        selected_source=source,
        selected_source_label=SOURCE_LABELS[source],
        page_url=request.path,
    )
    return render(request, "dashboard/monitoring/sessions.html", context)
