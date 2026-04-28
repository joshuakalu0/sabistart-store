"""
Storefront Utilities — User-Facing Layer
=========================================
Production-ready utility functions for the multi-tenant e-commerce platform.
Covers every area a customer-facing view, template, or middleware might need.

Architecture contract:
  - All functions operate inside the CURRENT tenant schema (django-tenants
    sets connection.schema_name before calling any view).
  - Heavy objects are cached under schema-namespaced keys to avoid cross-
    tenant cache pollution.
  - Every function is independently importable — no circular-import risk.

Modules
-------
1.  Cache helpers           – schema-aware cache key builders + bulk invalidation
2.  Settings accessors      – cached singleton getters for every settings model
3.  Theme / CSS utilities   – CSS variable generation, font-URL builder, dark-mode
4.  Navigation utilities    – menu trees, breadcrumbs, mega-menu builder
5.  Currency / price        – formatting, tax calculation, range helpers
6.  Homepage section data   – ordered section resolver for homepage templates
7.  Header / footer context – ready-to-use template context dicts
8.  Search utilities        – live-search query helpers, synonym expansion
9.  Product display helpers – badge logic, image-ratio CSS, hover-effect classes
10. Cart utilities          – session-based cart CRUD, totals, coupon application
11. Wishlist utilities      – session + DB wishlist helpers
12. Popup / notification    – popup eligibility, dismissal tracking
13. SEO utilities           – meta tags, structured data (JSON-LD), sitemap ping
14. Email rendering         – branding context for transactional emails
15. Mobile / PWA            – manifest.json generation, push-subscription check
16. Maintenance mode        – gate middleware helper
17. Context processors      – single `store_context` processor for templates
"""

from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
from typing import Any, Dict, List, Optional, Tuple

from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.text import slugify

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy model imports — avoids circular imports when utils are used in models
# ---------------------------------------------------------------------------
def _models():
    """Deferred import of all settings models."""
    from dashboard.store_settings import models as M  # noqa: adjust to your actual path
    return M


# ============================================================================
# 1. CACHE HELPERS
# ============================================================================

CACHE_TTL_SHORT  = 60 * 5        # 5 minutes  – volatile data
CACHE_TTL_MEDIUM = 60 * 30       # 30 minutes – semi-static
CACHE_TTL_LONG   = 60 * 60 * 4  # 4 hours    – near-static settings


def _schema() -> str:
    """Return the current tenant schema name (safe for cache keys)."""
    return connection.schema_name or "public"


def cache_key(namespace: str, *parts: Any) -> str:
    """
    Build a schema-namespaced cache key.

    Example:
        cache_key("theme", "css")  →  "t:mystore:theme:css"
    """
    schema = _schema()
    suffix = ":".join(str(p) for p in parts)
    raw = f"t:{schema}:{namespace}:{suffix}"
    # Keep key ≤ 250 chars (memcached limit)
    if len(raw) > 250:
        raw = f"t:{schema}:{namespace}:{hashlib.md5(suffix.encode()).hexdigest()}"
    return raw


def invalidate_settings_cache() -> None:
    """
    Bulk-invalidate every settings-related cache key for this tenant.
    Call after any settings model is saved.
    """
    namespaces = [
        "store_settings", "theme_settings", "header_settings",
        "footer_settings", "homepage_layout", "product_display",
        "product_page", "cart_settings", "checkout_settings",
        "search_settings", "email_template", "social_links",
        "notification_settings", "mobile_app", "blog_settings",
        "popup_settings", "performance_settings", "nav_menu",
        "theme_css", "store_context",
    ]
    keys = [cache_key(ns, "singleton") for ns in namespaces]
    keys.append(cache_key("nav", "all_menus"))
    cache.delete_many(keys)
    logger.debug("[%s] Settings cache invalidated (%d keys)", _schema(), len(keys))


def cached_setting(namespace: str, loader_fn, ttl: int = CACHE_TTL_LONG):
    """
    Generic caching wrapper for singleton settings objects.

    Usage:
        store = cached_setting("store_settings", lambda: StoreSettings.objects.first())
    """
    key = cache_key(namespace, "singleton")
    obj = cache.get(key)
    if obj is None:
        obj = loader_fn()
        if obj is not None:
            cache.set(key, obj, ttl)
    return obj


# ============================================================================
# 2. SETTINGS ACCESSORS
# ============================================================================

def get_store_settings():
    """Return the singleton StoreSettings for the current tenant (cached)."""
    from .models import StoreSettings  # noqa: adjust import path
    return cached_setting("store_settings", lambda: StoreSettings.objects.first())


def get_theme_settings():
    from .models import ThemeSettings  # noqa
    return cached_setting("theme_settings", lambda: ThemeSettings.objects.filter(is_active=True).first())


def get_header_settings():
    from .models import HeaderSettings  # noqa
    return cached_setting("header_settings", lambda: HeaderSettings.objects.first())


def get_footer_settings():
    from .models import FooterSettings  # noqa
    return cached_setting("footer_settings", lambda: FooterSettings.objects.first())


def get_homepage_layout():
    from .models import HomepageLayout  # noqa
    return cached_setting("homepage_layout", lambda: HomepageLayout.objects.first())


def get_product_display_settings():
    from .models import ProductDisplaySettings  # noqa
    return cached_setting("product_display", lambda: ProductDisplaySettings.objects.first())


def get_product_page_settings():
    from .models import ProductPageSettings  # noqa
    return cached_setting("product_page", lambda: ProductPageSettings.objects.first())


def get_cart_settings():
    from .models import CartSettings  # noqa
    return cached_setting("cart_settings", lambda: CartSettings.objects.first())


def get_checkout_settings():
    from .models import CheckoutSettings  # noqa
    return cached_setting("checkout_settings", lambda: CheckoutSettings.objects.first())


def get_search_settings():
    from .models import SearchSettings  # noqa
    return cached_setting("search_settings", lambda: SearchSettings.objects.first())


def get_email_template_settings():
    from .models import EmailTemplateSettings  # noqa
    return cached_setting("email_template", lambda: EmailTemplateSettings.objects.first())


def get_social_links():
    from .models import SocialMediaLinks  # noqa
    return cached_setting("social_links", lambda: SocialMediaLinks.objects.first())


def get_notification_settings():
    from .models import NotificationSettings  # noqa
    return cached_setting("notification_settings", lambda: NotificationSettings.objects.first())


def get_mobile_app_settings():
    from .models import MobileAppSettings  # noqa
    return cached_setting("mobile_app", lambda: MobileAppSettings.objects.first())


def get_blog_settings():
    from .models import BlogSettings  # noqa
    return cached_setting("blog_settings", lambda: BlogSettings.objects.first())


def get_popup_settings():
    from .models import PopupSettings  # noqa
    return cached_setting("popup_settings", lambda: PopupSettings.objects.first())


def get_performance_settings():
    from .models import PerformanceSettings  # noqa
    return cached_setting("performance_settings", lambda: PerformanceSettings.objects.first())


# ============================================================================
# 3. THEME / CSS UTILITIES
# ============================================================================

def get_theme_css_variables() -> str:
    """
    Return the full :root { … } CSS block generated from ThemeSettings.
    Result is cached per tenant.

    Returns:
        A <style> tag string safe to inject into <head>.
    """
    key = cache_key("theme_css", "variables")
    css = cache.get(key)
    if css:
        return css

    theme = get_theme_settings()
    if theme is None:
        return ""

    css = theme.generate_css_variables()
    cache.set(key, css, CACHE_TTL_LONG)
    return css


def get_google_fonts_url() -> Optional[str]:
    """
    Build a single Google Fonts URL covering both heading and body fonts.

    Returns:
        URL string or None if only system fonts are used.
    """
    theme = get_theme_settings()
    if not theme:
        return None

    _GOOGLE_FONTS = {
        "inter": "Inter:wght@300;400;500;600;700;800",
        "roboto": "Roboto:wght@300;400;500;700",
        "open-sans": "Open+Sans:wght@300;400;600;700",
        "lato": "Lato:wght@300;400;700",
        "montserrat": "Montserrat:wght@300;400;500;600;700;800",
        "poppins": "Poppins:wght@300;400;500;600;700",
        "playfair": "Playfair+Display:wght@400;500;600;700",
        "merriweather": "Merriweather:wght@300;400;700",
    }

    fonts = set()
    for attr in ("heading_font", "body_font"):
        val = getattr(theme, attr, "system")
        if val != "system" and val != "custom" and val in _GOOGLE_FONTS:
            fonts.add(_GOOGLE_FONTS[val])

    if theme.custom_font_url:
        return theme.custom_font_url

    if not fonts:
        return None

    return "https://fonts.googleapis.com/css2?family=" + "&family=".join(sorted(fonts)) + "&display=swap"


def get_theme_meta() -> Dict[str, Any]:
    """
    Return a dict of the most-used theme values for template context.
    Useful for injecting into base template context without passing the full ORM object.
    """
    theme = get_theme_settings()
    if not theme:
        return {}
    return {
        "primary_color": theme.primary_color,
        "secondary_color": theme.secondary_color,
        "accent_color": theme.accent_color,
        "background_color": theme.background_color,
        "text_color": theme.text_color,
        "border_radius": theme.border_radius,
        "container_width": theme.container_width,
        "use_shadows": theme.use_shadows,
        "shadow_intensity": theme.shadow_intensity,
        "heading_font": theme.heading_font,
        "body_font": theme.body_font,
        "google_fonts_url": get_google_fonts_url(),
    }


# ============================================================================
# 4. NAVIGATION UTILITIES
# ============================================================================

def get_navigation_menu(location: str = "header") -> Optional[Any]:
    """
    Return the NavigationMenu object for a given location (header/footer/sidebar).
    Result is cached per tenant + location.
    """
    from .models import NavigationMenu  # noqa
    key = cache_key("nav", location)
    menu = cache.get(key)
    if menu is None:
        menu = (
            NavigationMenu.objects
            .prefetch_related("items__children")
            .filter(location=location, is_active=True)
            .first()
        )
        if menu:
            cache.set(key, menu, CACHE_TTL_MEDIUM)
    return menu


def build_menu_tree(location: str = "header") -> List[Dict]:
    """
    Return a serializable nested list representation of the navigation tree.
    Suitable for JSON serialization or template iteration.

    Returns list of dicts:
        [
          {
            "label": "Shop",
            "url": "/shop/",
            "open_in_new_tab": False,
            "children": [...]
          },
          ...
        ]
    """
    menu = get_navigation_menu(location)
    if not menu:
        return []

    def _serialize_item(item) -> Dict:
        return {
            "label": item.label,
            "url": item.url or "#",
            "open_in_new_tab": getattr(item, "open_in_new_tab", False),
            "icon": getattr(item, "icon", None),
            "badge": getattr(item, "badge_text", None),
            "children": [_serialize_item(c) for c in item.children.filter(is_active=True).order_by("order")],
        }

    top_level = menu.items.filter(parent=None, is_active=True).order_by("order")
    return [_serialize_item(i) for i in top_level]


def build_breadcrumbs(*crumbs: Tuple[str, Optional[str]]) -> List[Dict]:
    """
    Build a breadcrumb list from (label, url) tuples.
    The last item is automatically marked as current (no URL needed).

    Usage:
        build_breadcrumbs(("Home", "/"), ("Electronics", "/electronics/"), ("Phones", None))

    Returns:
        [{"label": "Home", "url": "/", "current": False}, ...]
    """
    result = []
    total = len(crumbs)
    for idx, (label, url) in enumerate(crumbs):
        result.append({
            "label": label,
            "url": url,
            "current": idx == total - 1,
        })
    return result


# ============================================================================
# 5. CURRENCY / PRICE UTILITIES
# ============================================================================

_CURRENCY_SYMBOLS = {
    "USD": "$",  "EUR": "€",  "GBP": "£",  "NGN": "₦",
    "GHS": "₵",  "KES": "KSh","ZAR": "R",  "CAD": "CA$",
    "AUD": "AU$","INR": "₹",
}

_CURRENCY_DECIMALS = {
    "NGN": 0,  # Naira typically displayed without kobo
}


def format_price(
    amount: Decimal,
    currency: Optional[str] = None,
    position: Optional[str] = None,
    include_tax: bool = False,
    tax_rate: Optional[Decimal] = None,
) -> str:
    """
    Format a Decimal amount as a human-readable price string.

    Args:
        amount:       Raw price (Decimal).
        currency:     3-letter currency code; falls back to store settings.
        position:     'before' | 'after' | 'before_space' | 'after_space'.
        include_tax:  If True and tax_rate provided, adds tax before formatting.
        tax_rate:     Percentage (e.g., Decimal("7.5") for 7.5%).

    Returns:
        Formatted string, e.g.  "₦12,500"  or  "$19.99"
    """
    store = get_store_settings()
    currency = currency or (store.currency if store else "USD")
    position = position or (store.currency_position if store else "before")

    # Tax
    if include_tax and tax_rate:
        amount = amount * (1 + tax_rate / Decimal("100"))

    # Rounding
    decimals = _CURRENCY_DECIMALS.get(currency, 2)
    quantize_str = Decimal("1") if decimals == 0 else Decimal(f"0.{'0' * decimals}")
    amount = amount.quantize(quantize_str, rounding=ROUND_HALF_UP)

    # Thousands separator
    if decimals == 0:
        formatted_number = f"{int(amount):,}"
    else:
        formatted_number = f"{amount:,.{decimals}f}"

    symbol = _CURRENCY_SYMBOLS.get(currency, currency)

    mapping = {
        "before":       f"{symbol}{formatted_number}",
        "after":        f"{formatted_number}{symbol}",
        "before_space": f"{symbol} {formatted_number}",
        "after_space":  f"{formatted_number} {symbol}",
    }
    return mapping.get(position, f"{symbol}{formatted_number}")


def calculate_tax(amount: Decimal, tax_rate: Optional[Decimal] = None) -> Decimal:
    """
    Calculate the tax portion for a given amount.

    Args:
        amount:   Pre-tax price.
        tax_rate: Override; if None uses store default_tax_rate.

    Returns:
        Tax amount as Decimal, rounded to 2dp.
    """
    if tax_rate is None:
        store = get_store_settings()
        tax_rate = store.default_tax_rate if store else Decimal("0")

    return (amount * tax_rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_discount(original: Decimal, sale: Decimal) -> Decimal:
    """Return the percentage discount (0–100) between original and sale price."""
    if original <= 0:
        return Decimal("0")
    discount = ((original - sale) / original * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(Decimal("0"), min(Decimal("100"), discount))


def format_price_range(min_price: Decimal, max_price: Decimal, **fmt_kwargs) -> str:
    """
    Format a price range for product variants.

    Returns "₦5,000 – ₦12,000" or "₦5,000" if both prices are the same.
    """
    if min_price == max_price:
        return format_price(min_price, **fmt_kwargs)
    return f"{format_price(min_price, **fmt_kwargs)} – {format_price(max_price, **fmt_kwargs)}"


# ============================================================================
# 6. HOMEPAGE SECTION DATA
# ============================================================================

_DEFAULT_SECTION_ORDER = [
    "hero", "announcement", "featured_categories", "featured_products",
    "promo_banners", "new_arrivals", "best_sellers", "sale_section",
    "testimonials", "instagram", "blog_posts", "newsletter",
]


def get_homepage_sections() -> List[Dict]:
    """
    Return an ordered list of active homepage sections with their settings.

    Each entry: {"key": "hero", "enabled": True, "order": 1, "config": {...}}

    The order follows HomepageLayout.section_order (if it exists as a JSONField)
    or falls back to the static default order above.
    """
    layout = get_homepage_layout()
    if not layout:
        return []

    _SECTION_MAP = {
        "hero": {
            "enabled": layout.show_hero,
            "config": {
                "type":          layout.hero_type,
                "height":        layout.hero_height,
                "autoplay":      layout.hero_autoplay,
                "autoplay_speed":layout.hero_autoplay_speed,
            },
        },
        "featured_categories": {
            "enabled": layout.show_featured_categories,
            "config": {
                "title":   layout.featured_categories_title,
                "layout":  layout.featured_categories_layout,
                "count":   layout.featured_categories_count,
            },
        },
        "featured_products": {
            "enabled": layout.show_featured_products,
            "config": {
                "title": layout.featured_products_title,
                "count": layout.featured_products_count,
            },
        },
        "new_arrivals": {
            "enabled": layout.show_new_arrivals,
            "config": {
                "title": layout.new_arrivals_title,
                "count": layout.new_arrivals_count,
                "days":  layout.new_arrivals_days,
            },
        },
        "best_sellers": {
            "enabled": layout.show_best_sellers,
            "config": {
                "title": layout.best_sellers_title,
                "count": layout.best_sellers_count,
            },
        },
        "sale_section": {
            "enabled": layout.show_sale_section,
            "config": {
                "title": layout.sale_section_title,
                "count": layout.sale_section_count,
            },
        },
        "promo_banners": {
            "enabled": layout.show_promo_banners,
            "config": {"layout": layout.promo_banner_layout},
        },
        "testimonials": {
            "enabled": layout.show_testimonials,
            "config": {
                "title": layout.testimonials_title,
                "count": layout.testimonials_count,
            },
        },
        "blog_posts": {
            "enabled": layout.show_blog_posts,
            "config": {
                "title": getattr(layout, "blog_posts_title", "From the Blog"),
            },
        },
    }

    # Determine order (use stored JSON order if available)
    custom_order = getattr(layout, "section_order", None)
    section_order = custom_order if isinstance(custom_order, list) else _DEFAULT_SECTION_ORDER

    result = []
    for idx, key in enumerate(section_order):
        entry = _SECTION_MAP.get(key)
        if entry and entry["enabled"]:
            result.append({"key": key, "enabled": True, "order": idx + 1, **entry["config"]})

    return result


# ============================================================================
# 7. HEADER / FOOTER CONTEXT
# ============================================================================

def get_header_context() -> Dict:
    """
    Assemble a complete template context dict for the site header.
    Suitable for use in a context processor or header-specific view.
    """
    header = get_header_settings()
    store  = get_store_settings()
    if not header:
        return {}

    return {
        "header_layout":              header.layout,
        "header_is_sticky":           header.is_sticky,
        "header_is_transparent":      header.is_transparent,
        "header_bg_color":            header.background_color,
        "header_text_color":          header.text_color,
        "header_height":              header.height,
        "logo_max_width":             header.logo_max_width,
        "logo_position":              header.logo_position,
        "show_announcement_bar":      header.show_announcement_bar,
        "announcement_text":          header.announcement_text,
        "announcement_bg":            header.announcement_background_color,
        "announcement_color":         header.announcement_text_color,
        "announcement_link":          header.announcement_link,
        "nav_style":                  header.nav_style,
        "show_categories_in_nav":     header.show_categories_in_nav,
        "max_nav_items":              header.max_nav_items,
        "show_search":                header.show_search,
        "search_style":               header.search_style,
        "search_placeholder":         header.search_placeholder,
        "show_cart_icon":             header.show_cart_icon,
        "cart_icon_style":            header.cart_icon_style,
        "show_cart_count":            header.show_cart_count,
        "cart_preview_on_hover":      header.cart_preview_on_hover,
        "show_account_icon":          header.show_account_icon,
        "show_wishlist_icon":         header.show_wishlist_icon,
        "mobile_menu_style":          header.mobile_menu_style,
        "store_name":                 store.store_name if store else "",
        "header_nav_menu":            build_menu_tree("header"),
    }


def get_footer_context() -> Dict:
    """
    Assemble a complete template context dict for the site footer.
    """
    footer  = get_footer_settings()
    social  = get_social_links()
    store   = get_store_settings()
    if not footer:
        return {}

    social_links = {}
    if social:
        for platform in ("facebook", "instagram", "twitter", "tiktok",
                         "youtube", "linkedin", "pinterest", "snapchat"):
            url = getattr(social, platform, None)
            if url:
                social_links[platform] = url

    return {
        "footer_layout":          footer.layout if hasattr(footer, "layout") else "four_column",
        "footer_bg_color":        getattr(footer, "background_color", "#111827"),
        "footer_text_color":      getattr(footer, "text_color", "#FFFFFF"),
        "footer_show_logo":       footer.show_logo,
        "footer_about_text":      footer.about_text,
        "footer_copyright":       footer.copyright_text,
        "show_newsletter":        footer.show_newsletter,
        "newsletter_title":       footer.newsletter_title,
        "newsletter_description": footer.newsletter_description,
        "show_payment_icons":     footer.show_payment_icons,
        "accepted_payments":      footer.accepted_payments,
        "show_social_links":      footer.show_social_links,
        "social_links_style":     footer.social_links_style,
        "show_trust_badges":      footer.show_trust_badges,
        "show_legal_links":       footer.show_legal_links,
        "social_links":           social_links,
        "footer_nav_menu":        build_menu_tree("footer"),
        "store":                  store,
    }


# ============================================================================
# 8. SEARCH UTILITIES
# ============================================================================

def build_search_config() -> Dict:
    """
    Return a dict describing the current search configuration.
    Used by search views and the JS search widget.
    """
    s = get_search_settings()
    if not s:
        return {"enabled": True, "instant": False, "min_chars": 2}

    return {
        "enabled":             True,
        "instant_search":      getattr(s, "enable_instant_search", True),
        "min_chars":           getattr(s, "min_search_chars", 2),
        "show_suggestions":    getattr(s, "show_suggestions", True),
        "max_suggestions":     getattr(s, "max_suggestions", 8),
        "show_recent":         getattr(s, "show_recent_searches", True),
        "show_popular":        getattr(s, "show_popular_searches", True),
        "search_in_desc":      getattr(s, "search_in_description", False),
        "search_in_sku":       getattr(s, "search_in_sku", True),
        "search_in_tags":      getattr(s, "search_in_tags", True),
        "include_out_of_stock":getattr(s, "include_out_of_stock", False),
        "default_sort":        getattr(s, "default_sort_order", "relevance"),
    }


def tokenize_query(q: str) -> List[str]:
    """
    Split a search query into tokens, stripping stop words.
    Returns a list of lowercase meaningful tokens.
    """
    _STOP_WORDS = {
        "the", "a", "an", "and", "or", "for", "to", "in", "on",
        "at", "with", "of", "is", "are", "was", "were",
    }
    tokens = [t.strip().lower() for t in q.split() if t.strip()]
    return [t for t in tokens if t not in _STOP_WORDS and len(t) >= 2]


def build_search_queryset(Product, q: str, cfg: Optional[Dict] = None):
    """
    Apply search filters to a Product queryset based on search settings.

    Args:
        Product:  The Product model class.
        q:        Raw search query string.
        cfg:      Output of build_search_config() (fetched if None).

    Returns:
        Filtered queryset.
    """
    from django.db.models import Q

    if cfg is None:
        cfg = build_search_config()

    tokens = tokenize_query(q)
    if not tokens:
        return Product.objects.none()

    base_filter = Q()
    for token in tokens:
        token_filter = Q(name__icontains=token)
        if cfg.get("search_in_desc"):
            token_filter |= Q(description__icontains=token)
        if cfg.get("search_in_sku"):
            token_filter |= Q(sku__icontains=token)
        if cfg.get("search_in_tags"):
            token_filter |= Q(tags__name__icontains=token)
        base_filter &= token_filter

    qs = Product.objects.filter(base_filter, is_active=True).distinct()

    if not cfg.get("include_out_of_stock"):
        # Assumes a `stock_quantity` or `is_in_stock` field
        qs = qs.filter(stock_quantity__gt=0)

    return qs


# ============================================================================
# 9. PRODUCT DISPLAY HELPERS
# ============================================================================

def get_product_badge(product, settings=None) -> Optional[str]:
    """
    Determine which badge (if any) should be shown on a product card.
    Priority: SALE > NEW > OUT-OF-STOCK.

    Args:
        product:  Product ORM instance.
        settings: ProductDisplaySettings instance (fetched if None).

    Returns:
        Badge string: "sale" | "new" | "out_of_stock" | None
    """
    if settings is None:
        settings = get_product_display_settings()
    if not settings:
        return None

    # Sale badge
    if settings.show_sale_badge:
        compare_price = getattr(product, "compare_at_price", None)
        price = getattr(product, "price", None)
        if compare_price and price and compare_price > price:
            return "sale"

    # New badge
    if settings.show_new_badge:
        created = getattr(product, "created_at", None)
        if created:
            age_days = (timezone.now() - created).days
            if age_days <= settings.new_badge_days:
                return "new"

    # Out of stock
    if settings.show_stock_status:
        stock = getattr(product, "stock_quantity", 1)
        if stock is not None and stock <= 0:
            return "out_of_stock"

    return None


def get_image_ratio_css(settings=None) -> str:
    """
    Return a CSS padding-bottom value that enforces the configured image ratio.
    Used for padding-trick responsive images.

    Returns:
        CSS padding-bottom string, e.g. "100%"
    """
    if settings is None:
        settings = get_product_display_settings()

    ratio_map = {
        "square":    "100%",
        "portrait":  "133.33%",
        "landscape": "75%",
        "auto":      "auto",
    }
    ratio = getattr(settings, "image_ratio", "square") if settings else "square"
    return ratio_map.get(ratio, "100%")


def get_hover_effect_class(settings=None) -> str:
    """Return a CSS class name corresponding to the configured hover effect."""
    if settings is None:
        settings = get_product_display_settings()

    class_map = {
        "none":  "",
        "zoom":  "hover-zoom",
        "fade":  "hover-fade",
        "slide": "hover-slide",
    }
    effect = getattr(settings, "image_hover_effect", "fade") if settings else "fade"
    return class_map.get(effect, "")


def get_products_per_row_classes(settings=None) -> str:
    """
    Return Bootstrap-style column classes for the product grid.

    Returns e.g. "col-6 col-md-4 col-lg-3"
    """
    if settings is None:
        settings = get_product_display_settings()
    if not settings:
        return "col-6 col-md-4 col-lg-3"

    mobile_cols  = 12 // max(1, settings.products_per_row_mobile)
    tablet_cols  = 12 // max(1, settings.products_per_row_tablet)
    desktop_cols = 12 // max(1, settings.products_per_row_desktop)

    return f"col-{mobile_cols} col-md-{tablet_cols} col-lg-{desktop_cols}"


# ============================================================================
# 10. CART UTILITIES (Session-based)
# ============================================================================

_CART_SESSION_KEY = "_store_cart"
_CART_ITEM_SCHEMA = {"product_id": str, "variant_id": str, "qty": int, "unit_price": str}


def _get_or_create_cart(request: HttpRequest) -> Dict:
    """Return the cart dict from the session, creating it if absent."""
    if _CART_SESSION_KEY not in request.session:
        request.session[_CART_SESSION_KEY] = {"items": {}, "coupon": None}
    return request.session[_CART_SESSION_KEY]


def cart_add(request: HttpRequest, product_id: str, unit_price: Decimal,
             qty: int = 1, variant_id: Optional[str] = None) -> Dict:
    """
    Add a product (or variant) to the session cart.
    If the item already exists its quantity is incremented.

    Args:
        request:    Current HTTP request.
        product_id: String or UUID of the product.
        unit_price: Price at time of adding (Decimal).
        qty:        Quantity to add (default 1).
        variant_id: Optional variant identifier.

    Returns:
        The updated cart dict.
    """
    cart = _get_or_create_cart(request)
    key = f"{product_id}:{variant_id or 'default'}"

    if key in cart["items"]:
        cart["items"][key]["qty"] += qty
    else:
        cart["items"][key] = {
            "product_id": str(product_id),
            "variant_id": str(variant_id) if variant_id else None,
            "qty":        qty,
            "unit_price": str(unit_price),
        }

    request.session.modified = True

    # Respect per-item quantity limits from CartSettings
    cs = get_cart_settings()
    max_qty = getattr(cs, "max_quantity_per_item", 99) if cs else 99
    cart["items"][key]["qty"] = min(cart["items"][key]["qty"], max_qty)

    return cart


def cart_remove(request: HttpRequest, product_id: str,
                variant_id: Optional[str] = None) -> Dict:
    """Remove an item from the cart entirely."""
    cart = _get_or_create_cart(request)
    key = f"{product_id}:{variant_id or 'default'}"
    cart["items"].pop(key, None)
    request.session.modified = True
    return cart


def cart_update_qty(request: HttpRequest, product_id: str, qty: int,
                    variant_id: Optional[str] = None) -> Dict:
    """Update the quantity of a cart item. Removes if qty ≤ 0."""
    if qty <= 0:
        return cart_remove(request, product_id, variant_id)
    cart = _get_or_create_cart(request)
    key = f"{product_id}:{variant_id or 'default'}"
    if key in cart["items"]:
        cart["items"][key]["qty"] = qty
        request.session.modified = True
    return cart


def cart_clear(request: HttpRequest) -> None:
    """Empty the entire cart."""
    request.session[_CART_SESSION_KEY] = {"items": {}, "coupon": None}
    request.session.modified = True


def cart_count(request: HttpRequest) -> int:
    """Return total item quantity in the cart (sum of all qtys)."""
    cart = _get_or_create_cart(request)
    return sum(item["qty"] for item in cart["items"].values())


def cart_totals(request: HttpRequest) -> Dict:
    """
    Calculate and return cart financial summary.

    Returns:
        {
            "subtotal":    Decimal,
            "discount":    Decimal,
            "tax":         Decimal,
            "shipping":    Decimal,
            "total":       Decimal,
            "item_count":  int,
            "free_shipping_remaining": Decimal or None,
        }
    """
    cart  = _get_or_create_cart(request)
    store = get_store_settings()

    subtotal = Decimal("0")
    item_count = 0

    for item in cart["items"].values():
        price = Decimal(item["unit_price"])
        qty   = item["qty"]
        subtotal   += price * qty
        item_count += qty

    discount = Decimal("0")
    coupon_code = cart.get("coupon")
    if coupon_code:
        discount = _apply_coupon_discount(coupon_code, subtotal)

    after_discount = subtotal - discount
    tax_rate = store.default_tax_rate if store else Decimal("0")
    tax = calculate_tax(after_discount, tax_rate) if store and store.tax_enabled else Decimal("0")

    # Shipping
    shipping = Decimal("0")
    free_remaining = None
    if store:
        if store.free_shipping_enabled and after_discount >= store.free_shipping_threshold:
            shipping = Decimal("0")
        elif store.free_shipping_enabled and store.free_shipping_threshold > 0:
            free_remaining = store.free_shipping_threshold - after_discount

    total = after_discount + tax + shipping

    return {
        "subtotal":               subtotal,
        "discount":               discount,
        "tax":                    tax,
        "shipping":               shipping,
        "total":                  total,
        "item_count":             item_count,
        "free_shipping_remaining": free_remaining,
    }


def _apply_coupon_discount(code: str, subtotal: Decimal) -> Decimal:
    """
    Look up a coupon by code and return the discount amount.
    Integrate with your Coupon / DiscountCode model here.

    Returns Decimal("0") if code is invalid or not applicable.
    """
    try:
        # Example integration — replace with your actual Coupon model
        # from shop.models import Coupon
        # coupon = Coupon.objects.get(code=code.upper(), is_active=True)
        # return coupon.calculate_discount(subtotal)
        return Decimal("0")
    except Exception:
        return Decimal("0")


def cart_apply_coupon(request: HttpRequest, code: str) -> Tuple[bool, str]:
    """
    Validate and apply a coupon code to the cart.

    Returns:
        (True, "Applied successfully") or (False, "reason for failure")
    """
    try:
        from dashboard.feature_marketplace.services import FeatureEntitlementEngine

        if not FeatureEntitlementEngine(_schema()).has_feature("discount_codes"):
            return False, "Discount codes are not enabled for this store."
    except Exception:
        return False, "Discount codes are not enabled for this store."

    if not code or len(code) > 50:
        return False, "Invalid coupon code."

    cart = _get_or_create_cart(request)
    cart["coupon"] = code.upper().strip()
    request.session.modified = True
    return True, "Coupon applied."


# ============================================================================
# 11. WISHLIST UTILITIES
# ============================================================================

_WISHLIST_SESSION_KEY = "_store_wishlist"


def wishlist_get(request: HttpRequest) -> List[str]:
    """Return the list of product IDs in the session wishlist."""
    return request.session.get(_WISHLIST_SESSION_KEY, [])


def wishlist_add(request: HttpRequest, product_id: str) -> List[str]:
    """Add a product to the session wishlist (no-op if already present)."""
    wishlist = wishlist_get(request)
    pid = str(product_id)
    if pid not in wishlist:
        wishlist.append(pid)
        request.session[_WISHLIST_SESSION_KEY] = wishlist
        request.session.modified = True
    return wishlist


def wishlist_remove(request: HttpRequest, product_id: str) -> List[str]:
    """Remove a product from the session wishlist."""
    wishlist = [p for p in wishlist_get(request) if p != str(product_id)]
    request.session[_WISHLIST_SESSION_KEY] = wishlist
    request.session.modified = True
    return wishlist


def wishlist_toggle(request: HttpRequest, product_id: str) -> Tuple[List[str], bool]:
    """
    Toggle a product in/out of the wishlist.

    Returns:
        (updated_wishlist, is_now_in_wishlist)
    """
    pid = str(product_id)
    wishlist = wishlist_get(request)
    if pid in wishlist:
        return wishlist_remove(request, pid), False
    return wishlist_add(request, pid), True


def wishlist_count(request: HttpRequest) -> int:
    """Return the number of items in the wishlist."""
    return len(wishlist_get(request))


def wishlist_contains(request: HttpRequest, product_id: str) -> bool:
    """Check if a product is in the wishlist."""
    return str(product_id) in wishlist_get(request)


# ============================================================================
# 12. POPUP / NOTIFICATION UTILITIES
# ============================================================================

_POPUP_DISMISSED_KEY = "_popup_dismissed"


def should_show_popup(request: HttpRequest) -> bool:
    """
    Determine whether the popup should be displayed for this request.

    Checks:
    - Popup is enabled in settings
    - User has not dismissed it recently (session flag)
    - Not on checkout/cart pages (configurable)
    """
    popup = get_popup_settings()
    if not popup:
        return False

    # Check master toggle
    if not getattr(popup, "is_enabled", False):
        return False

    store = get_store_settings()
    if store and not store.enable_popup:
        return False

    # Check session dismissal
    dismissed_at = request.session.get(_POPUP_DISMISSED_KEY)
    if dismissed_at:
        from datetime import datetime
        try:
            ts = datetime.fromisoformat(dismissed_at)
            reshow_hours = getattr(popup, "reshow_after_hours", 24)
            elapsed = (timezone.now() - timezone.make_aware(ts)).total_seconds() / 3600
            if elapsed < reshow_hours:
                return False
        except (ValueError, TypeError):
            pass

    # Don't show on checkout / cart
    path = request.path
    skip_paths = ["/cart", "/checkout", "/account", "/order"]
    if any(path.startswith(p) for p in skip_paths):
        return False

    return True


def dismiss_popup(request: HttpRequest) -> None:
    """Mark the popup as dismissed in the session."""
    request.session[_POPUP_DISMISSED_KEY] = timezone.now().isoformat()
    request.session.modified = True


# ============================================================================
# 13. SEO UTILITIES
# ============================================================================

def get_store_meta_tags(override_title: str = "", override_description: str = "") -> Dict:
    """
    Return a dict of SEO meta tags for use in the base template.

    Args:
        override_title:       Per-page title override.
        override_description: Per-page description override.

    Returns:
        Dict with keys: title, description, keywords, allow_indexing,
                        og_title, og_description, twitter_card
    """
    store = get_store_settings()
    if not store:
        return {}

    title = override_title or getattr(store, "meta_title", store.store_name)
    description = override_description or getattr(store, "meta_description", "")

    return {
        "title":           title,
        "description":     description,
        "keywords":        getattr(store, "meta_keywords", ""),
        "allow_indexing":  store.allow_indexing,
        "og_title":        title,
        "og_description":  description,
        "og_site_name":    store.store_name,
        "twitter_card":    "summary_large_image",
    }


def get_organization_jsonld() -> str:
    """
    Return a JSON-LD <script> block for the store's Organization schema.
    Inject into base template <head> for rich search results.
    """
    store   = get_store_settings()
    social  = get_social_links()
    if not store:
        return ""

    social_urls = []
    if social:
        for platform in ("facebook", "instagram", "twitter", "linkedin", "youtube"):
            url = getattr(social, platform, None)
            if url:
                social_urls.append(url)

    data = {
        "@context":   "https://schema.org",
        "@type":      "Organization",
        "name":       store.store_name,
        "email":      store.contact_email,
        "telephone":  store.phone,
        "address": {
            "@type":           "PostalAddress",
            "streetAddress":   store.address_line1,
            "addressLocality": store.city,
            "addressRegion":   store.state,
            "postalCode":      store.postal_code,
            "addressCountry":  store.country,
        },
        "sameAs": social_urls,
    }

    return mark_safe(
        f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>'
    )


def get_product_jsonld(product) -> str:
    """
    Return a JSON-LD Product schema block for a product detail page.

    Args:
        product: Product ORM instance (must have name, price, description, sku).

    Returns:
        Safe HTML string with embedded JSON-LD.
    """
    store = get_store_settings()
    currency = store.currency if store else "USD"

    data = {
        "@context":   "https://schema.org",
        "@type":      "Product",
        "name":       getattr(product, "name", ""),
        "description":getattr(product, "description", ""),
        "sku":        getattr(product, "sku", ""),
        "offers": {
            "@type":         "Offer",
            "priceCurrency": currency,
            "price":         str(getattr(product, "price", "0")),
            "availability":  (
                "https://schema.org/InStock"
                if getattr(product, "stock_quantity", 1) > 0
                else "https://schema.org/OutOfStock"
            ),
        },
    }

    return mark_safe(
        f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>'
    )


# ============================================================================
# 14. EMAIL RENDERING UTILITIES
# ============================================================================

def get_email_branding_context() -> Dict:
    """
    Return a complete context dict for transactional email templates.
    Pass to any email template that extends the base email layout.
    """
    et    = get_email_template_settings()
    store = get_store_settings()
    social = get_social_links()
    if not et:
        return {}

    social_links = {}
    if social and et.show_social_links_in_footer:
        for platform in ("facebook", "instagram", "twitter", "linkedin", "youtube"):
            url = getattr(social, platform, None)
            if url:
                social_links[platform] = url

    return {
        "email_logo":              et.logo.url if et.logo else None,
        "email_accent_color":      et.accent_color,
        "email_bg_color":          et.background_color,
        "email_content_bg_color":  et.content_background_color,
        "email_text_color":        et.text_color,
        "email_header_text":       et.header_text,
        "email_footer_text":       et.footer_text,
        "show_contact_info":       et.show_contact_info,
        "show_social_links":       et.show_social_links_in_footer,
        "show_unsubscribe":        et.show_unsubscribe_link,
        "email_social_links":      social_links,
        "store_name":              store.store_name if store else "",
        "store_email":             store.contact_email if store else "",
        "store_phone":             store.phone if store else "",
        "store_address":           store.full_address if store else "",
        "current_year":            timezone.now().year,
    }


# ============================================================================
# 15. MOBILE / PWA UTILITIES
# ============================================================================

def generate_pwa_manifest() -> Dict:
    """
    Generate a Web App Manifest dict from MobileAppSettings.
    Serve at /manifest.json via a dedicated view.
    """
    mobile = get_mobile_app_settings()
    theme  = get_theme_settings()
    if not mobile:
        return {}

    return {
        "name":             getattr(mobile, "app_name", "Store"),
        "short_name":       getattr(mobile, "app_short_name", "Store")[:12],
        "description":      getattr(mobile, "app_description", ""),
        "start_url":        "/",
        "display":          "standalone",
        "background_color": theme.background_color if theme else "#FFFFFF",
        "theme_color":      theme.primary_color if theme else "#2563EB",
        "icons": [
            {
                "src":   getattr(mobile, f"icon_{size}", ""),
                "sizes": f"{size}x{size}",
                "type":  "image/png",
            }
            for size in (192, 512)
            if getattr(mobile, f"icon_{size}", None)
        ],
        "categories": ["shopping"],
    }


# ============================================================================
# 16. MAINTENANCE MODE GATE
# ============================================================================

def is_maintenance_mode() -> bool:
    """
    Return True if the store is currently in maintenance mode.
    Checks the cached StoreSettings.maintenance_mode flag.
    """
    store = get_store_settings()
    return bool(store and store.maintenance_mode)


def maintenance_mode_middleware(get_response):
    """
    Django middleware factory that returns a 503 page when maintenance mode is on.

    Usage in settings.py:
        MIDDLEWARE = [
            ...
            "dashboard.store_settings.storefront_utils.maintenance_mode_middleware",
            ...
        ]
    """
    from django.http import HttpResponse

    # Allow list — always reachable even in maintenance mode
    _ALLOW_PATHS = ["/admin/", "/healthcheck/", "/favicon.ico"]

    def middleware(request):
        if any(request.path.startswith(p) for p in _ALLOW_PATHS):
            return get_response(request)

        if is_maintenance_mode():
            store = get_store_settings()
            message = getattr(store, "maintenance_message", "We'll be back shortly.") if store else "Maintenance in progress."
            return HttpResponse(
                f"<h1>Under Maintenance</h1><p>{message}</p>",
                status=503,
                content_type="text/html",
            )
        return get_response(request)

    return middleware


# ============================================================================
# 17. CONTEXT PROCESSORS
# ============================================================================

def store_context(request: HttpRequest) -> Dict:
    """
    Django context processor — injects store-wide variables into every template.

    Add to settings.py:
        TEMPLATES[0]["OPTIONS"]["context_processors"] = [
            ...
            "dashboard.store_settings.storefront_utils.store_context",
        ]
    """
    key = cache_key("store_context", "global")
    ctx = cache.get(key)
    if ctx is not None:
        return ctx

    store   = get_store_settings()
    theme   = get_theme_settings()
    header  = get_header_settings()

    cart_count_val = cart_count(request)
    wishlist_count_val = wishlist_count(request)
    try:
        from dashboard.feature_marketplace.services import FeatureEntitlementEngine

        entitlement_engine = FeatureEntitlementEngine(_schema())
        wishlist_enabled = entitlement_engine.has_feature("wishlist")
        compare_enabled = entitlement_engine.has_feature("compare")
        reviews_enabled = entitlement_engine.has_feature("reviews")
        live_chat_enabled = entitlement_engine.has_feature("live_chat")
    except Exception:
        wishlist_enabled = False
        compare_enabled = False
        reviews_enabled = False
        live_chat_enabled = False

    ctx = {
        # Core store
        "store":              store,
        "store_name":         store.store_name if store else "",
        "store_currency":     store.currency if store else "USD",
        "maintenance_mode":   store.maintenance_mode if store else False,

        # Theme
        "theme":              theme,
        "theme_css":          get_theme_css_variables(),
        "theme_meta":         get_theme_meta(),
        "google_fonts_url":   get_google_fonts_url(),

        # Header
        "header":             header,
        "show_announcement_bar": header.show_announcement_bar if header else False,
        "announcement_text":  header.announcement_text if header else "",

        # Cart & Wishlist (per-request, not cached globally)
        "cart_count":         cart_count_val,
        "wishlist_count":     wishlist_count_val,

        # SEO
        "meta_tags":          get_store_meta_tags(),
        "organization_jsonld":get_organization_jsonld(),

        # Feature flags
        "enable_wishlist":    wishlist_enabled,
        "enable_compare":     compare_enabled,
        "enable_reviews":     reviews_enabled,
        "enable_live_chat":   live_chat_enabled,
        "enable_social_sharing": store.enable_social_sharing if store else True,

        # Analytics IDs
        "ga_id":              getattr(store, "google_analytics_id", "") if store else "",
        "gtm_id":             getattr(store, "google_tag_manager_id", "") if store else "",
        "fb_pixel_id":        getattr(store, "facebook_pixel_id", "") if store else "",

        # Popup
        "show_popup":         should_show_popup(request),
    }

    # Cache the non-request-specific portion (avoid caching cart/wishlist counts)
    cacheable_ctx = {k: v for k, v in ctx.items()
                     if k not in ("cart_count", "wishlist_count", "show_popup")}
    cache.set(key, cacheable_ctx, CACHE_TTL_MEDIUM)

    return ctx
