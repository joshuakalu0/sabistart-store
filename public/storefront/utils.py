from public.utils import (
    build_seo_context,
    get_cart_item_count,
    get_site_settings as shared_get_site_settings,
)


def get_site_settings(request):
    """Compatibility wrapper for legacy storefront imports."""
    return shared_get_site_settings(request)


def get_cart(request):
    """Compatibility wrapper for legacy storefront imports."""
    return {"item_count": get_cart_item_count(request)}
