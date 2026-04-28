from dashboard.sidebar_utiles import main_sidebar
from dashboard.feature_marketplace.services import FeatureEntitlementEngine


def build_page_context(prefix: str, page_title: str, active_menu: str, **extra):
    engine = FeatureEntitlementEngine()
    context = {
        "prefix": prefix,
        "page_title": page_title,
        "active_menu": active_menu,
        "sidebar": main_sidebar(prefix, active_menu),
        "feature_access_map": engine.get_all_entitlements(),
    }
    context.update(extra)
    return context
