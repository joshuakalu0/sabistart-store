from __future__ import annotations

from dataclasses import dataclass

from django.db.utils import OperationalError, ProgrammingError


PREMIUM_SETTING_FEATURES = {
    "enable_reviews": "reviews",
    "enable_wishlist": "wishlist",
    "enable_compare": "compare",
    "enable_gift_cards": "gift_cards",
    "enable_subscriptions": "subscriptions",
    "enable_social_login": "social_login",
    "enable_discount_codes": "discount_codes",
    "enable_live_chat": "live_chat",
    "enable_api_access": "api_access",
    "enable_webhooks": "webhooks",
}

FEATURE_SETTING_FIELDS = {
    feature_code: field_name
    for field_name, feature_code in PREMIUM_SETTING_FEATURES.items()
}

LIMIT_FEATURE_CODES = (
    "max_products",
    "staff_management",
    "max_pos_locations",
    "max_custom_domains",
)

USAGE_SNAPSHOT_FEATURE_CODES = LIMIT_FEATURE_CODES + ("ai_credits",)

NAVIGATION_FEATURE_CODES = {
    "pos": "max_pos_locations",
    "domains": "max_custom_domains",
}


@dataclass(frozen=True)
class ReservedFeaturePattern:
    feature_code: str
    feature_type: str
    note: str


FUTURE_RESERVED_FEATURES = (
    ReservedFeaturePattern(
        feature_code="product_scraper",
        feature_type="boolean",
        note="Module unlock for future catalog scraping/import tooling.",
    ),
    ReservedFeaturePattern(
        feature_code="import_credits",
        feature_type="usage",
        note="Usage credits for future scraping/import jobs.",
    ),
    ReservedFeaturePattern(
        feature_code="scrape_jobs",
        feature_type="limit",
        note="Quota-based future import job allocation.",
    ),
)


def _safe_count(func) -> int:
    try:
        return int(func())
    except (OperationalError, ProgrammingError):
        return 0
    except Exception:
        return 0


def count_products() -> int:
    from public.product.models import Product

    return _safe_count(lambda: Product.objects.count())


def count_staff() -> int:
    from public.userauth.models import StoreStaff

    return _safe_count(
        lambda: StoreStaff.objects.filter(status=StoreStaff.StaffStatus.ACTIVE).count()
    )


def count_pos_locations() -> int:
    from dashboard.pos.models import Store

    return _safe_count(lambda: Store.objects.filter(is_active=True, is_deleted=False).count())


def count_custom_domains() -> int:
    from dashboard.domain.models import CustomDomain

    return _safe_count(
        lambda: CustomDomain.objects.exclude(status=CustomDomain.Status.REMOVED).count()
    )


RESOURCE_COUNTERS = {
    "max_products": count_products,
    "staff_management": count_staff,
    "max_pos_locations": count_pos_locations,
    "max_custom_domains": count_custom_domains,
}
