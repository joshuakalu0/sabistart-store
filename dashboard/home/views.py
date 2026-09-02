from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db import ProgrammingError, OperationalError
from dashboard.decorators import dashboard_prefix_required
from dashboard.feature_marketplace.services import FeatureEntitlementEngine
from dashboard.sidebar_utiles import main_sidebar
from dashboard.store_settings.models import StoreSettings
from dashboard.analytics.services import build_overview_bundle, bundle_to_json, parse_analytics_window


@login_required
@dashboard_prefix_required
def dashboard_home(request, prefix):
    """Dashboard home page - requires valid prefix."""
    try:
        settings_obj = StoreSettings.objects.get_settings()
        store_name = settings_obj.store_name if settings_obj else f"Store - {prefix}"
    except (ProgrammingError, OperationalError):
        store_name = f"Store - {prefix}"
    except Exception:
        store_name = f"Store - {prefix}"

    engine = FeatureEntitlementEngine()
    try:
        analytics_window = parse_analytics_window({"period": "30d"})
        overview_bundle = build_overview_bundle(analytics_window)
    except Exception:
        overview_bundle = {}

    try:
        feature_access_map = engine.get_all_entitlements()
    except Exception:
        feature_access_map = {}

    try:
        bundle_json = bundle_to_json(overview_bundle)
    except Exception:
        bundle_json = "{}"

    try:
        sidebar = main_sidebar(prefix, 'dashboard')
    except Exception:
        sidebar = []

    context = {
        'prefix': prefix,
        'page_title': 'Dashboard',
        'active_menu': 'dashboard',
        'sidebar': sidebar,
        'store_name': store_name,
        'feature_access_map': feature_access_map,
        'overview_bundle': overview_bundle,
        'overview_bundle_json': bundle_json,
    }
    return render(request, 'dashboard/home/index.html', context)


