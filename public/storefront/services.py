from __future__ import annotations

from collections import defaultdict
import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import connection, transaction
from django.db.models import Case, Count, F, IntegerField, Max, Min, Prefetch, Q, Value, When
from django.db.models.functions import Coalesce
from django.db.utils import OperationalError, ProgrammingError
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from dashboard.store_settings.models import (
    CheckoutSettings,
    FooterSettings,
    HeaderSettings,
    HomepageLayout,
    NavigationMenu,
    ProductDisplaySettings,
    SearchSettings,
    SocialMediaLinks,
    StoreSettings,
    ThemeSettings,
)
from dashboard.theme_manager.utils import render_theme_template
from pricing.utils.discount import (
    calculate_line_level_discounts,
    DiscountValidationError,
    evaluate_cart_discounts,
    record_discount_usage,
    reverse_discount_usage_for_order,
    validate_discount_code,
)
from dashboard.pricing.utiles.advanced import (
    mark_discount_experiment_redeemed,
)
from pricing.utils.price_resolver import PricingContext, resolve_price
from public.cart.models import (
    Cart,
    CartItem,
    Order,
    OrderAddress,
    OrderDiscount,
    OrderItem,
    OrderTax,
)
from public.category.models import Brand, Category, Tag
from public.product.models import (
    Attribute,
    AttributeValue,
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductVariant,
    ProductVideo,
)
from public.userauth.models import Customer

try:
    from dashboard.pricing.models import (
        AutomaticDiscount,
        BundleOffer,
        BundleOfferItem,
        BundleOrderLedger,
        DiscountCode,
        FlashSale,
        FlashSaleItem,
        IssuedDiscountCode,
        PromotionCommissionLedger,
        PromotionLink,
        VolumePricingTier,
    )
except Exception:  # pragma: no cover - defensive import
    DiscountCode = None
    FlashSale = None
    FlashSaleItem = None
    VolumePricingTier = None
    AutomaticDiscount = None
    BundleOffer = None
    BundleOfferItem = None
    BundleOrderLedger = None
    IssuedDiscountCode = None
    PromotionCommissionLedger = None
    PromotionLink = None


logger = logging.getLogger(__name__)
TWO_PLACES = Decimal("0.01")


def get_tenant_key(request) -> str:
    tenant = getattr(request, "tenant", None)
    return str(
        getattr(tenant, "schema_name", None)
        or getattr(tenant, "id", None)
        or getattr(tenant, "pk", None)
        or getattr(connection, "schema_name", None)
        or "default"
    )


def get_shop_id(request) -> str:
    tenant = getattr(request, "tenant", None)
    return str(
        getattr(tenant, "id", None)
        or getattr(tenant, "pk", None)
        or getattr(tenant, "schema_name", None)
        or getattr(connection, "schema_name", None)
        or "default"
    )


def tenant_cache_key(request, suffix: str) -> str:
    return f"storefront:{get_tenant_key(request)}:{suffix}"


def tenant_session_key(request, suffix: str) -> str:
    return f"storefront:{get_tenant_key(request)}:{suffix}"


def ensure_request_session(request) -> None:
    if not request.session.session_key:
        request.session.create()


def quantize_money(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def get_currency_symbol(currency_code: str | None) -> str:
    symbols = {
        "USD": "$",
        "EUR": "EUR",
        "GBP": "GBP",
        "NGN": "NGN",
        "GHS": "GHS",
        "KES": "KES",
        "ZAR": "ZAR",
        "CAD": "CAD",
        "AUD": "AUD",
        "INR": "INR",
    }
    normalized = (currency_code or "USD").upper()
    return symbols.get(normalized, normalized)


def format_money(value: Decimal | None, currency_code: str | None = "USD") -> str:
    amount = quantize_money(value)
    return f"{get_currency_symbol(currency_code)} {amount:,.2f}"


def safe_reverse(name: str, *args, **kwargs) -> str:
    try:
        return reverse(name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        return "#"


def build_seo_context(
    title: str,
    description: str = "",
    image_url: str | None = None,
    canonical: str | None = None,
) -> dict[str, Any]:
    return {
        "meta_title": title,
        "meta_description": (description or "")[:160],
        "og_title": title,
        "og_description": (description or "")[:160],
        "og_image": image_url or "",
        "canonical_url": canonical or "",
    }


def _singleton_from_cache(request, suffix: str, model_class):
    cache_key = tenant_cache_key(request, suffix)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        queryset = model_class.objects.all()
        if hasattr(model_class, "is_active"):
            queryset = queryset.order_by(
                "-is_active", "-updated_at", "-created_at")
        instance = queryset.first()
        if model_class is ThemeSettings:
            instance = (
                model_class.objects.filter(is_active=True).order_by(
                    "-updated_at", "-created_at").first()
                or instance
            )
        if instance is None and model_class is StoreSettings:
            instance = StoreSettings.objects.get_settings()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Unable to load %s: %s", suffix, exc)
        instance = None

    cache.set(cache_key, instance, 300)
    return instance


def get_store_settings_cached(request):
    return _singleton_from_cache(request, "store_settings", StoreSettings)


def get_theme_settings_cached(request):
    return _singleton_from_cache(request, "theme_settings", ThemeSettings)


def get_header_settings_cached(request):
    return _singleton_from_cache(request, "header_settings", HeaderSettings)


def get_footer_settings_cached(request):
    return _singleton_from_cache(request, "footer_settings", FooterSettings)


def get_checkout_settings_cached(request):
    return _singleton_from_cache(request, "checkout_settings", CheckoutSettings)


def get_product_display_settings_cached(request):
    return _singleton_from_cache(request, "product_display_settings", ProductDisplaySettings)


def get_search_settings_cached(request):
    return _singleton_from_cache(request, "search_settings", SearchSettings)


def get_homepage_layout_cached(request):
    return _singleton_from_cache(request, "homepage_layout", HomepageLayout)


def get_social_links_cached(request):
    return _singleton_from_cache(request, "social_media_links", SocialMediaLinks)


def build_theme_tokens(request) -> dict[str, Any]:
    theme = get_theme_settings_cached(request)
    default_tokens = {
        "primary_color": "#0F172A",
        "secondary_color": "#9D4300",
        "accent_color": "#FD761A",
        "background_color": "#F9F9F9",
        "secondary_background_color": "#F3F3F3",
        "text_color": "#1A1C1C",
        "secondary_text_color": "#45464D",
        "border_color": "#C6C6CD",
        "success_color": "#10B981",
        "warning_color": "#F59E0B",
        "error_color": "#EF4444",
        "heading_font": '"Plus Jakarta Sans", sans-serif',
        "body_font": '"Inter", sans-serif',
        "base_font_size": 16,
        "heading_weight": 800,
        "body_weight": 400,
        "container_width": 1480,
        "spacing_unit": 10,
        "border_radius": 18,
        "button_radius": 12,
        "button_transform": "none",
        "shadow": "0 20px 40px rgba(15, 23, 42, 0.06)",
        "google_fonts_url": "https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Inter:wght@400;500;600;700&display=swap",
        "custom_font_url": "",
    }
    if not theme:
        return default_tokens

    google_font_families = {
        "inter": "Inter:wght@400;500;600;700",
        "roboto": "Roboto:wght@400;500;700",
        "open-sans": "Open+Sans:wght@400;500;600;700",
        "lato": "Lato:wght@400;700",
        "montserrat": "Montserrat:wght@400;500;600;700",
        "poppins": "Poppins:wght@400;500;600;700",
        "playfair": "Playfair+Display:wght@500;600;700",
        "merriweather": "Merriweather:wght@400;700",
    }
    chosen_google_fonts = []
    for font_choice in {theme.heading_font, theme.body_font}:
        font_family = google_font_families.get(font_choice)
        if font_family:
            chosen_google_fonts.append(font_family)
    google_fonts_url = ""
    if chosen_google_fonts:
        google_fonts_url = f"https://fonts.googleapis.com/css2?family={'&family='.join(sorted(chosen_google_fonts))}&display=swap"

    return {
        "primary_color": theme.primary_color,
        "secondary_color": theme.secondary_color,
        "accent_color": theme.accent_color,
        "background_color": theme.background_color,
        "secondary_background_color": theme.secondary_background_color,
        "text_color": theme.text_color,
        "secondary_text_color": theme.secondary_text_color,
        "border_color": theme.border_color,
        "success_color": theme.success_color,
        "warning_color": theme.warning_color,
        "error_color": theme.error_color,
        "heading_font": theme.get_font_family(theme.heading_font),
        "body_font": theme.get_font_family(theme.body_font),
        "base_font_size": theme.base_font_size,
        "heading_weight": theme.heading_font_weight,
        "body_weight": theme.body_font_weight,
        "container_width": theme.container_width,
        "spacing_unit": theme.get_spacing_unit(),
        "border_radius": theme.border_radius,
        "button_radius": theme.button_border_radius,
        "button_transform": theme.button_text_transform,
        "shadow": theme.get_shadow_value(),
        "google_fonts_url": google_fonts_url,
        "custom_font_url": theme.custom_font_url,
    }


def get_social_platforms(request) -> list[dict[str, str]]:
    social_links = get_social_links_cached(request)
    if not social_links:
        return []

    platforms = []
    platform_meta = [
        ("facebook_url", "Facebook", "facebook"),
        ("instagram_url", "Instagram", "instagram"),
        ("twitter_url", "X", "twitter"),
        ("pinterest_url", "Pinterest", "pinterest"),
        ("tiktok_url", "TikTok", "tiktok"),
        ("youtube_url", "YouTube", "youtube"),
        ("linkedin_url", "LinkedIn", "linkedin"),
    ]
    for field_name, label, slug in platform_meta:
        url = getattr(social_links, field_name, "")
        if url:
            platforms.append({"label": label, "slug": slug, "url": url})

    if social_links.whatsapp_number:
        platforms.append(
            {
                "label": "WhatsApp",
                "slug": "whatsapp",
                "url": f"https://wa.me/{social_links.whatsapp_number.replace('+', '').replace(' ', '')}",
            }
        )
    return platforms


def get_shop_context(request) -> dict[str, Any]:
    settings_obj = get_store_settings_cached(request)
    tenant = getattr(request, "tenant", None)
    free_shipping_threshold = getattr(settings_obj, "free_shipping_threshold", Decimal(
        "0.00")) if settings_obj else Decimal("0.00")
    return {
        "id": get_shop_id(request),
        "schema_name": get_tenant_key(request),
        "name": getattr(tenant, "name", None) or getattr(settings_obj, "store_name", None) or "Storefront",
        "tagline": getattr(settings_obj, "store_tagline", "") if settings_obj else "",
        "description": getattr(settings_obj, "store_description", "") if settings_obj else "",
        "email": getattr(settings_obj, "contact_email", "") if settings_obj else "",
        "support_email": getattr(settings_obj, "support_email", "") if settings_obj else "",
        "phone": getattr(settings_obj, "phone", "") if settings_obj else "",
        "whatsapp": getattr(settings_obj, "whatsapp_number", "") if settings_obj else "",
        "logo_url": settings_obj.logo.url if settings_obj and getattr(settings_obj, "logo", None) else "",
        "logo_dark_url": settings_obj.logo_dark.url if settings_obj and getattr(settings_obj, "logo_dark", None) else "",
        "favicon_url": settings_obj.favicon.url if settings_obj and getattr(settings_obj, "favicon", None) else "",
        "currency": getattr(settings_obj, "currency", "USD") if settings_obj else "USD",
        "address": getattr(settings_obj, "full_address", "") if settings_obj else "",
        "free_shipping_enabled": bool(getattr(settings_obj, "free_shipping_enabled", False)),
        "free_shipping_threshold": quantize_money(free_shipping_threshold),
        "free_shipping_threshold_display": format_money(free_shipping_threshold, getattr(settings_obj, "currency", "USD") if settings_obj else "USD"),
    }


def get_feature_flags(request) -> dict[str, bool]:
    settings_obj = get_store_settings_cached(request)
    try:
        from dashboard.feature_marketplace.services import FeatureEntitlementEngine

        engine = FeatureEntitlementEngine(get_tenant_key(request))
        reviews_enabled = engine.has_feature("reviews")
        wishlist_enabled = engine.has_feature("wishlist")
        compare_enabled = engine.has_feature("compare")
        discount_codes_enabled = engine.has_feature("discount_codes")
        gift_cards_enabled = engine.has_feature("gift_cards")
        subscriptions_enabled = engine.has_feature("subscriptions")
        social_login_enabled = engine.has_feature("social_login")
        live_chat_enabled = engine.has_feature("live_chat")
        api_access_enabled = engine.has_feature("api_access")
        webhooks_enabled = engine.has_feature("webhooks")
    except Exception:
        reviews_enabled = False
        wishlist_enabled = False
        compare_enabled = False
        discount_codes_enabled = False
        gift_cards_enabled = False
        subscriptions_enabled = False
        social_login_enabled = False
        live_chat_enabled = False
        api_access_enabled = False
        webhooks_enabled = False

    return {
        "enable_reviews": reviews_enabled,
        "enable_wishlist": wishlist_enabled,
        "enable_compare": compare_enabled,
        "enable_guest_checkout": bool(getattr(settings_obj, "allow_guest_checkout", True)),
        "enable_discount_codes": discount_codes_enabled,
        "enable_gift_cards": gift_cards_enabled,
        "enable_subscriptions": subscriptions_enabled,
        "enable_social_login": social_login_enabled,
        "enable_live_chat": live_chat_enabled,
        "enable_api_access": api_access_enabled,
        "enable_webhooks": webhooks_enabled,
        "enable_b2b": True,
    }


def get_top_categories(request, limit: int = 8):
    cache_key = tenant_cache_key(request, f"top_categories:{limit}")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    categories = list(
        Category.objects.filter(
            is_active=True,
            is_visible=True,
            parent__isnull=True,
        )
        .order_by("-featured", "menu_order", "display_order", "name")[:limit]
    )
    cache.set(cache_key, categories, 300)
    return categories


def _serialize_category_node(category: Category) -> dict[str, Any]:
    return {
        "id": str(category.id),
        "name": category.name,
        "slug": category.slug,
        "url": safe_reverse("category:category_detail", category_slug=category.slug),
        "description": category.description,
        "icon": category.icon,
        "image_url": category.image.url if category.image else "",
        "children": [
            _serialize_category_node(child)
            for child in category.children.filter(
                is_active=True,
                is_visible=True,
                show_in_menu=True,
            ).order_by("menu_order", "display_order", "name")
        ],
    }


def get_navigation_categories(request, limit: int = 8) -> list[dict[str, Any]]:
    cache_key = tenant_cache_key(request, f"navigation_categories:{limit}")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    categories = list(
        Category.objects.filter(
            is_active=True,
            is_visible=True,
            show_in_menu=True,
            parent__isnull=True,
        ).order_by("menu_order", "display_order", "name")[:limit]
    )
    tree = [_serialize_category_node(category) for category in categories]
    cache.set(cache_key, tree, 300)
    return tree


def get_navigation_links(request) -> list[dict[str, str]]:
    return [
        {"slug": "home", "label": "Home", "url": safe_reverse("home:index")},
        {"slug": "shop", "label": "Shop",
            "url": safe_reverse("category:shop_all")},
        {"slug": "new-arrivals", "label": "New Arrivals",
            "url": safe_reverse("category:new_arrivals")},
        {"slug": "best-sellers", "label": "Best Sellers",
            "url": safe_reverse("category:best_sellers")},
        {"slug": "deals", "label": "Deals",
            "url": safe_reverse("category:deals")},
        {"slug": "brands", "label": "Brands",
            "url": safe_reverse("category:brands_directory")},
    ]


def get_utility_navigation(request) -> list[dict[str, str]]:
    return [
        {"label": "Help", "url": safe_reverse("support:help_center")},
        {"label": "Delivery", "url": safe_reverse("support:delivery_info")},
        {"label": "Returns", "url": safe_reverse("support:returns_policy")},
        {"label": "Track Order", "url": safe_reverse("tenant:account_orders")},
    ]


def get_footer_link_groups(request) -> list[dict[str, Any]]:
    return [
        {
            "title": "Shop",
            "links": [
                {"label": "Shop All", "url": safe_reverse(
                    "category:shop_all")},
                {"label": "New Arrivals", "url": safe_reverse(
                    "category:new_arrivals")},
                {"label": "Best Sellers", "url": safe_reverse(
                    "category:best_sellers")},
                {"label": "Deals", "url": safe_reverse("category:deals")},
                {"label": "Gift Guide", "url": safe_reverse(
                    "category:gift_guide")},
            ],
        },
        {
            "title": "Support",
            "links": [
                {"label": "Help Center", "url": safe_reverse(
                    "support:help_center")},
                {"label": "Contact Us", "url": safe_reverse(
                    "support:contact_us")},
                {"label": "Delivery Info", "url": safe_reverse(
                    "support:delivery_info")},
                {"label": "Returns Policy", "url": safe_reverse(
                    "support:returns_policy")},
                {"label": "Warranty", "url": safe_reverse(
                    "support:warranty_info")},
            ],
        },
        {
            "title": "Discover",
            "links": [
                {"label": "Brands", "url": safe_reverse(
                    "category:brands_directory")},
                {"label": "Collections", "url": safe_reverse(
                    "category:collections_list")},
                {"label": "Blog", "url": safe_reverse("content:blog_index")},
                {"label": "Lookbook", "url": safe_reverse("content:lookbook")},
                {"label": "Video Gallery", "url": safe_reverse(
                    "content:video_gallery")},
            ],
        },
        {
            "title": "Legal",
            "links": [
                {"label": "Privacy Policy", "url": safe_reverse(
                    "legal:privacy_policy")},
                {"label": "Terms of Service", "url": safe_reverse(
                    "legal:terms_of_service")},
                {"label": "Cookie Policy", "url": safe_reverse(
                    "legal:cookie_policy")},
                {"label": "Accessibility", "url": safe_reverse(
                    "legal:accessibility")},
                {"label": "Compliance", "url": safe_reverse(
                    "legal:compliance")},
            ],
        },
    ]


def get_account_navigation(request) -> list[dict[str, str]]:
    return [
        {"label": "Overview", "url": safe_reverse("tenant:account_overview")},
        {"label": "Orders", "url": safe_reverse("tenant:account_orders")},
        {"label": "Profile", "url": safe_reverse("tenant:profile_edit")},
        {"label": "Security", "url": safe_reverse("tenant:account_security")},
        {"label": "Addresses", "url": safe_reverse("tenant:address_book")},
        {"label": "Wishlist", "url": safe_reverse("tenant:wishlist")},
        {"label": "Recently Viewed", "url": safe_reverse(
            "tenant:recently_viewed")},
        {"label": "Notifications", "url": safe_reverse(
            "tenant:notification_settings")},
        {"label": "Privacy", "url": safe_reverse("tenant:privacy_settings")},
    ]


def get_mini_footer_links(request) -> list[dict[str, str]]:
    return [
        {"label": "Privacy Policy", "url": safe_reverse(
            "legal:privacy_policy")},
        {"label": "Terms of Service", "url": safe_reverse(
            "legal:terms_of_service")},
        {"label": "Support", "url": safe_reverse("support:help_center")},
        {"label": "Contact", "url": safe_reverse("support:contact_us")},
    ]


def get_banner_slides(request, limit: int = 5):
    return []


def get_active_flash_sale(request=None):
    if FlashSale is None:
        return None
    now = timezone.now()
    try:
        return (
            FlashSale.objects.filter(is_active=True, is_publicly_visible=True)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
            .prefetch_related("items__product", "items__variant__product")
            .order_by("-starts_at")
            .first()
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Unable to resolve flash sale: %s", exc)
        return None


def serialize_flash_sale(flash_sale) -> dict[str, Any] | None:
    if flash_sale is None:
        return None
    return {
        "id": str(flash_sale.id),
        "name": flash_sale.name,
        "slug": flash_sale.slug,
        "description": flash_sale.description,
        "badge_label": flash_sale.badge_label or "Flash Sale",
        "banner_image_url": flash_sale.banner_image.url if getattr(flash_sale, "banner_image", None) else "",
        "show_countdown": bool(flash_sale.show_countdown_timer and getattr(flash_sale, "ends_at", None)),
        "ends_at_iso": flash_sale.ends_at.isoformat() if getattr(flash_sale, "ends_at", None) else "",
        "url": safe_reverse("category:flash_sale"),
    }


def _discount_code_is_active(code, now) -> bool:
    if not getattr(code, "is_active", False):
        return False
    if getattr(code, "starts_at", None) and code.starts_at > now:
        return False
    if getattr(code, "ends_at", None) and code.ends_at < now:
        return False
    if hasattr(code, "is_usage_limit_reached") and code.is_usage_limit_reached():
        return False
    return True


def get_active_discount_campaigns(request, limit: int = 3) -> list[dict[str, Any]]:
    if DiscountCode is None:
        return []

    now = timezone.now()
    campaigns = []
    try:
        queryset = DiscountCode.objects.filter(
            is_active=True).order_by("-starts_at", "code")
        for code in queryset:
            if not _discount_code_is_active(code, now):
                continue
            if not (code.description or "").strip():
                continue
            detail = ""
            if code.value_type == code.ValueType.PERCENTAGE and code.percentage_value:
                detail = f"{quantize_money(code.percentage_value).normalize()}% off"
            elif code.value_type == code.ValueType.FIXED_AMOUNT and code.fixed_amount:
                detail = f"{format_money(code.fixed_amount, code.currency)} off"
            elif code.value_type == code.ValueType.FREE_SHIPPING:
                detail = "Free shipping"
            if code.minimum_order_amount:
                detail = f"{detail} on orders over {format_money(code.minimum_order_amount, code.currency)}" if detail else format_money(
                    code.minimum_order_amount, code.currency)

            campaigns.append(
                {
                    "code": code.code,
                    "title": code.title,
                    "description": code.description,
                    "detail": detail,
                    "url": f"{safe_reverse('promotions:coupon_landing')}?discount={code.code}",
                }
            )
            if len(campaigns) >= limit:
                break
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Unable to load discount campaigns: %s", exc)
    return campaigns


def serialize_brand_card(brand: Brand) -> dict[str, Any]:
    return {
        "id": str(brand.id),
        "name": brand.name,
        "slug": brand.slug,
        "description": brand.description or brand.story,
        "story": brand.story,
        "logo_url": brand.logo.url if brand.logo else "",
        "banner_url": brand.banner.url if brand.banner else "",
        "url": safe_reverse("category:brand_detail", brand_slug=brand.slug),
    }


def get_featured_brands(request, limit: int = 6) -> list[dict[str, Any]]:
    cache_key = tenant_cache_key(request, f"featured_brands:{limit}")
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    brands = [
        serialize_brand_card(brand)
        for brand in Brand.objects.filter(is_active=True).order_by("-featured", "display_order", "name")[:limit]
    ]
    cache.set(cache_key, brands, 300)
    return brands


def get_storefront_announcement(request) -> str:
    settings_obj = get_store_settings_cached(request)
    if not settings_obj:
        return ""
    if getattr(settings_obj, "free_shipping_enabled", False) and getattr(settings_obj, "free_shipping_threshold", None):
        return f"Free delivery nationwide on orders above {format_money(settings_obj.free_shipping_threshold, settings_obj.currency)}"
    return settings_obj.store_tagline or settings_obj.store_name


def get_service_highlights(request) -> list[dict[str, str]]:
    settings_obj = get_store_settings_cached(request)
    if not settings_obj:
        return []
    currency = getattr(settings_obj, "currency", "USD")
    shipping_copy = (
        f"Orders above {format_money(settings_obj.free_shipping_threshold, currency)}"
        if getattr(settings_obj, "free_shipping_enabled", False)
        else f"Dispatch in about {getattr(settings_obj, 'processing_time_days', 2)} business days"
    )
    return [
        {"icon": "local_shipping", "title": "Delivery Promise", "body": shipping_copy},
        {"icon": "verified_user", "title": "Secure Payment",
            "body": "Protected checkout with encrypted payment details."},
        {"icon": "replay", "title": "Flexible Returns",
            "body": "Clear return and refund support through the store support team."},
        {"icon": "headset_mic", "title": "Store Support",
            "body": settings_obj.support_email or settings_obj.contact_email or settings_obj.phone or "Talk to the store team when you need help."},
    ]


def get_store_editorial_cards(request) -> list[dict[str, str]]:
    settings_obj = get_store_settings_cached(request)
    shop = get_shop_context(request)
    if not settings_obj:
        return []
    return [
        {
            "eyebrow": "Store Story",
            "title": shop["tagline"] or f"Why {shop['name']} exists",
            "body": shop["description"] or "A curated storefront experience tailored to the products and audience of this tenant.",
            "url": safe_reverse("content:blog_index"),
            "cta": "Read the story",
        },
        {
            "eyebrow": "Delivery & Support",
            "title": "Buying should feel easy",
            "body": f"Questions, shipping updates, and post-purchase support flow through {settings_obj.support_email or settings_obj.contact_email or settings_obj.phone or 'the store support team'}.",
            "url": safe_reverse("support:help_center"),
            "cta": "Get support",
        },
        {
            "eyebrow": "Store Policies",
            "title": "Clear terms for every order",
            "body": "Shipping, privacy, returns, and service terms are presented directly in the storefront so customers know what to expect.",
            "url": safe_reverse("legal:privacy_policy"),
            "cta": "View policies",
        },
    ]


def build_flash_sale_lookup(flash_sale) -> dict[str, Any]:
    lookup = {
        "flash_sale": flash_sale,
        "product_items": {},
        "variant_items": {},
        "product_ids": set(),
    }
    if flash_sale is None or not hasattr(flash_sale, "items"):
        return lookup

    for item in flash_sale.items.all():
        if not getattr(item, "is_active", True) or item.is_sold_out_at_sale_price:
            continue
        if item.product_id:
            lookup["product_items"][str(item.product_id)] = item
            lookup["product_ids"].add(str(item.product_id))
        if item.variant_id:
            lookup["variant_items"][str(item.variant_id)] = item
            lookup["product_ids"].add(str(item.variant.product_id))
    return lookup


def _get_product_flash_sale_item(product: Product, default_variant: ProductVariant | None, flash_sale_lookup: dict[str, Any] | None):
    if not flash_sale_lookup:
        return None
    if default_variant and str(default_variant.id) in flash_sale_lookup["variant_items"]:
        return flash_sale_lookup["variant_items"][str(default_variant.id)]
    return flash_sale_lookup["product_items"].get(str(product.id))


def _get_display_price_data(
    product: Product,
    default_variant: ProductVariant | None,
    currency_code: str,
    *,
    flash_sale_lookup: dict[str, Any] | None = None,
    customer=None,
) -> dict[str, Any]:
    price = quantize_money(
        getattr(product, "effective_price", None)
        or getattr(default_variant, "price", None)
        or product.price
        or Decimal("0.00")
    )
    compare_price = getattr(product, "effective_compare_price", None) or getattr(
        default_variant, "compare_at_price", None) or product.compare_at_price
    compare_price = quantize_money(compare_price) if compare_price else None

    promo_badge = ""
    promo_source = ""
    countdown_ends_at_iso = ""
    if default_variant:
        resolved = resolve_price(
            default_variant,
            PricingContext(
                customer=customer,
                quantity=1,
                currency_code=currency_code or "USD",
            ),
        )
        price = quantize_money(resolved.final_price)
        compare_price = quantize_money(resolved.compare_at_price) if resolved.compare_at_price else compare_price
        if compare_price and compare_price <= price:
            compare_price = None
        promo_badge = resolved.sale_badge
        promo_source = resolved.applied_layer if resolved.applied_layer != "base" else ""
        savings = quantize_money(resolved.savings)
        savings_percentage = quantize_money(resolved.savings_percentage)
        if resolved.flash_sale_applied:
            flash_sale_item = _get_product_flash_sale_item(product, default_variant, flash_sale_lookup)
            promo_badge = promo_badge or (
                getattr(flash_sale_item.flash_sale, "badge_label", "") if flash_sale_item else "Flash Sale"
            )
            countdown_ends_at_iso = (
                flash_sale_item.flash_sale.ends_at.isoformat()
                if flash_sale_item and getattr(flash_sale_item.flash_sale, "ends_at", None)
                else ""
            )
        is_on_sale = resolved.is_on_sale or bool(compare_price and compare_price > price)
    else:
        is_on_sale = bool(compare_price and compare_price > price) or bool(product.is_on_sale)
        savings = quantize_money(compare_price - price) if compare_price and compare_price > price else Decimal("0.00")
        savings_percentage = ((savings / compare_price) * Decimal("100")).quantize(Decimal("0.1")) if savings > 0 and compare_price else Decimal("0.0")

    if not promo_badge and is_on_sale:
        promo_badge = "Sale"

    return {
        "price": price,
        "compare_price": compare_price if compare_price and compare_price > price else None,
        "price_display": format_money(price, currency_code),
        "compare_price_display": format_money(compare_price, currency_code) if compare_price and compare_price > price else "",
        "is_on_sale": is_on_sale,
        "promo_badge": promo_badge,
        "promo_source": promo_source or ("sale" if is_on_sale else ""),
        "savings": savings,
        "savings_display": format_money(savings, currency_code) if savings > 0 else "",
        "savings_percentage": savings_percentage,
        "countdown_ends_at_iso": countdown_ends_at_iso,
    }


def _get_volume_pricing_table(
    variant: ProductVariant | None,
    *,
    customer=None,
    currency_code: str = "USD",
) -> list[dict[str, Any]]:
    if variant is None or VolumePricingTier is None:
        return []
    customer_group_ids = set()
    if customer and hasattr(customer, "groups"):
        try:
            customer_group_ids = {group.id for group in customer.groups.all()}
        except Exception:
            customer_group_ids = set()
    tiers = variant.volume_tiers.filter(is_active=True).order_by("min_quantity", "max_quantity")
    rows = []
    for tier in tiers:
        if tier.customer_group_id and tier.customer_group_id not in customer_group_ids:
            continue
        tier_price = quantize_money(tier.compute_price(variant.effective_price))
        rows.append(
            {
                "id": str(tier.id),
                "min_quantity": tier.min_quantity,
                "max_quantity": tier.max_quantity,
                "label": f"{tier.min_quantity}+" if tier.max_quantity is None else f"{tier.min_quantity}-{tier.max_quantity}",
                "price": tier_price,
                "price_display": format_money(tier_price, currency_code),
                "savings_label": (
                    f"Save {tier.discount_percentage}%"
                    if tier.price_type == "percentage" and tier.discount_percentage
                    else f"Save {format_money(tier.fixed_discount, currency_code)}"
                    if tier.price_type == "fixed_discount" and tier.fixed_discount
                    else ""
                ),
            }
        )
    return rows


def _serialize_attribute_assignment(product_value: ProductAttributeValue) -> dict[str, str]:
    value = ""
    if product_value.value_option:
        value = product_value.value_option.value
    elif product_value.value_text:
        value = product_value.value_text
    elif product_value.value_number is not None:
        value = str(product_value.value_number)
    elif product_value.value_boolean is not None:
        value = "Yes" if product_value.value_boolean else "No"
    elif product_value.value_date is not None:
        value = product_value.value_date.isoformat()
    elif product_value.value_json:
        value = str(product_value.value_json)
    return {
        "attribute_name": product_value.attribute.name,
        "attribute_slug": product_value.attribute.slug,
        "value": value,
        "is_visible_on_front": bool(product_value.attribute.is_visible_on_front),
    }


def _serialize_variant_option(option: AttributeValue) -> dict[str, str]:
    return {
        "attribute_name": option.attribute.name,
        "attribute_slug": option.attribute.slug,
        "value": option.value,
        "slug": option.slug,
        "color_hex": option.color_hex,
        "swatch_url": option.swatch.url if option.swatch else "",
        "image_url": option.image.url if option.image else "",
    }


def _base_product_queryset():
    now = timezone.now()
    variant_queryset = ProductVariant.objects.filter(is_active=True).order_by("-is_default", "price", "created_at").prefetch_related(
        Prefetch("option_values", queryset=AttributeValue.objects.filter(is_active=True).select_related(
            "attribute").order_by("attribute__display_order", "display_order", "value"))
    )
    return (
        Product.objects.filter(status="published", is_active=True)
        .filter(Q(available_from__isnull=True) | Q(available_from__lte=now))
        .filter(Q(available_until__isnull=True) | Q(available_until__gte=now))
        .exclude(catalog_visibility="hidden")
        .select_related("brand")
        .prefetch_related(
            "categories",
            "tags",
            Prefetch("images", queryset=ProductImage.objects.order_by(
                "-is_primary", "display_order", "created_at")),
            Prefetch("videos", queryset=ProductVideo.objects.order_by(
                "-is_featured", "display_order", "created_at")),
            Prefetch(
                "attribute_values",
                queryset=ProductAttributeValue.objects.select_related(
                    "attribute", "value_option").order_by("display_order", "attribute__display_order"),
            ),
            Prefetch("variants", queryset=variant_queryset),
        )
    )


def get_product_queryset():
    return _base_product_queryset()


def filter_to_listable_products(queryset):
    return queryset.filter(
        Q(variants__available_quantity__gt=0)
        | Q(variants__isnull=True, stock_status__in=["in_stock", "on_backorder"])
    ).distinct()


def get_listable_product_queryset():
    return filter_to_listable_products(_base_product_queryset())


def annotate_product_pricing(queryset):
    return queryset.annotate(
        effective_price=Coalesce("price", Min("variants__price")),
        effective_compare_price=Coalesce(
            "compare_at_price", Min("variants__compare_at_price")),
    )


def serialize_product_card(product, currency_code: str | None = "USD", flash_sale_lookup: dict[str, Any] | None = None) -> dict[str, Any]:
    images = list(product.images.all())
    variants = list(product.variants.all())
    primary_image = next(
        (image for image in images if image.is_primary), images[0] if images else None)
    default_variant = next(
        (variant for variant in variants if variant.is_default), variants[0] if variants else None)
    pricing = _get_display_price_data(
        product, default_variant, currency_code, flash_sale_lookup=flash_sale_lookup)
    in_stock = (
        bool(default_variant and getattr(
            default_variant, "available_quantity", 0) > 0)
        or (not variants and product.stock_status != "out_of_stock")
    )

    return {
        "id": str(product.id),
        "slug": product.slug,
        "name": product.name,
        "brand_name": product.brand.name if product.brand else "",
        "brand_url": safe_reverse("category:brand_detail", brand_slug=product.brand.slug) if product.brand else "",
        "short_description": product.short_description or product.description[:180],
        "price": pricing["price"],
        "compare_price": pricing["compare_price"],
        "price_display": pricing["price_display"],
        "compare_price_display": pricing["compare_price_display"],
        "image_url": primary_image.image.url if primary_image and primary_image.image else "",
        "detail_url": safe_reverse("product:product_detail", product_slug=product.slug),
        "default_variant_id": str(default_variant.id) if default_variant else "",
        "is_on_sale": pricing["is_on_sale"],
        "is_new": bool(product.is_new),
        "is_bestseller": bool(product.is_bestseller),
        "is_featured": bool(product.is_featured),
        "in_stock": in_stock,
        "stock_label": "In stock" if in_stock else "Out of stock",
        "promo_badge": pricing["promo_badge"],
        "promo_source": pricing["promo_source"],
        "savings_display": pricing["savings_display"],
        "savings_percentage": pricing["savings_percentage"],
        "countdown_ends_at_iso": pricing["countdown_ends_at_iso"],
    }


def serialize_product_detail(product, request, flash_sale_lookup: dict[str, Any] | None = None) -> dict[str, Any]:
    settings_obj = get_store_settings_cached(request)
    currency = getattr(settings_obj, "currency",
                       "USD") if settings_obj else "USD"
    customer_profile = get_or_create_customer_profile(request.user) if getattr(request.user, "is_authenticated", False) else None
    images = list(product.images.all())
    videos = list(product.videos.all())
    variants = list(product.variants.all())
    attribute_values = [_serialize_attribute_assignment(
        value) for value in product.attribute_values.all()]
    default_variant = next(
        (variant for variant in variants if variant.is_default), variants[0] if variants else None)
    pricing = _get_display_price_data(
        product, default_variant, currency, flash_sale_lookup=flash_sale_lookup, customer=customer_profile)
    specification_items = [
        {"label": key.replace("_", " ").title(), "value": value}
        for key, value in (product.specifications or {}).items()
        if value not in ("", None, [], {})
    ]
    specification_items.extend(
        {"label": item["attribute_name"], "value": item["value"]}
        for item in attribute_values
        if item["is_visible_on_front"] and item["value"]
    )
    variant_rows = []
    for variant in variants:
        variant_pricing = _get_display_price_data(
            product,
            variant,
            currency,
            flash_sale_lookup=flash_sale_lookup,
            customer=customer_profile,
        )
        variant_rows.append(
            {
                "id": str(variant.id),
                "label": variant.variant_name or " / ".join(option.value for option in variant.option_values.all()) or variant.sku,
                "sku": variant.sku,
                "price": variant_pricing["price"],
                "price_display": variant_pricing["price_display"],
                "compare_price": variant_pricing["compare_price"],
                "compare_price_display": variant_pricing["compare_price_display"],
                "available_quantity": getattr(variant, "available_quantity", 0),
                "is_default": variant.is_default,
                "in_stock": getattr(variant, "available_quantity", 0) > 0,
                "option_values": [_serialize_variant_option(option) for option in variant.option_values.all()],
                "volume_pricing": _get_volume_pricing_table(variant, customer=customer_profile, currency_code=currency),
            }
        )

    return {
        "id": str(product.id),
        "slug": product.slug,
        "name": product.name,
        "brand_name": product.brand.name if product.brand else "",
        "brand_story": product.brand.story if product.brand else "",
        "brand_url": safe_reverse("category:brand_detail", brand_slug=product.brand.slug) if product.brand else "",
        "description": product.description,
        "short_description": product.short_description,
        "specifications": product.specifications or {},
        "specification_items": specification_items,
        "features": product.features or [],
        "product_attributes": attribute_values,
        "price": pricing["price"],
        "compare_price": pricing["compare_price"],
        "price_display": pricing["price_display"],
        "compare_price_display": pricing["compare_price_display"],
        "promo_badge": pricing["promo_badge"],
        "promo_source": pricing["promo_source"],
        "savings_display": pricing["savings_display"],
        "savings_percentage": pricing["savings_percentage"],
        "countdown_ends_at_iso": pricing["countdown_ends_at_iso"],
        "average_rating": quantize_money(getattr(product, "average_rating", Decimal("0.00"))),
        "review_count": int(getattr(product, "review_count", 0) or 0),
        "rating_count": int(getattr(product, "rating_count", 0) or 0),
        "images": [
            {
                "url": image.image.url if image.image else "",
                "caption": image.caption,
                "is_primary": image.is_primary,
            }
            for image in images
        ],
        "videos": [
            {
                "title": video.title or product.name,
                "description": video.description,
                "video_type": video.video_type,
                "video_url": video.video_url or (video.video_file.url if video.video_file else ""),
                "thumbnail_url": video.thumbnail.url if video.thumbnail else "",
                "is_featured": video.is_featured,
            }
            for video in videos
            if video.video_url or video.video_file
        ],
        "variants": variant_rows,
        "volume_pricing": _get_volume_pricing_table(default_variant, customer=customer_profile, currency_code=currency) if default_variant else [],
        "categories": [{"name": category.name, "slug": category.slug, "url": safe_reverse("category:category_detail", category_slug=category.slug)} for category in product.categories.all()],
        "tags": [{"name": tag.name, "slug": tag.slug} for tag in product.tags.all()],
        "stock_label": "In stock" if ((default_variant and default_variant.available_quantity > 0) or (not variants and product.stock_status != "out_of_stock")) else "Out of stock",
        "in_stock": bool((default_variant and default_variant.available_quantity > 0) or (not variants and product.stock_status != "out_of_stock")),
        "default_variant_id": str(default_variant.id) if default_variant else "",
    }


def paginate_queryset(queryset, page_number, per_page=24):
    paginator = Paginator(queryset, per_page)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    return page_obj, paginator


def resolve_sort_order(request, default_sort: str = "newest") -> str:
    requested_sort = request.GET.get("sort")
    if requested_sort:
        return requested_sort
    product_display_settings = get_product_display_settings_cached(request)
    return default_sort or getattr(product_display_settings, "default_sort_order", "newest")


def is_ajax_request(request) -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def build_querystring(request, **replacements) -> str:
    query_params = request.GET.copy()
    for key, value in replacements.items():
        if value in (None, "", []):
            query_params.pop(key, None)
            continue
        if isinstance(value, (list, tuple)):
            query_params.setlist(key, [str(item)
                                 for item in value if item not in ("", None)])
            continue
        query_params[key] = str(value)
    return query_params.urlencode()


def _distinct_query_values(request, key: str) -> list[str]:
    seen = []
    for value in request.GET.getlist(key):
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def _build_attribute_filter_groups(base_queryset, request) -> list[dict[str, Any]]:
    attribute_groups = []
    attributes = (
        Attribute.objects.filter(is_filterable=True)
        .filter(
            Q(product_values__product__in=base_queryset)
            | Q(values__variants__product__in=base_queryset)
        )
        .distinct()
        .order_by("display_order", "name")
    )
    for attribute in attributes:
        param_name = f"attribute_{attribute.slug}"
        values = (
            AttributeValue.objects.filter(attribute=attribute, is_active=True)
            .filter(
                Q(product_assignments__product__in=base_queryset)
                | Q(variants__product__in=base_queryset)
            )
            .distinct()
            .order_by("display_order", "value")
        )
        options = [
            {
                "label": value.value,
                "value": value.slug,
                "selected": value.slug in request.GET.getlist(param_name),
                "color_hex": value.color_hex,
            }
            for value in values
        ]
        if options:
            attribute_groups.append(
                {
                    "name": attribute.name,
                    "slug": attribute.slug,
                    "param_name": param_name,
                    "options": options,
                }
            )
    return attribute_groups


def build_catalog_filter_options(base_queryset, request) -> dict[str, Any]:
    categories = (
        Category.objects.filter(
            is_active=True,
            is_visible=True,
            products__in=base_queryset,
        )
        .distinct()
        .order_by("parent__display_order", "display_order", "name")
    )
    brands = (
        Brand.objects.filter(is_active=True, products__in=base_queryset)
        .distinct()
        .order_by("-featured", "display_order", "name")
    )
    return {
        "categories": [
            {
                "label": category.name,
                "value": category.slug,
                "selected": category.slug in request.GET.getlist("category"),
                "depth": 1 if category.parent_id else 0,
            }
            for category in categories
        ],
        "brands": [
            {
                "label": brand.name,
                "value": brand.slug,
                "selected": brand.slug in request.GET.getlist("brand"),
            }
            for brand in brands
        ],
        "attributes": _build_attribute_filter_groups(base_queryset, request),
    }


def build_active_filter_chips(request, filter_options: dict[str, Any]) -> list[dict[str, str]]:
    category_lookup = {option["value"]: option["label"]
                       for option in filter_options["categories"]}
    brand_lookup = {option["value"]: option["label"]
                    for option in filter_options["brands"]}
    attribute_lookup = {}
    for group in filter_options["attributes"]:
        for option in group["options"]:
            attribute_lookup[(group["param_name"], option["value"])
                             ] = f"{group['name']}: {option['label']}"

    chips = []
    for category_slug in _distinct_query_values(request, "category"):
        chips.append({"label": category_lookup.get(
            category_slug, category_slug), "value": category_slug, "kind": "category"})
    for brand_slug in _distinct_query_values(request, "brand"):
        chips.append({"label": brand_lookup.get(
            brand_slug, brand_slug), "value": brand_slug, "kind": "brand"})
    if request.GET.get("availability") == "in_stock":
        chips.append(
            {"label": "In stock", "value": "in_stock", "kind": "availability"})
    if request.GET.get("discount") == "on_sale":
        chips.append(
            {"label": "On sale", "value": "on_sale", "kind": "discount"})
    if request.GET.get("min_price"):
        chips.append({"label": f"Min {request.GET['min_price']}",
                     "value": request.GET["min_price"], "kind": "min_price"})
    if request.GET.get("max_price"):
        chips.append({"label": f"Max {request.GET['max_price']}",
                     "value": request.GET["max_price"], "kind": "max_price"})
    for key in request.GET.keys():
        if not key.startswith("attribute_"):
            continue
        for value in _distinct_query_values(request, key):
            chips.append({"label": attribute_lookup.get(
                (key, value), value), "value": value, "kind": key})
    return chips


def apply_catalog_filters(queryset, request, *, tag=None):
    queryset = annotate_product_pricing(queryset)
    active_flash_sale = get_active_flash_sale(request)
    flash_sale_lookup = build_flash_sale_lookup(active_flash_sale)

    query = request.GET.get("q", "").strip()
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query)
            | Q(short_description__icontains=query)
            | Q(description__icontains=query)
            | Q(sku__icontains=query)
            | Q(tags__name__icontains=query)
            | Q(brand__name__icontains=query)
            | Q(attribute_values__value_text__icontains=query)
            | Q(attribute_values__value_option__value__icontains=query)
            | Q(variants__option_values__value__icontains=query)
        )

    brand_slugs = _distinct_query_values(request, "brand")
    if brand_slugs:
        queryset = queryset.filter(brand__slug__in=brand_slugs)

    category_slugs = _distinct_query_values(request, "category")
    if category_slugs:
        queryset = queryset.filter(categories__slug__in=category_slugs)

    if tag is not None:
        queryset = queryset.filter(tags=tag)

    min_price = request.GET.get("min_price")
    if min_price:
        try:
            queryset = queryset.filter(effective_price__gte=Decimal(min_price))
        except Exception:
            pass

    max_price = request.GET.get("max_price")
    if max_price:
        try:
            queryset = queryset.filter(effective_price__lte=Decimal(max_price))
        except Exception:
            pass

    if request.GET.get("availability") == "in_stock":
        queryset = queryset.filter(
            Q(variants__available_quantity__gt=0)
            | Q(variants__isnull=True, stock_status__in=["in_stock", "on_backorder"])
        )

    if request.GET.get("discount") == "on_sale":
        sale_filter = Q(effective_compare_price__gt=F(
            "effective_price")) | Q(is_on_sale=True)
        if flash_sale_lookup["product_ids"]:
            sale_filter |= Q(id__in=list(flash_sale_lookup["product_ids"]))
        queryset = queryset.filter(sale_filter)

    for key in request.GET.keys():
        if not key.startswith("attribute_"):
            continue
        values = _distinct_query_values(request, key)
        if not values:
            continue
        attribute_slug = key.replace("attribute_", "", 1)
        queryset = queryset.filter(
            Q(attribute_values__attribute__slug=attribute_slug,
              attribute_values__value_option__slug__in=values)
            | Q(variants__option_values__attribute__slug=attribute_slug, variants__option_values__slug__in=values)
        )

    queryset = queryset.annotate(
        discount_priority=Case(
            When(
                Q(effective_compare_price__gt=F("effective_price")) | Q(
                    is_on_sale=True) | Q(id__in=list(flash_sale_lookup["product_ids"])),
                then=Value(0),
            ),
            default=Value(1),
            output_field=IntegerField(),
        )
    )

    sort_order = resolve_sort_order(request)
    sort_mapping = {
        "newest": ("discount_priority", "-published_at", "-created_at"),
        "popular": ("discount_priority", "-sales_count", "-view_count", "-created_at"),
        "price_asc": ("discount_priority", "effective_price", "name"),
        "price_desc": ("discount_priority", "-effective_price", "name"),
        "name_asc": ("discount_priority", "name"),
        "name_desc": ("discount_priority", "-name"),
    }
    queryset = queryset.order_by(
        *sort_mapping.get(sort_order, sort_mapping["newest"]))
    return queryset.distinct(), sort_order, flash_sale_lookup


def build_catalog_page(
    request,
    *,
    queryset,
    page_title: str,
    page_description: str,
    breadcrumbs: list[dict[str, str]],
    hero_title: str | None = None,
    hero_body: str | None = None,
    extra_context: dict[str, Any] | None = None,
):
    product_display_settings = get_product_display_settings_cached(request)
    base_queryset = annotate_product_pricing(queryset).distinct()
    filtered_queryset, sort_order, flash_sale_lookup = apply_catalog_filters(
        queryset, request)
    page_obj, paginator = paginate_queryset(
        filtered_queryset,
        request.GET.get("page"),
        getattr(product_display_settings, "products_per_page", 24),
    )
    store_settings = get_store_settings_cached(request)
    currency = getattr(store_settings, "currency",
                       "USD") if store_settings else "USD"
    filter_options = build_catalog_filter_options(base_queryset, request)
    query_without_page = build_querystring(request, page=None)

    context = {
        "page_title": page_title,
        "page_description": page_description,
        "hero_title": hero_title or page_title,
        "hero_body": hero_body or page_description,
        "breadcrumbs": breadcrumbs,
        "page_obj": page_obj,
        "paginator": paginator,
        "products": [serialize_product_card(product, currency, flash_sale_lookup=flash_sale_lookup) for product in page_obj.object_list],
        "result_count": filtered_queryset.count(),
        "current_sort": sort_order,
        "active_brands": _distinct_query_values(request, "brand"),
        "active_categories": _distinct_query_values(request, "category"),
        "active_query": request.GET.get("q", "").strip(),
        "active_min_price": request.GET.get("min_price", ""),
        "active_max_price": request.GET.get("max_price", ""),
        "active_availability": request.GET.get("availability", ""),
        "active_discount": request.GET.get("discount", ""),
        "filter_options": filter_options,
        "active_filter_chips": build_active_filter_chips(request, filter_options),
        "clear_filters_url": request.path,
        "query_without_page": query_without_page,
        "ajax_results_url": f"{request.path}?{query_without_page}" if query_without_page else request.path,
    }
    if extra_context:
        context.update(extra_context)
    return context


def build_breadcrumbs(*items: tuple[str, str]) -> list[dict[str, str]]:
    return [{"label": label, "url": url} for label, url in items]


def get_related_product_cards(product: Product, request, limit: int = 4):
    category_ids = list(product.categories.values_list("id", flat=True))
    queryset = annotate_product_pricing(
        get_listable_product_queryset().exclude(id=product.id))
    if category_ids:
        queryset = queryset.filter(categories__id__in=category_ids)
    elif product.brand_id:
        queryset = queryset.filter(brand_id=product.brand_id)
    queryset = queryset.distinct().order_by(
        "-sales_count", "-view_count", "-created_at")[:limit]
    currency = getattr(get_store_settings_cached(request), "currency", "USD")
    flash_sale_lookup = build_flash_sale_lookup(get_active_flash_sale(request))
    return [serialize_product_card(item, currency, flash_sale_lookup=flash_sale_lookup) for item in queryset]


def get_serialized_products(queryset, request, limit: int | None = None):
    currency = getattr(get_store_settings_cached(request), "currency", "USD")
    if limit is not None:
        queryset = queryset[:limit]
    flash_sale_lookup = build_flash_sale_lookup(get_active_flash_sale(request))
    return [serialize_product_card(product, currency, flash_sale_lookup=flash_sale_lookup) for product in queryset]


def get_or_create_customer_profile(user) -> Customer | None:
    if not getattr(user, "is_authenticated", False):
        return None
    customer_user_model = Customer._meta.get_field("user").remote_field.model
    if customer_user_model is None or not isinstance(user, customer_user_model):
        return None
    customer, _ = Customer.objects.get_or_create(
        user=user,
        defaults={"status": Customer.Status.ACTIVE},
    )
    return customer


def generate_checkout_token() -> str:
    return uuid.uuid4().hex


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def get_cart_session_identifier(request) -> str:
    ensure_request_session(request)
    session_key_name = tenant_session_key(request, "cart_session_key")
    session_identifier = request.session.get(
        session_key_name) or request.session.session_key
    request.session[session_key_name] = session_identifier
    request.session.modified = True
    return session_identifier


def _prefetched_cart_queryset():
    return Cart.objects.select_related("customer__user").prefetch_related(
        Prefetch(
            "items",
            queryset=CartItem.objects.select_related(
                "variant__product").order_by("created_at"),
        )
    )


def _merge_carts(target: Cart, source: Cart) -> None:
    for source_item in source.items.select_related("variant__product"):
        target_item = target.items.filter(variant=source_item.variant).first()
        if target_item:
            target_item.quantity += source_item.quantity
            target_item.save(update_fields=["quantity", "updated_at"])
        else:
            source_item.pk = None
            source_item.cart = target
            source_item.save()
    source.status = Cart.CartStatus.CONVERTED
    source.converted_at = timezone.now()
    source.save(update_fields=["status", "converted_at", "updated_at"])


def get_discount_code(code: str | None):
    if not code or DiscountCode is None:
        return None
    now = timezone.now()
    try:
        return (
            DiscountCode.objects.filter(
                code__iexact=code.strip(), is_active=True)
            .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
            .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
            .first()
        )
    except Exception:
        return None


def _resolve_variant_cart_pricing_details(
    variant: ProductVariant,
    *,
    customer=None,
    quantity: int = 1,
    currency_code: str = "USD",
) -> dict[str, Any]:
    quantity = max(int(quantity or 1), 1)
    result = resolve_price(
        variant,
        PricingContext(
            customer=customer,
            quantity=quantity,
            currency_code=currency_code or "USD",
        ),
    )
    compare_at_price = quantize_money(result.compare_at_price) if result.compare_at_price else None
    details: dict[str, Any] = {
        "unit_price": quantize_money(result.final_price),
        "compare_at_price": compare_at_price if compare_at_price and compare_at_price > result.final_price else None,
        "original_price": quantize_money(result.base_price),
        "pricing_layer": result.applied_layer,
        "flash_sale_id": result.flash_sale_id,
        "flash_sale_item_id": None,
        "volume_tier_min_qty": result.volume_tier_min_qty if result.volume_tier_applied else None,
        "volume_tier_discount_pct": str(result.volume_tier_discount_pct or "") if result.volume_tier_applied else "",
        "price_list_id": result.price_list_id,
        "price_list_code": result.price_list_code,
        "price_list_name": result.price_list_name,
        "sale_badge": result.sale_badge,
        "savings_label": result.savings_label,
        "savings_percentage": str(result.savings_percentage or ""),
    }
    if FlashSaleItem is not None and result.flash_sale_applied and result.flash_sale_id:
        flash_sale_item = (
            FlashSaleItem.objects.filter(
                flash_sale_id=result.flash_sale_id,
                is_active=True,
            )
            .filter(Q(variant=variant) | Q(product=variant.product, variant__isnull=True))
            .order_by("-variant")
            .first()
        )
        if flash_sale_item:
            details["flash_sale_item_id"] = str(flash_sale_item.id)
    return details


def _update_cart_item_pricing_snapshot(item: CartItem, pricing_details: dict[str, Any]) -> None:
    properties = dict(item.custom_properties or {})
    properties["pricing_snapshot"] = {
        "pricing_layer": pricing_details.get("pricing_layer", "base"),
        "flash_sale_id": pricing_details.get("flash_sale_id") or "",
        "flash_sale_item_id": pricing_details.get("flash_sale_item_id") or "",
        "volume_tier_min_qty": pricing_details.get("volume_tier_min_qty") or "",
        "price_list_id": pricing_details.get("price_list_id") or "",
        "price_list_code": pricing_details.get("price_list_code") or "",
    }
    item.custom_properties = properties


def _cart_items_for_discount_engine(cart: Cart) -> list[dict[str, Any]]:
    return [
        {
            "id": str(item.id),
            "variant": item.variant,
            "product": item.variant.product if item.variant else None,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "line_subtotal": item.line_total,
            "compare_at_price": item.compare_at_price,
            "sku": item.sku,
            "product_title": item.product_title,
        }
        for item in cart.items.select_related("variant__product").all()
        if item.variant_id
    ]


def _line_discount_map(line_allocations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        allocation["order_item_id"]: allocation
        for allocation in line_allocations
    }


def _bundle_item_matches_cart_item(bundle_item, cart_item: CartItem) -> bool:
    if bundle_item.variant_id:
        return cart_item.variant_id == bundle_item.variant_id
    if bundle_item.product_id:
        return getattr(cart_item.variant, "product_id", None) == bundle_item.product_id
    if bundle_item.category_id:
        try:
            return cart_item.variant.product.categories.filter(pk=bundle_item.category_id).exists()
        except Exception:
            return False
    return False


def _bundle_candidate_lines(bundle_items, cart_items):
    matched = []
    for cart_item in cart_items:
        for bundle_item in bundle_items:
            if _bundle_item_matches_cart_item(bundle_item, cart_item):
                matched.append((bundle_item, cart_item))
                break
    return matched


def _merge_line_allocations(
    primary_allocations: list[dict[str, Any]],
    secondary_allocations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for allocation in [*primary_allocations, *secondary_allocations]:
        order_item_id = str(allocation.get("order_item_id") or "")
        if not order_item_id:
            continue
        bucket = buckets.setdefault(
            order_item_id,
            {
                "order_item_id": order_item_id,
                "sku": allocation.get("sku", ""),
                "product_title": allocation.get("product_title", ""),
                "unit_discount": Decimal("0.00"),
                "line_discount": Decimal("0.00"),
                "sources": [],
            },
        )
        bucket["sku"] = bucket["sku"] or allocation.get("sku", "")
        bucket["product_title"] = bucket["product_title"] or allocation.get("product_title", "")
        bucket["unit_discount"] = quantize_money(bucket["unit_discount"] + quantize_money(allocation.get("unit_discount")))
        bucket["line_discount"] = quantize_money(bucket["line_discount"] + quantize_money(allocation.get("line_discount")))
        bucket["sources"].extend(list(allocation.get("sources") or []))
    return list(buckets.values())


def _evaluate_bundle_discounts(
    cart: Cart,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if BundleOffer is None:
        return [], [], []

    now = timezone.now()
    cart_items = list(cart.items.select_related("variant__product").all())
    if not cart_items:
        return [], [], []

    bundle_rows: list[dict[str, Any]] = []
    line_allocations: list[dict[str, Any]] = []
    bundle_ledgers: list[dict[str, Any]] = []
    active_bundles = (
        BundleOffer.objects.filter(is_active=True, is_public=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        .prefetch_related("items__product", "items__variant", "items__category")
    )

    for bundle in active_bundles:
        items = list(bundle.items.all())
        if not items:
            continue

        discount_amount = Decimal("0.00")
        targeted_cart_items: list[CartItem] = []
        bundle_quantity = 0
        revenue_attributed = Decimal("0.00")

        if bundle.offer_type == BundleOffer.OfferType.FIXED:
            required_items = [item for item in items if item.role == BundleOfferItem.ItemRole.REQUIRED]
            if not required_items or bundle.bundle_price is None:
                continue
            bundle_units = None
            for bundle_item in required_items:
                matching_qty = sum(
                    cart_item.quantity
                    for cart_item in cart_items
                    if _bundle_item_matches_cart_item(bundle_item, cart_item)
                )
                units_for_item = matching_qty // max(1, int(bundle_item.quantity or 1))
                bundle_units = units_for_item if bundle_units is None else min(bundle_units, units_for_item)
            bundle_units = int(bundle_units or 0)
            if bundle_units <= 0:
                continue
            bundle_quantity = bundle_units
            for bundle_item in required_items:
                targeted_cart_items.extend(
                    cart_item for cart_item in cart_items if _bundle_item_matches_cart_item(bundle_item, cart_item)
                )
            unique_targeted = {str(item.id): item for item in targeted_cart_items}
            regular_total = sum(
                quantize_money(cart_item.unit_price) * Decimal(cart_item.quantity)
                for cart_item in unique_targeted.values()
            )
            revenue_attributed = quantize_money(regular_total)
            discount_amount = max(Decimal("0.00"), quantize_money(regular_total - (quantize_money(bundle.bundle_price) * bundle_units)))

        elif bundle.offer_type == BundleOffer.OfferType.MIX_MATCH:
            choice_items = [item for item in items if item.role in {BundleOfferItem.ItemRole.CHOICE, BundleOfferItem.ItemRole.REQUIRED}]
            if not choice_items or bundle.bundle_price is None:
                continue
            matching = [cart_item for cart_item in cart_items if any(_bundle_item_matches_cart_item(bundle_item, cart_item) for bundle_item in choice_items)]
            total_qty = sum(item.quantity for item in matching)
            required_qty = max(1, int(bundle.required_quantity or bundle.min_selection or 1))
            bundle_groups = total_qty // required_qty
            if bundle_groups <= 0:
                continue
            bundle_quantity = bundle_groups
            targeted_cart_items = matching
            regular_total = sum(quantize_money(item.unit_price) * Decimal(item.quantity) for item in matching)
            bundle_total = quantize_money(bundle.bundle_price) * bundle_groups
            revenue_attributed = quantize_money(regular_total)
            discount_amount = max(Decimal("0.00"), quantize_money(regular_total - bundle_total))

        elif bundle.offer_type == BundleOffer.OfferType.UPSELL:
            if not bundle.upsell_parent_product_id:
                continue
            parent_in_cart = any(getattr(item.variant, "product_id", None) == bundle.upsell_parent_product_id for item in cart_items)
            if not parent_in_cart:
                continue
            upsell_items = [item for item in items if item.role == BundleOfferItem.ItemRole.UPSELL]
            matching = [cart_item for cart_item in cart_items if any(_bundle_item_matches_cart_item(bundle_item, cart_item) for bundle_item in upsell_items)]
            if not matching:
                continue
            targeted_cart_items = matching
            bundle_quantity = sum(item.quantity for item in matching)
            for cart_item in matching:
                bundle_item = next((candidate for candidate in upsell_items if _bundle_item_matches_cart_item(candidate, cart_item)), None)
                if bundle_item is None:
                    continue
                if bundle_item.discounted_unit_price is not None:
                    per_unit_discount = max(Decimal("0.00"), quantize_money(cart_item.unit_price - bundle_item.discounted_unit_price))
                elif bundle_item.discount_percentage:
                    per_unit_discount = quantize_money(cart_item.unit_price * (Decimal(str(bundle_item.discount_percentage)) / Decimal("100")))
                else:
                    per_unit_discount = Decimal("0.00")
                discount_amount += quantize_money(per_unit_discount * cart_item.quantity)
                revenue_attributed += quantize_money(cart_item.unit_price * Decimal(cart_item.quantity))

        discount_amount = quantize_money(discount_amount)
        if discount_amount <= 0 or not targeted_cart_items:
            continue

        unique_targeted = {str(item.id): item for item in targeted_cart_items}
        bundle_rows.append(
            {
                "discount_type": "bundle",
                "code": "",
                "discount_id": str(bundle.id),
                "description": bundle.public_title or bundle.name,
                "amount": discount_amount,
                "is_percentage": False,
                "percentage_value": None,
                "allocation_method": "across",
            }
        )
        bundle_ledgers.append(
            {
                "bundle_id": str(bundle.id),
                "quantity": max(1, int(bundle_quantity or 1)),
                "discount_amount": discount_amount,
                "revenue_attributed": quantize_money(revenue_attributed or sum(item.line_total for item in unique_targeted.values())),
                "item_ids": list(unique_targeted.keys()),
                "offer_type": bundle.offer_type,
                "title": bundle.public_title or bundle.name,
            }
        )
        line_allocations.extend(
            {
                "order_item_id": allocation.order_item_id,
                "sku": allocation.sku,
                "product_title": allocation.product_title,
                "unit_discount": allocation.unit_discount,
                "line_discount": allocation.line_discount,
                "sources": [
                    {
                        "type": "bundle",
                        "label": bundle.public_title or bundle.name,
                        "amount": allocation.line_discount,
                        "discount_id": str(bundle.id),
                    }
                ],
            }
            for allocation in calculate_line_level_discounts(
                [
                    {
                        "id": str(item.id),
                        "sku": item.sku,
                        "product_title": item.product_title,
                        "quantity": item.quantity,
                        "subtotal": item.line_total,
                        "unit_price": item.unit_price,
                    }
                    for item in unique_targeted.values()
                ],
                discount_amount,
                allocation_method="across",
            )
        )

    return bundle_rows, line_allocations, bundle_ledgers


def _evaluate_all_cart_promotions(
    cart: Cart,
    *,
    customer,
    cart_items: list[dict[str, Any]],
    subtotal: Decimal,
    shipping_total: Decimal,
    currency_code: str,
    ip_address: str = "",
) -> dict[str, Any]:
    discount_evaluation = evaluate_cart_discounts(
        cart_subtotal=subtotal,
        cart_items=cart_items,
        customer=customer,
        code=cart.discount_code,
        shipping_total=shipping_total,
        currency_code=currency_code,
        ip_address=ip_address,
        session_key=cart.session_key,
        cart_token=cart.checkout_token,
        cart_id=cart.id,
    )
    if not discount_evaluation["valid"]:
        return discount_evaluation

    bundle_rows, bundle_allocations, bundle_ledgers = _evaluate_bundle_discounts(cart)
    merged_rows = list(discount_evaluation["applied_discounts"]) + bundle_rows
    merged_allocations = _merge_line_allocations(
        list(discount_evaluation["line_allocations"]),
        bundle_allocations,
    )
    bundle_total = quantize_money(sum((row.get("amount") or Decimal("0.00")) for row in bundle_rows))
    discount_evaluation["applied_discounts"] = merged_rows
    discount_evaluation["line_allocations"] = merged_allocations
    discount_evaluation["discount_total"] = quantize_money(discount_evaluation["discount_total"] + bundle_total)
    discount_evaluation["bundle_rows"] = bundle_rows
    discount_evaluation["bundle_ledgers"] = bundle_ledgers
    return discount_evaluation


def _persist_cart_discount_rows(cart: Cart, applied_discounts: list[dict[str, Any]]) -> None:
    from public.cart.models import CartDiscount

    cart.discounts.filter(
        discount_type__in=[
            CartDiscount.DiscountType.CODE,
            CartDiscount.DiscountType.AUTOMATIC,
            CartDiscount.DiscountType.BUNDLE,
        ]
    ).delete()
    bulk_rows = [
        CartDiscount(
            cart=cart,
            discount_type=(
                CartDiscount.DiscountType.CODE
                if row["discount_type"] == "code"
                else CartDiscount.DiscountType.BUNDLE
                if row["discount_type"] == "bundle"
                else CartDiscount.DiscountType.AUTOMATIC
            ),
            code=row.get("code", ""),
            discount_id=row.get("discount_id") or None,
            description=row.get("description", ""),
            amount=quantize_money(row.get("amount")),
            is_percentage=bool(row.get("is_percentage")),
            percentage_value=row.get("percentage_value"),
        )
        for row in applied_discounts
        if quantize_money(row.get("amount")) > 0 or row["discount_type"] in {"code", "automatic", "bundle"}
    ]
    if bulk_rows:
        CartDiscount.objects.bulk_create(bulk_rows)


def recalculate_cart(cart: Cart):
    try:
        settings_obj = StoreSettings.objects.first()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(
            "Store settings unavailable during cart recalculation: %s", exc)
        settings_obj = None
    currency_code = cart.currency or getattr(settings_obj, "currency", "USD")
    customer = cart.customer

    for item in cart.items.select_related("variant__product").all():
        pricing_details = _resolve_variant_cart_pricing_details(
            item.variant,
            customer=customer,
            quantity=item.quantity,
            currency_code=currency_code,
        )
        item.unit_price = pricing_details["unit_price"]
        item.compare_at_price = pricing_details["compare_at_price"]
        item.original_price = pricing_details["original_price"]
        _update_cart_item_pricing_snapshot(item, pricing_details)
        item.save(
            update_fields=[
                "unit_price",
                "compare_at_price",
                "original_price",
                "custom_properties",
                "updated_at",
            ]
        )

    cart_items = _cart_items_for_discount_engine(cart)
    subtotal = quantize_money(sum((item["line_subtotal"] for item in cart_items), Decimal("0.00")))
    base_shipping_total = quantize_money(cart.shipping_total)
    discount_evaluation = _evaluate_all_cart_promotions(
        cart,
        customer=customer,
        cart_items=cart_items,
        subtotal=subtotal,
        shipping_total=base_shipping_total,
        currency_code=currency_code,
        ip_address=getattr(cart, "ip_address", ""),
    )

    if not discount_evaluation["valid"]:
        cart.discount_code = ""
        discount_evaluation = _evaluate_all_cart_promotions(
            cart,
            customer=customer,
            cart_items=cart_items,
            subtotal=subtotal,
            shipping_total=base_shipping_total,
            currency_code=currency_code,
            ip_address=getattr(cart, "ip_address", ""),
        )

    _persist_cart_discount_rows(cart, discount_evaluation["applied_discounts"])

    merchandise_discount_total = quantize_money(discount_evaluation["discount_total"])
    shipping_discount_total = quantize_money(discount_evaluation["shipping_discount_total"])
    shipping_total = max(Decimal("0.00"), quantize_money(base_shipping_total - shipping_discount_total))
    total_discount = quantize_money(merchandise_discount_total + shipping_discount_total)

    tax_total = Decimal("0.00")
    if settings_obj and getattr(settings_obj, "tax_enabled", False):
        taxable_amount = subtotal - merchandise_discount_total + shipping_total
        if not getattr(settings_obj, "charge_tax_on_shipping", True):
            taxable_amount = subtotal - merchandise_discount_total
        tax_rate = Decimal(str(getattr(settings_obj, "default_tax_rate", Decimal("0.00")) or Decimal("0.00")))
        tax_total = quantize_money(taxable_amount * (tax_rate / Decimal("100")))

    grand_total = quantize_money(subtotal - merchandise_discount_total + shipping_total + tax_total)
    cart.subtotal = subtotal
    cart.discount_total = total_discount
    cart.shipping_total = shipping_total
    cart.tax_total = tax_total
    cart.grand_total = grand_total
    cart.last_activity_at = timezone.now()
    cart.save(
        update_fields=[
            "subtotal",
            "discount_total",
            "shipping_total",
            "tax_total",
            "grand_total",
            "discount_code",
            "last_activity_at",
            "updated_at",
        ]
    )
    return cart


def get_or_create_cart(request) -> Cart:
    session_identifier = get_cart_session_identifier(request)
    update_promo_context(
        request,
        utm_source=request.GET.get("utm_source", ""),
        utm_medium=request.GET.get("utm_medium", ""),
        utm_campaign=request.GET.get("utm_campaign", ""),
        utm_content=request.GET.get("utm_content", ""),
        promo_code=request.GET.get("discount") or request.GET.get("code") or "",
        referral_slug=request.GET.get("ref") or request.GET.get("partner") or "",
        landing_path=request.path,
        referrer_url=request.META.get("HTTP_REFERER", ""),
    )
    promo_context = get_promo_context(request)
    defaults = {
        "status": Cart.CartStatus.ACTIVE,
        "session_key": session_identifier,
        "email": getattr(getattr(request, "user", None), "email", "") or "",
        "checkout_token": generate_checkout_token(),
        "ip_address": get_client_ip(request),
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
        "utm_source": promo_context.get("utm_source", ""),
        "utm_medium": promo_context.get("utm_medium", ""),
        "utm_campaign": promo_context.get("utm_campaign", ""),
        "referrer_url": promo_context.get("referrer_url", ""),
    }

    customer = None
    if getattr(request.user, "is_authenticated", False):
        customer = get_or_create_customer_profile(request.user)

    if customer is not None:
        cart = _prefetched_cart_queryset().filter(
            customer=customer, status=Cart.CartStatus.ACTIVE).first()
        guest_cart = _prefetched_cart_queryset().filter(session_key=session_identifier,
                                                         status=Cart.CartStatus.ACTIVE).exclude(customer=customer).first()
        if cart is None:
            cart = Cart.objects.create(customer=customer, **defaults)
        if guest_cart and guest_cart.pk != cart.pk:
            _merge_carts(cart, guest_cart)
        if (
            cart.email != request.user.email
            or cart.session_key != session_identifier
            or not cart.checkout_token
            or cart.utm_source != promo_context.get("utm_source", cart.utm_source)
            or cart.utm_medium != promo_context.get("utm_medium", cart.utm_medium)
            or cart.utm_campaign != promo_context.get("utm_campaign", cart.utm_campaign)
            or cart.referrer_url != promo_context.get("referrer_url", cart.referrer_url)
        ):
            cart.email = request.user.email
            cart.session_key = session_identifier
            if not cart.checkout_token:
                cart.checkout_token = generate_checkout_token()
            cart.utm_source = promo_context.get("utm_source", cart.utm_source)
            cart.utm_medium = promo_context.get("utm_medium", cart.utm_medium)
            cart.utm_campaign = promo_context.get("utm_campaign", cart.utm_campaign)
            cart.referrer_url = promo_context.get("referrer_url", cart.referrer_url)
            cart.save(update_fields=[
                      "email", "session_key", "checkout_token", "utm_source", "utm_medium", "utm_campaign", "referrer_url", "updated_at"])
    else:
        cart = _prefetched_cart_queryset().filter(session_key=session_identifier,
                                                  status=Cart.CartStatus.ACTIVE).first()
        if cart is None:
            cart = Cart.objects.create(**defaults)
        elif (
            not cart.checkout_token
            or cart.utm_source != promo_context.get("utm_source", cart.utm_source)
            or cart.utm_medium != promo_context.get("utm_medium", cart.utm_medium)
            or cart.utm_campaign != promo_context.get("utm_campaign", cart.utm_campaign)
            or cart.referrer_url != promo_context.get("referrer_url", cart.referrer_url)
        ):
            cart.checkout_token = generate_checkout_token()
            cart.utm_source = promo_context.get("utm_source", cart.utm_source)
            cart.utm_medium = promo_context.get("utm_medium", cart.utm_medium)
            cart.utm_campaign = promo_context.get("utm_campaign", cart.utm_campaign)
            cart.referrer_url = promo_context.get("referrer_url", cart.referrer_url)
            cart.save(update_fields=["checkout_token", "utm_source", "utm_medium", "utm_campaign", "referrer_url", "updated_at"])

    return recalculate_cart(_prefetched_cart_queryset().get(pk=cart.pk))


def get_cart_item_count(request) -> int:
    try:
        return get_or_create_cart(request).item_count
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("Cart count fallback used: %s", exc)
        return 0


def _resolve_variant_cart_prices(
    variant: ProductVariant,
    *,
    customer=None,
    quantity: int = 1,
    currency_code: str = "USD",
) -> tuple[Decimal, Decimal | None, Decimal]:
    pricing_details = _resolve_variant_cart_pricing_details(
        variant,
        customer=customer,
        quantity=quantity,
        currency_code=currency_code,
    )
    return (
        pricing_details["unit_price"],
        pricing_details["compare_at_price"],
        pricing_details["original_price"],
    )


def add_variant_to_cart(cart: Cart, variant: ProductVariant, quantity: int = 1) -> Cart:
    quantity = max(int(quantity or 1), 1)
    item = cart.items.filter(variant=variant).first()
    primary_image = variant.product.images.order_by(
        "-is_primary", "display_order", "created_at").first()
    new_quantity = (item.quantity + quantity) if item else quantity
    pricing_details = _resolve_variant_cart_pricing_details(
        variant,
        customer=cart.customer,
        quantity=new_quantity,
        currency_code=cart.currency or "USD",
    )
    if item:
        item.quantity += quantity
        item.unit_price = pricing_details["unit_price"]
        item.compare_at_price = pricing_details["compare_at_price"]
        item.original_price = pricing_details["original_price"]
        _update_cart_item_pricing_snapshot(item, pricing_details)
        item.save(update_fields=["quantity", "unit_price",
                  "compare_at_price", "original_price", "custom_properties", "updated_at"])
    else:
        item = CartItem.objects.create(
            cart=cart,
            variant=variant,
            quantity=quantity,
            unit_price=pricing_details["unit_price"],
            compare_at_price=pricing_details["compare_at_price"],
            original_price=pricing_details["original_price"],
            product_title=variant.product.name,
            variant_title=variant.variant_name,
            product_image_url=primary_image.image.url if primary_image and primary_image.image else "",
            sku=variant.sku,
            requires_shipping=variant.product.requires_shipping,
        )
        _update_cart_item_pricing_snapshot(item, pricing_details)
        item.save(update_fields=["custom_properties", "updated_at"])
    return recalculate_cart(_prefetched_cart_queryset().get(pk=cart.pk))


def update_cart_from_payload(request, cart: Cart) -> Cart:
    for item in list(cart.items.all()):
        quantity_value = request.POST.get(f"quantity_{item.id}")
        if quantity_value is None:
            continue
        try:
            quantity = int(quantity_value)
        except (TypeError, ValueError):
            quantity = item.quantity

        if quantity <= 0:
            item.delete()
        else:
            item.quantity = quantity
            pricing_details = _resolve_variant_cart_pricing_details(
                item.variant,
                customer=cart.customer,
                quantity=quantity,
                currency_code=cart.currency or "USD",
            )
            item.unit_price = pricing_details["unit_price"]
            item.compare_at_price = pricing_details["compare_at_price"]
            item.original_price = pricing_details["original_price"]
            _update_cart_item_pricing_snapshot(item, pricing_details)
            item.save(update_fields=["quantity", "unit_price", "compare_at_price", "original_price", "custom_properties", "updated_at"])

    remove_item_id = request.POST.get("remove_item")
    if remove_item_id:
        cart.items.filter(id=remove_item_id).delete()

    return recalculate_cart(_prefetched_cart_queryset().get(pk=cart.pk))


def apply_coupon_to_cart(cart: Cart, code: str) -> Cart:
    cleaned_code = (code or "").strip().upper()
    validation = validate_discount_code(
        code=cleaned_code,
        cart_subtotal=quantize_money(cart.subtotal),
        customer=cart.customer,
        cart_items=_cart_items_for_discount_engine(cart),
        ip_address=getattr(cart, "ip_address", ""),
        shipping_total=quantize_money(cart.shipping_total),
        currency_code=cart.currency or "USD",
        session_key=cart.session_key,
        cart_token=cart.checkout_token,
        cart_id=cart.id,
    )
    if not validation.valid:
        raise ValueError(validation.message)

    cart.discount_code = cleaned_code
    cart.save(update_fields=["discount_code", "updated_at"])
    return recalculate_cart(_prefetched_cart_queryset().get(pk=cart.pk))


def get_cart_summary(request) -> dict[str, Any]:
    cart = get_or_create_cart(request)
    settings_obj = get_store_settings_cached(request)
    currency = getattr(settings_obj, "currency",
                       "USD") if settings_obj else "USD"
    items = []
    for item in cart.items.all():
        image_url = item.product_image_url
        if not image_url and item.variant and item.variant.product.images.exists():
            primary_image = item.variant.product.images.order_by(
                "-is_primary", "display_order").first()
            image_url = primary_image.image.url if primary_image and primary_image.image else ""
        items.append(
            {
                "id": str(item.id),
                "product_name": item.product_title or item.variant.product.name,
                "variant_name": item.variant_title,
                "sku": item.sku,
                "quantity": item.quantity,
                "unit_price": quantize_money(item.unit_price),
                "unit_price_display": format_money(item.unit_price, currency),
                "compare_at_price": quantize_money(item.compare_at_price) if item.compare_at_price else None,
                "compare_at_price_display": format_money(item.compare_at_price, currency) if item.compare_at_price and item.compare_at_price > item.unit_price else "",
                "line_total": quantize_money(item.line_total),
                "line_total_display": format_money(item.line_total, currency),
                "image_url": image_url,
                "product_url": safe_reverse("product:product_detail", product_slug=item.variant.product.slug) if item.variant else "#",
            }
        )
    discount_lines = [
        {
            "type": discount.discount_type,
            "label": discount.description or discount.code or discount.discount_type.replace("_", " ").title(),
            "amount": quantize_money(discount.amount),
            "amount_display": format_money(discount.amount, currency),
            "code": discount.code,
        }
        for discount in cart.discounts.all()
    ]
    return {
        "id": str(cart.id),
        "item_count": cart.item_count,
        "items": items,
        "discount_lines": discount_lines,
        "subtotal": quantize_money(cart.subtotal),
        "discount_total": quantize_money(cart.discount_total),
        "shipping_total": quantize_money(cart.shipping_total),
        "tax_total": quantize_money(cart.tax_total),
        "grand_total": quantize_money(cart.grand_total),
        "subtotal_display": format_money(cart.subtotal, currency),
        "discount_total_display": format_money(cart.discount_total, currency),
        "shipping_total_display": format_money(cart.shipping_total, currency),
        "tax_total_display": format_money(cart.tax_total, currency),
        "grand_total_display": format_money(cart.grand_total, currency),
        "currency": currency,
        "currency_symbol": get_currency_symbol(currency),
        "discount_code": cart.discount_code,
        "checkout_token": cart.checkout_token,
        "is_empty": cart.is_empty,
    }


def _get_session_product_ids(request, key_suffix: str) -> list[str]:
    return list(request.session.get(tenant_session_key(request, key_suffix), []))


def _set_session_product_ids(request, key_suffix: str, ids: list[str]) -> None:
    request.session[tenant_session_key(request, key_suffix)] = ids
    request.session.modified = True


def toggle_session_product(request, key_suffix: str, product_id: str) -> bool:
    ids = _get_session_product_ids(request, key_suffix)
    if product_id in ids:
        ids.remove(product_id)
        _set_session_product_ids(request, key_suffix, ids)
        return False
    ids.insert(0, product_id)
    _set_session_product_ids(request, key_suffix, ids[:20])
    return True


def push_recently_viewed_product(request, product_id: str) -> None:
    ids = _get_session_product_ids(request, "recently_viewed")
    if product_id in ids:
        ids.remove(product_id)
    ids.insert(0, product_id)
    _set_session_product_ids(request, "recently_viewed", ids[:12])


def _resolve_session_products(request, key_suffix: str):
    ids = _get_session_product_ids(request, key_suffix)
    if not ids:
        return []
    products = {
        str(product.id): product
        for product in annotate_product_pricing(get_listable_product_queryset()).filter(id__in=ids)
    }
    currency = getattr(get_store_settings_cached(request), "currency", "USD")
    flash_sale_lookup = build_flash_sale_lookup(get_active_flash_sale(request))
    return [serialize_product_card(products[product_id], currency, flash_sale_lookup=flash_sale_lookup) for product_id in ids if product_id in products]


def get_wishlist_products(request):
    return _resolve_session_products(request, "wishlist")


def get_compare_products(request):
    return _resolve_session_products(request, "compare")


def get_recently_viewed_products(request):
    return _resolve_session_products(request, "recently_viewed")


def get_checkout_state(request) -> dict[str, Any]:
    return dict(request.session.get(tenant_session_key(request, "checkout_state"), {}))


def update_checkout_state(request, **values) -> dict[str, Any]:
    current = get_checkout_state(request)
    current.update(values)
    request.session[tenant_session_key(request, "checkout_state")] = current
    request.session.modified = True
    return current


def clear_checkout_state(request) -> None:
    request.session.pop(tenant_session_key(request, "checkout_state"), None)
    request.session.modified = True


def get_promo_context(request) -> dict[str, Any]:
    return dict(request.session.get(tenant_session_key(request, "promo_context"), {}))


def update_promo_context(request, **values) -> dict[str, Any]:
    current = get_promo_context(request)
    current.update({key: value for key, value in values.items() if value not in (None, "")})
    request.session[tenant_session_key(request, "promo_context")] = current
    request.session.modified = True
    return current


def clear_promo_context(request) -> None:
    request.session.pop(tenant_session_key(request, "promo_context"), None)
    request.session.modified = True


def get_shipping_methods(request, cart: Cart) -> list[dict[str, Any]]:
    settings_obj = get_store_settings_cached(request)
    currency = getattr(settings_obj, "currency",
                       "USD") if settings_obj else "USD"
    threshold = Decimal(getattr(settings_obj, "free_shipping_threshold", Decimal(
        "0.00")) or Decimal("0.00")) if settings_obj else Decimal("0.00")
    qualifies_for_free = bool(getattr(
        settings_obj, "free_shipping_enabled", False) and cart.subtotal >= threshold)
    processing_days = getattr(
        settings_obj, "processing_time_days", 2) if settings_obj else 2

    methods = [
        {
            "code": "standard",
            "label": "Standard delivery",
            "description": f"Dispatch in about {processing_days} business days.",
            "amount": Decimal("0.00") if qualifies_for_free else Decimal("10.00"),
        },
        {
            "code": "express",
            "label": "Express delivery",
            "description": "Priority handling with faster transit.",
            "amount": Decimal("20.00"),
        },
    ]
    if settings_obj and getattr(settings_obj, "allow_local_pickup", False):
        methods.append(
            {
                "code": "pickup",
                "label": "Local pickup",
                "description": "Collect from the store once your order is ready.",
                "amount": Decimal("0.00"),
            }
        )

    for method in methods:
        method["amount_display"] = format_money(method["amount"], currency)
    return methods


def get_payment_methods(request) -> list[dict[str, Any]]:
    settings_obj = get_store_settings_cached(request)
    currency = getattr(settings_obj, "currency",
                       "USD") if settings_obj else "USD"
    methods = [
        {
            "code": "card",
            "label": "Card payment",
            "description": f"Pay securely online in {currency}.",
        },
        {
            "code": "bank_transfer",
            "label": "Bank transfer",
            "description": "Place the order now and complete payment offline.",
        },
    ]
    if settings_obj and getattr(settings_obj, "allow_guest_checkout", True):
        methods.append(
            {
                "code": "cash_on_delivery",
                "label": "Cash on delivery",
                "description": "Pay when the order arrives.",
            }
        )
    return methods


def get_checkout_prefill(request) -> dict[str, Any]:
    state = get_checkout_state(request)
    prefill = {
        "email": state.get("email", ""),
        "first_name": state.get("first_name", ""),
        "last_name": state.get("last_name", ""),
        "phone": state.get("phone", ""),
        "company": state.get("company", ""),
        "address1": state.get("address1", ""),
        "address2": state.get("address2", ""),
        "city": state.get("city", ""),
        "state": state.get("state", ""),
        "postal_code": state.get("postal_code", ""),
        "country_code": state.get("country_code", "NG"),
        "delivery_instructions": state.get("delivery_instructions", ""),
        "marketing_opt_in": state.get("marketing_opt_in", False),
    }
    if getattr(request.user, "is_authenticated", False):
        prefill["email"] = request.user.email
        prefill["first_name"] = prefill["first_name"] or request.user.first_name
        prefill["last_name"] = prefill["last_name"] or request.user.last_name
        prefill["phone"] = prefill["phone"] or request.user.phone
        customer = get_or_create_customer_profile(request.user)
        default_address = customer.addresses.filter(
            is_active=True, is_default_shipping=True).first()
        if default_address:
            prefill.update(
                {
                    "address1": prefill["address1"] or default_address.address1,
                    "address2": prefill["address2"] or default_address.address2,
                    "city": prefill["city"] or default_address.city,
                    "state": prefill["state"] or default_address.state,
                    "postal_code": prefill["postal_code"] or default_address.postal_code,
                    "country_code": prefill["country_code"] or default_address.country_code,
                }
            )
    return prefill


def _next_order_sequence() -> int:
    current = Order.objects.aggregate(max_sequence=Max(
        "order_number_sequence")).get("max_sequence") or 0
    return current + 1


def get_customer_order_queryset(request):
    if not getattr(request.user, "is_authenticated", False):
        return Order.objects.none()
    customer = get_or_create_customer_profile(request.user)
    return (
        Order.objects.filter(Q(customer=customer) | Q(
            customer_email__iexact=request.user.email))
        .prefetch_related("items", "addresses", "status_history")
        .order_by("-placed_at")
        .distinct()
    )


def _create_order_tax_rows(order: Order) -> None:
    if quantize_money(order.total_tax) <= 0:
        return
    OrderTax.objects.create(
        order=order,
        title="Tax",
        rate=Decimal("0.00"),
        amount=quantize_money(order.total_tax),
        is_included_in_price=False,
        jurisdiction="",
        tax_authority="",
    )


def _build_flash_sale_consumption_map(order: Order) -> dict[str, int]:
    consumption: dict[str, int] = {}
    for item in order.items.all():
        pricing_snapshot = (item.custom_properties or {}).get("pricing_snapshot", {})
        flash_sale_item_id = str(pricing_snapshot.get("flash_sale_item_id") or "").strip()
        if not flash_sale_item_id:
            continue
        consumption[flash_sale_item_id] = consumption.get(flash_sale_item_id, 0) + int(item.quantity or 0)
    return consumption


def _increment_automatic_discount_usage(order: Order) -> list[str]:
    applied_ids: list[str] = []
    for order_discount in order.discounts.filter(discount_type=OrderDiscount.DiscountType.AUTOMATIC):
        if not order_discount.discount_id:
            continue
        discount_id = str(order_discount.discount_id)
        AutomaticDiscount.objects.filter(pk=discount_id).update(usage_count=F("usage_count") + 1)
        applied_ids.append(discount_id)
    return applied_ids


def _decrement_automatic_discount_usage(order: Order) -> list[str]:
    reversed_ids: list[str] = []
    for order_discount in order.discounts.filter(discount_type=OrderDiscount.DiscountType.AUTOMATIC):
        if not order_discount.discount_id:
            continue
        discount = AutomaticDiscount.objects.filter(pk=order_discount.discount_id).first()
        if not discount:
            continue
        discount.usage_count = max(0, int(discount.usage_count or 0) - 1)
        discount.save(update_fields=["usage_count", "updated_at"])
        reversed_ids.append(str(order_discount.discount_id))
    return reversed_ids


def _increment_flash_sale_units_for_order(order: Order) -> dict[str, int]:
    consumption = _build_flash_sale_consumption_map(order)
    if not consumption:
        return {}

    applied: dict[str, int] = {}
    for flash_sale_item_id, quantity in consumption.items():
        flash_item = FlashSaleItem.objects.filter(pk=flash_sale_item_id).first() if FlashSaleItem is not None else None
        if not flash_item:
            continue
        flash_item.increment_units_sold(quantity)
        applied[flash_sale_item_id] = quantity
    return applied


def _decrement_flash_sale_units_for_order(order: Order) -> dict[str, int]:
    consumption = _build_flash_sale_consumption_map(order)
    if not consumption or FlashSaleItem is None:
        return {}

    reversed_items: dict[str, int] = {}
    for flash_sale_item_id, quantity in consumption.items():
        flash_item = FlashSaleItem.objects.filter(pk=flash_sale_item_id).first()
        if not flash_item:
            continue
        flash_item.units_sold = max(0, int(flash_item.units_sold or 0) - int(quantity or 0))
        flash_item.save(update_fields=["units_sold", "updated_at"])
        reversed_items[flash_sale_item_id] = quantity
    return reversed_items


def _record_partner_commissions(order: Order, applied_discounts: list[dict[str, Any]], code_usage=None) -> list[str]:
    if PromotionCommissionLedger is None:
        return []

    recorded: list[str] = []
    for row in applied_discounts:
        discount_id = row.get("discount_id")
        if not discount_id:
            continue
        source = None
        if row.get("discount_type") == "code":
            source = DiscountCode.objects.select_related("attributed_partner").filter(pk=discount_id).first()
        elif row.get("discount_type") == "automatic":
            source = AutomaticDiscount.objects.select_related("attributed_partner").filter(pk=discount_id).first()
        partner = getattr(source, "attributed_partner", None)
        if partner is None:
            continue
        commission_rate = Decimal(str(partner.commission_rate_percentage or 0)) / Decimal("100")
        revenue = quantize_money(order.total_price)
        discount_value = quantize_money(row.get("amount"))
        commission_amount = quantize_money(revenue * commission_rate)
        entry, _ = PromotionCommissionLedger.objects.get_or_create(
            partner=partner,
            order_id=order.id,
            discount_code=source if isinstance(source, DiscountCode) else None,
            defaults={
                "usage": code_usage if isinstance(source, DiscountCode) else None,
                "order_number": order.order_number,
                "revenue_attributed": revenue,
                "discount_value": discount_value,
                "commission_amount": commission_amount,
                "currency": order.currency,
                "metadata": {
                    "discount_type": row.get("discount_type"),
                    "description": row.get("description", ""),
                },
            },
        )
        recorded.append(str(entry.id))
    return recorded


def _reverse_partner_commissions(order: Order) -> list[str]:
    if PromotionCommissionLedger is None:
        return []
    entries = list(PromotionCommissionLedger.objects.filter(order_id=order.id).exclude(status=PromotionCommissionLedger.LedgerStatus.REVERSED))
    if not entries:
        return []
    reversed_ids: list[str] = []
    for entry in entries:
        entry.status = PromotionCommissionLedger.LedgerStatus.REVERSED
        entry.metadata = dict(entry.metadata or {})
        entry.metadata["reversed_at"] = timezone.now().isoformat()
        entry.save(update_fields=["status", "metadata", "updated_at"])
        reversed_ids.append(str(entry.id))
    return reversed_ids


def _record_bundle_ledgers(order: Order, bundle_ledgers: list[dict[str, Any]], *, customer=None) -> list[str]:
    if BundleOrderLedger is None:
        return []
    saved_ids: list[str] = []
    for payload in bundle_ledgers:
        bundle_id = payload.get("bundle_id")
        if not bundle_id:
            continue
        ledger, _ = BundleOrderLedger.objects.update_or_create(
            bundle_id=bundle_id,
            order_id=order.id,
            defaults={
                "order_number": order.order_number,
                "customer": customer,
                "quantity": max(1, int(payload.get("quantity") or 1)),
                "bundle_discount_amount": quantize_money(payload.get("discount_amount")),
                "revenue_attributed": quantize_money(payload.get("revenue_attributed")),
                "metadata": {
                    "item_ids": list(payload.get("item_ids") or []),
                    "offer_type": payload.get("offer_type", ""),
                    "title": payload.get("title", ""),
                },
            },
        )
        saved_ids.append(str(ledger.id))
    return saved_ids


def _reverse_bundle_ledgers(order: Order) -> list[str]:
    if BundleOrderLedger is None:
        return []
    ledgers = list(BundleOrderLedger.objects.filter(order_id=order.id))
    reversed_ids: list[str] = []
    for ledger in ledgers:
        metadata = dict(ledger.metadata or {})
        if metadata.get("reversed_at"):
            continue
        metadata["reversed_at"] = timezone.now().isoformat()
        metadata["reversed_order_status"] = order.status
        ledger.metadata = metadata
        ledger.save(update_fields=["metadata", "updated_at"])
        reversed_ids.append(str(ledger.id))
    return reversed_ids


def _mark_issued_code_redeemed(discount_code_id: str, *, customer=None) -> list[str]:
    if IssuedDiscountCode is None:
        return []
    queryset = IssuedDiscountCode.objects.filter(
        discount_code_id=discount_code_id,
        status__in=[IssuedDiscountCode.Status.PENDING, IssuedDiscountCode.Status.DELIVERED],
    )
    if customer is not None:
        queryset = queryset.filter(customer=customer)
    issued_codes = list(queryset.order_by("-created_at"))
    marked_ids: list[str] = []
    for issued_code in issued_codes:
        issued_code.status = IssuedDiscountCode.Status.REDEEMED
        issued_code.redeemed_at = timezone.now()
        payload = dict(issued_code.delivery_payload or {})
        payload["redeemed_at"] = issued_code.redeemed_at.isoformat()
        issued_code.delivery_payload = payload
        issued_code.save(update_fields=["status", "redeemed_at", "delivery_payload", "updated_at"])
        marked_ids.append(str(issued_code.id))
    return marked_ids


def _restore_redeemed_issued_codes(order: Order, *, reason: str = "") -> list[str]:
    if IssuedDiscountCode is None:
        return []
    restored_ids: list[str] = []
    code_rows = [row for row in order.discounts.filter(discount_type=OrderDiscount.DiscountType.CODE) if row.discount_id]
    for row in code_rows:
        queryset = IssuedDiscountCode.objects.filter(
            discount_code_id=row.discount_id,
            status=IssuedDiscountCode.Status.REDEEMED,
        )
        if order.customer_id:
            queryset = queryset.filter(customer=order.customer)
        for issued_code in queryset.order_by("-updated_at"):
            payload = dict(issued_code.delivery_payload or {})
            payload["reversal_order_id"] = str(order.id)
            payload["reversal_order_number"] = order.order_number
            payload["reversal_reason"] = reason or order.cancellation_reason or ""
            issued_code.status = IssuedDiscountCode.Status.DELIVERED
            issued_code.redeemed_at = None
            issued_code.delivery_payload = payload
            issued_code.save(update_fields=["status", "redeemed_at", "delivery_payload", "updated_at"])
            restored_ids.append(str(issued_code.id))
    return restored_ids


def reverse_order_pricing_effects(order: Order, reason: str = "") -> bool:
    metadata = dict(order.metafields or {})
    pricing_effects = dict(metadata.get("pricing_effects") or {})
    if pricing_effects.get("reversed_at"):
        return False

    reversed_usage_count = reverse_discount_usage_for_order(order, reason=reason)
    reversed_automatic_ids = _decrement_automatic_discount_usage(order)
    reversed_flash_items = _decrement_flash_sale_units_for_order(order)
    reversed_bundle_ledgers = _reverse_bundle_ledgers(order)
    reversed_commission_ids = _reverse_partner_commissions(order)
    restored_issued_codes = _restore_redeemed_issued_codes(order, reason=reason)

    pricing_effects.update(
        {
            "reversed_at": timezone.now().isoformat(),
            "reversal_reason": (reason or "")[:255],
            "reversed_discount_usage_count": reversed_usage_count,
            "reversed_automatic_discount_ids": reversed_automatic_ids,
            "reversed_flash_sale_items": reversed_flash_items,
            "reversed_bundle_ledger_ids": reversed_bundle_ledgers,
            "reversed_commission_ids": reversed_commission_ids,
            "restored_issued_code_ids": restored_issued_codes,
        }
    )
    metadata["pricing_effects"] = pricing_effects
    order.metafields = metadata
    order.save(update_fields=["metafields", "updated_at"])
    return True


@transaction.atomic
def create_order_from_checkout(request) -> Order:
    cart = get_or_create_cart(request)
    if cart.is_empty:
        raise ValueError("Your cart is empty.")

    checkout_state = get_checkout_state(request)
    if not checkout_state.get("first_name") or not checkout_state.get("address1"):
        raise ValueError("Checkout information is incomplete.")
    if not checkout_state.get("shipping_method"):
        raise ValueError("Select a shipping method before placing the order.")
    if not checkout_state.get("payment_method"):
        raise ValueError("Select a payment method before placing the order.")

    shipping_methods = {
        method["code"]: method for method in get_shipping_methods(request, cart)}
    selected_shipping = shipping_methods.get(checkout_state["shipping_method"])
    if selected_shipping is None:
        raise ValueError("Selected shipping method is no longer available.")

    cart.shipping_total = quantize_money(selected_shipping["amount"])
    recalculate_cart(cart)
    promo_context = get_promo_context(request)

    customer = get_or_create_customer_profile(request.user) if getattr(
        request.user, "is_authenticated", False) else None
    discount_evaluation = _evaluate_all_cart_promotions(
        cart,
        customer=customer,
        cart_items=_cart_items_for_discount_engine(cart),
        subtotal=quantize_money(cart.subtotal),
        shipping_total=quantize_money(selected_shipping["amount"]),
        currency_code=cart.currency or "USD",
        ip_address=get_client_ip(request),
    )
    if not discount_evaluation["valid"]:
        raise ValueError(discount_evaluation["message"] or "The active discount could not be validated at checkout.")

    line_allocation_map = {
        allocation["order_item_id"]: allocation
        for allocation in discount_evaluation["line_allocations"]
    }
    applied_discounts = list(discount_evaluation["applied_discounts"])
    order_sequence = _next_order_sequence()
    payment_method = checkout_state["payment_method"]

    order = Order.objects.create(
        order_number=f"ORD-{order_sequence:06d}",
        order_number_sequence=order_sequence,
        customer=customer,
        cart_id=cart.id,
        currency=cart.currency or "USD",
        customer_email=checkout_state.get(
            "email") or cart.email or getattr(request.user, "email", ""),
        customer_phone=checkout_state.get("phone", ""),
        customer_name=f'{checkout_state.get("first_name", "")} {checkout_state.get("last_name", "")}'.strip(
        ),
        status=Order.OrderStatus.PENDING,
        financial_status=Order.FinancialStatus.PENDING,
        fulfillment_status=Order.FulfillmentStatus.UNFULFILLED,
        source=Order.OrderSource.WEB,
        subtotal_price=cart.subtotal,
        total_discounts=cart.discount_total,
        total_shipping=cart.shipping_total,
        total_tax=cart.tax_total,
        total_price=cart.grand_total,
        total_outstanding=cart.grand_total,
        total_paid=Decimal("0.00"),
        customer_note=checkout_state.get("delivery_instructions", ""),
        shipping_method_name=selected_shipping["label"],
        ip_address=get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
        buyer_accepts_marketing=bool(checkout_state.get("marketing_opt_in")),
        utm_source=promo_context.get("utm_source", "") or cart.utm_source,
        utm_medium=promo_context.get("utm_medium", "") or cart.utm_medium,
        utm_campaign=promo_context.get("utm_campaign", "") or cart.utm_campaign,
        referrer_url=promo_context.get("referrer_url", "") or cart.referrer_url,
        metafields={
            "payment_method": payment_method,
            "payment_state": "pending",
            "checkout_schema": get_tenant_key(request),
            "checkout_token": cart.checkout_token,
            "promo_context": promo_context,
            "pricing_effects": {
                "accounted_at": "",
                "reversed_at": "",
                "applied_discounts": [],
                "automatic_discount_ids": [],
                "flash_sale_items": {},
                "discount_usage_recorded_for_code": "",
                "warnings": discount_evaluation.get("warnings", []),
            },
        },
    )

    OrderAddress.objects.create(
        order=order,
        address_type=OrderAddress.AddressType.SHIPPING,
        first_name=checkout_state["first_name"],
        last_name=checkout_state["last_name"],
        company=checkout_state.get("company", ""),
        address_line1=checkout_state["address1"],
        address_line2=checkout_state.get("address2", ""),
        city=checkout_state["city"],
        state=checkout_state.get("state", ""),
        postal_code=checkout_state.get("postal_code", ""),
        country=checkout_state.get("country_code", "NG"),
        country_name=checkout_state.get("country_code", "NG"),
        phone=checkout_state.get("phone", ""),
        email=checkout_state.get("email") or cart.email,
    )
    OrderAddress.objects.create(
        order=order,
        address_type=OrderAddress.AddressType.BILLING,
        first_name=checkout_state["first_name"],
        last_name=checkout_state["last_name"],
        company=checkout_state.get("company", ""),
        address_line1=checkout_state["address1"],
        address_line2=checkout_state.get("address2", ""),
        city=checkout_state["city"],
        state=checkout_state.get("state", ""),
        postal_code=checkout_state.get("postal_code", ""),
        country=checkout_state.get("country_code", "NG"),
        country_name=checkout_state.get("country_code", "NG"),
        phone=checkout_state.get("phone", ""),
        email=checkout_state.get("email") or cart.email,
    )

    for item in cart.items.select_related("variant__product"):
        variant = item.variant
        product = variant.product if variant else None
        allocation = line_allocation_map.get(str(item.id), {})
        unit_discount = quantize_money(allocation.get("unit_discount"))
        total_discount = quantize_money(allocation.get("line_discount"))
        line_subtotal = quantize_money((item.unit_price * item.quantity) - total_discount)
        line_total = quantize_money(line_subtotal)
        custom_properties = dict(item.custom_properties or {})
        custom_properties["discount_sources"] = allocation.get("sources", [])
        applied_discount_ids = [
            source["discount_id"]
            for source in allocation.get("sources", [])
            if source.get("discount_id")
        ]
        OrderItem.objects.create(
            order=order,
            variant=variant,
            quantity=item.quantity,
            product_id_snapshot=product.id if product else None,
            variant_id_snapshot=variant.id if variant else None,
            product_title=item.product_title or (
                product.name if product else ""),
            variant_title=item.variant_title,
            sku=item.sku or (variant.sku if variant else ""),
            product_image_url=item.product_image_url,
            unit_price=item.unit_price,
            compare_at_price=item.compare_at_price,
            unit_discount=unit_discount,
            unit_tax=Decimal("0.00"),
            tax_rate=Decimal("0.00"),
            total_discount=total_discount,
            total_tax=Decimal("0.00"),
            subtotal=line_subtotal,
            total=line_total,
            requires_shipping=item.requires_shipping,
            custom_properties=custom_properties,
            applied_discount_ids=applied_discount_ids,
        )

    for row in applied_discounts:
        OrderDiscount.objects.create(
            order=order,
            discount_type=(
                OrderDiscount.DiscountType.CODE
                if row["discount_type"] == "code"
                else OrderDiscount.DiscountType.BUNDLE
                if row["discount_type"] == "bundle"
                else OrderDiscount.DiscountType.AUTOMATIC
            ),
            code=row.get("code", ""),
            description=row.get("description", ""),
            discount_id=row.get("discount_id") or None,
            allocation_method=row.get("allocation_method") or OrderDiscount.AllocationMethod.ACROSS,
            amount=quantize_money(row.get("amount")),
            is_percentage=bool(row.get("is_percentage")),
            percentage_value=row.get("percentage_value"),
        )

    _create_order_tax_rows(order)

    code_discount_id = ""
    code_discount_amount = Decimal("0.00")
    code_usage = None
    redeemed_issued_code_ids: list[str] = []
    for row in applied_discounts:
        if row["discount_type"] != "code" or not row.get("discount_id"):
            continue
        code_discount_id = str(row["discount_id"])
        code_discount_amount = quantize_money(row.get("amount"))
        code_usage = record_discount_usage(
            discount_code_id=code_discount_id,
            order_id=str(order.id),
            order_number=order.order_number,
            discount_amount=code_discount_amount,
            order_subtotal=quantize_money(order.subtotal_price),
            customer=customer,
            customer_email=order.customer_email,
            currency=order.currency,
            ip_address=order.ip_address or "",
            user_agent=order.user_agent or "",
        )
        discount_obj = DiscountCode.objects.filter(pk=code_discount_id).first()
        if discount_obj is not None:
            mark_discount_experiment_redeemed(
                discount_code=discount_obj,
                order=order,
                customer=customer,
                session_key=cart.session_key,
            )
        redeemed_issued_code_ids = _mark_issued_code_redeemed(
            code_discount_id,
            customer=customer,
        )
        break

    automatic_discount_ids = _increment_automatic_discount_usage(order)
    flash_sale_items = _increment_flash_sale_units_for_order(order)
    bundle_ledger_ids = _record_bundle_ledgers(
        order,
        discount_evaluation.get("bundle_ledgers", []),
        customer=customer,
    )
    commission_entry_ids = _record_partner_commissions(order, applied_discounts, code_usage=code_usage)

    metafields = dict(order.metafields or {})
    pricing_effects = dict(metafields.get("pricing_effects") or {})
    pricing_effects.update(
        {
            "accounted_at": timezone.now().isoformat(),
            "applied_discounts": applied_discounts,
            "automatic_discount_ids": automatic_discount_ids,
            "flash_sale_items": flash_sale_items,
            "bundle_ledger_ids": bundle_ledger_ids,
            "discount_usage_recorded_for_code": code_discount_id,
            "discount_usage_amount": str(code_discount_amount),
            "redeemed_issued_code_ids": redeemed_issued_code_ids,
            "commission_entry_ids": commission_entry_ids,
        }
    )
    metafields["pricing_effects"] = pricing_effects
    order.metafields = metafields
    order.save(update_fields=["metafields", "updated_at"])

    target_status = Order.OrderStatus.ON_HOLD if payment_method == "bank_transfer" else Order.OrderStatus.CONFIRMED
    order.transition_status(
        target_status, note="Checkout completed", source="checkout")
    request.session[tenant_session_key(request, "guest_order_ids")] = list(
        dict.fromkeys(
            [str(order.id), *request.session.get(tenant_session_key(request, "guest_order_ids"), [])])
    )[:10]
    request.session.modified = True
    cart.mark_converted(order.id)
    clear_checkout_state(request)
    clear_promo_context(request)
    return order


def update_order_payment_state(order: Order, status: str, reference: str = "", payload: dict[str, Any] | None = None) -> Order:
    normalized_status = (status or "").strip().lower()
    metadata = dict(order.metafields or {})
    if reference:
        metadata["payment_reference"] = reference
    if payload:
        metadata["payment_payload"] = payload

    success_states = {"success", "succeeded", "paid", "completed"}
    failure_states = {"failed", "failure", "cancelled", "voided"}
    reversal_states = {"cancelled", "voided"}

    if normalized_status in success_states and order.financial_status != Order.FinancialStatus.PAID:
        order.financial_status = Order.FinancialStatus.PAID
        order.total_paid = order.total_price
        order.total_outstanding = Decimal("0.00")
        metadata["payment_state"] = "paid"
        order.metafields = metadata
        order.save(update_fields=["financial_status", "total_paid",
                   "total_outstanding", "metafields", "updated_at"])
        if order.status in {Order.OrderStatus.PENDING, Order.OrderStatus.ON_HOLD}:
            order.transition_status(
                Order.OrderStatus.PROCESSING, note="Payment confirmed", source="payment_gateway")
        return order

    if normalized_status in failure_states and order.financial_status != Order.FinancialStatus.FAILED:
        if normalized_status in reversal_states:
            reverse_order_pricing_effects(order, reason=f"payment_{normalized_status}")
            if order.is_cancellable:
                try:
                    order.cancel(reason=f"payment_{normalized_status}", note="Payment was cancelled or voided.")
                except Exception:
                    logger.debug("Unable to cancel order %s during %s reversal.", order.order_number, normalized_status)
        order.financial_status = Order.FinancialStatus.FAILED
        metadata["payment_state"] = "failed"
        order.metafields = metadata
        order.save(update_fields=["financial_status",
                   "metafields", "updated_at"])
        return order

    metadata["payment_state"] = metadata.get(
        "payment_state", normalized_status or "pending")
    order.metafields = metadata
    order.save(update_fields=["metafields", "updated_at"])
    return order


def get_order_for_request(request, order_id) -> Order | None:
    queryset = Order.objects.prefetch_related(
        "items", "addresses", "status_history").all()
    if getattr(request.user, "is_authenticated", False):
        return queryset.filter(
            Q(id=order_id)
            & (Q(customer=get_or_create_customer_profile(request.user)) | Q(customer_email__iexact=request.user.email))
        ).distinct().first()

    guest_order_ids = request.session.get(
        tenant_session_key(request, "guest_order_ids"), [])
    if str(order_id) not in guest_order_ids:
        return None
    return queryset.filter(id=order_id).first()


def render_storefront(
    request,
    template_name: str,
    context: dict[str, Any] | None = None,
    *,
    page_title: str = "",
    page_description: str = "",
    status: int = 200,
    canonical: str = "",
):
    store_settings = get_store_settings_cached(request)
    header_settings = get_header_settings_cached(request)
    footer_settings = get_footer_settings_cached(request)
    homepage_layout = get_homepage_layout_cached(request)
    checkout_settings = get_checkout_settings_cached(request)
    product_display_settings = get_product_display_settings_cached(request)
    search_settings = get_search_settings_cached(request)
    social_links = get_social_links_cached(request)
    active_flash_sale = get_active_flash_sale(request)
    active_flash_sale_payload = serialize_flash_sale(active_flash_sale)
    cart_summary = get_cart_summary(request)
    theme_tokens = build_theme_tokens(request)
    social_platforms = get_social_platforms(request)

    shop = get_shop_context(request)
    seo_title = page_title or shop["name"]
    seo = build_seo_context(
        seo_title,
        page_description or getattr(
            store_settings, "meta_description", "") or shop["description"],
        canonical=canonical or request.build_absolute_uri(request.path),
    )

    base_context = {
        "shop": shop,
        "store_settings": store_settings,
        "site_settings": store_settings,
        "header_settings": header_settings,
        "footer_settings": footer_settings,
        "homepage_layout": homepage_layout,
        "checkout_settings": checkout_settings,
        "product_display_settings": product_display_settings,
        "search_settings": search_settings,
        "social_links": social_links,
        "social_platforms": social_platforms,
        "theme_tokens": theme_tokens,
        "navigation_links": get_navigation_links(request),
        "utility_navigation": get_utility_navigation(request),
        "navigation_categories": get_navigation_categories(request, limit=12),
        "footer_link_groups": get_footer_link_groups(request),
        "account_navigation": get_account_navigation(request),
        "mini_footer_links": get_mini_footer_links(request),
        "top_categories": get_top_categories(request),
        "active_flash_sale": active_flash_sale,
        "active_flash_sale_payload": active_flash_sale_payload,
        "active_discount_campaigns": get_active_discount_campaigns(request),
        "featured_brands": get_featured_brands(request),
        "service_highlights": get_service_highlights(request),
        "store_editorial_cards": get_store_editorial_cards(request),
        "storefront_announcement": get_storefront_announcement(request),
        "cart_summary": cart_summary,
        "wishlist_count": len(get_wishlist_products(request)),
        "compare_count": len(get_compare_products(request)),
        "recently_viewed_count": len(get_recently_viewed_products(request)),
        "storefront_features": get_feature_flags(request),
        "seo": seo,
        "page_title": seo_title,
        "page_description": page_description, "search_query": "",
    }
    if context:
        base_context.update(context)
    response = render_theme_template(request, template_name, base_context)
    response.status_code = status
    return response


def render_info_page(
    request,
    *,
    title: str,
    headline: str | None = None,
    body: str,
    form=None,
    form_action: str = "",
    breadcrumbs: list[dict[str, str]] | None = None,
    extra_context: dict[str, Any] | None = None,
    status: int = 200,
):
    context = {
        "headline": headline or title,
        "body": body,
        "form": form,
        "form_action": form_action,
        "breadcrumbs": breadcrumbs or [{"label": "Home", "url": safe_reverse("home:index")}, {"label": title, "url": ""}],
    }
    if extra_context:
        context.update(extra_context)
    return render_storefront(
        request,
        "shared/info_page.html",
        context,
        page_title=title,
        page_description=body,
        status=status,
    )
