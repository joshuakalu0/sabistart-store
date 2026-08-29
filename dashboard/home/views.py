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
    except (ProgrammingError, OperationalError):
        # Tenant schema migrations haven't completed yet — redirect to provisioning
        return redirect(f"/platform/register/provisioning/?schema={prefix}&next=/dashboard/{prefix}/")

    engine = FeatureEntitlementEngine()
    analytics_window = parse_analytics_window({"period": "30d"})
    overview_bundle = build_overview_bundle(analytics_window)
    context = {
        'prefix': prefix,
        'page_title': 'Dashboard',
        'active_menu': 'dashboard',
        'sidebar': main_sidebar(prefix, 'dashboard'),
        'store_name': settings_obj.store_name,
        'feature_access_map': engine.get_all_entitlements(),
        'overview_bundle': overview_bundle,
        'overview_bundle_json': bundle_to_json(overview_bundle),
    }
    return render(request, 'dashboard/home/index.html', context)

