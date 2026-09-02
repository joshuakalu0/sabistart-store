"""
Storefront Context Processors
Global context injected into every template.
"""

import logging

from django.db import connection

from public.storefront.services import (
    get_active_flash_sale,
    get_active_discount_campaigns,
    get_account_navigation,
    get_cart_summary,
    get_compare_products,
    get_featured_brands,
    get_feature_flags,
    get_footer_link_groups,
    get_navigation_links,
    get_navigation_categories,
    get_recently_viewed_products,
    get_shop_context,
    get_social_platforms,
    get_store_settings_cached,
    get_store_editorial_cards,
    get_storefront_announcement,
    build_theme_tokens,
    get_utility_navigation,
    get_top_categories,
    get_wishlist_products,
)

logger = logging.getLogger(__name__)


def _should_skip_storefront_context(request) -> bool:
    """
    Storefront context is tenant-only. Public-schema platform/admin requests and
    internal dashboard/auth routes do not need storefront cart/catalog tables.
    """
    if getattr(connection, "schema_name", None) == "public":
        return True

    path = getattr(request, "path_info", "") or getattr(request, "path", "") or ""
    return path.startswith(("/platform/", "/admin/", "/__monitoring/", "/dashboard/", "/account/"))


def global_storefront_context(request):
    """
    Injected into every template via settings.TEMPLATES context_processors.
    Must never raise an exception.
    """
    context = {}

    if _should_skip_storefront_context(request):
        return context

    try:
        site_settings = None
        try:
            site_settings = get_store_settings_cached(request)
        except Exception:
            pass

        cart_summary = {"item_count": 0, "items": [], "subtotal": 0, "total": 0}
        try:
            cart_summary = get_cart_summary(request)
        except Exception:
            pass

        wishlist_products = []
        try:
            wishlist_products = get_wishlist_products(request)
        except Exception:
            pass

        compare_products = []
        try:
            compare_products = get_compare_products(request)
        except Exception:
            pass

        recently_viewed = []
        try:
            recently_viewed = get_recently_viewed_products(request)
        except Exception:
            pass

        context["shop"] = get_shop_context(request)
        context["site_settings"] = site_settings
        context["store_settings"] = site_settings
        context["theme_tokens"] = build_theme_tokens(request)
        context["top_categories"] = get_top_categories(request)
        context["navigation_links"] = get_navigation_links(request)
        context["navigation_categories"] = get_navigation_categories(request, limit=12)
        context["utility_navigation"] = get_utility_navigation(request)
        context["footer_link_groups"] = get_footer_link_groups(request)
        context["account_navigation"] = get_account_navigation(request)
        context["social_platforms"] = get_social_platforms(request)
        context["cart_summary"] = cart_summary
        context["cart_item_count"] = cart_summary.get("item_count", 0)
        context["wishlist_count"] = len(wishlist_products)
        context["compare_count"] = len(compare_products)
        context["recently_viewed_count"] = len(recently_viewed)
        context["is_maintenance_mode"] = getattr(site_settings, "maintenance_mode", False) if site_settings else False
        context["current_currency"] = getattr(site_settings, "currency", "USD") if site_settings else "USD"
        context["current_region"] = getattr(request, "session", {}).get("region_preference", "NG") if hasattr(request, "session") else "NG"
        context["active_flash_sale"] = get_active_flash_sale(request)
        context["active_discount_campaigns"] = get_active_discount_campaigns(request)
        context["featured_brands"] = get_featured_brands(request)
        context["storefront_announcement"] = get_storefront_announcement(request)
        context["store_editorial_cards"] = get_store_editorial_cards(request)
        context["storefront_features"] = get_feature_flags(request)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error in global_storefront_context: %s", exc, exc_info=True)

    return context

