from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand

from system.feature_marketplace.catalog_registry import (
    CATALOG_PROFILES,
    STALE_PLAN_BUNDLE_SLUGS,
    STALE_PLAN_CAMPAIGN_NAMES,
)
from system.feature_marketplace.models import (
    BundleItem,
    Coupon,
    DiscountCampaign,
    FeatureBundle,
    FeatureCategory,
    FeatureDefinition,
    FeaturePrice,
)


class Command(BaseCommand):
    help = "Seed the shared feature marketplace catalog with starter or realistic-plus data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile",
            choices=tuple(CATALOG_PROFILES.keys()),
            default="realistic-plus",
            help="Choose the seed profile to apply. Defaults to realistic-plus.",
        )

    def handle(self, *args, **options):
        profile_name = options["profile"]
        profile = CATALOG_PROFILES[profile_name]
        categories: dict[str, FeatureCategory] = {}
        features: dict[str, FeatureDefinition] = {}

        for spec in profile["features"]:
            category = self._get_or_create_category(categories, spec)
            feature = self._upsert_feature(spec["feature"], category)
            features[feature.code] = feature
            self._upsert_prices(feature, spec["prices"])

        for spec in profile["bundles"]:
            self._upsert_bundle(spec, features)
        self._deactivate_stale_bundles(profile["bundles"])

        for spec in profile["campaigns"]:
            self._upsert_campaign(spec)
        self._deactivate_stale_campaigns(profile["campaigns"])

        for spec in profile["coupons"]:
            self._upsert_coupon(spec)

        self.stdout.write(
            self.style.SUCCESS(
                f"Feature marketplace catalog seeded successfully with the '{profile_name}' profile."
            )
        )

    def _get_or_create_category(self, category_cache: dict[str, FeatureCategory], spec: dict) -> FeatureCategory:
        slug = spec["slug"]
        if slug in category_cache:
            return category_cache[slug]
        category, _ = FeatureCategory.objects.update_or_create(
            slug=slug,
            defaults={
                "name": spec["category"],
                "description": spec.get("category_description", spec["category"]),
                "icon": spec.get("category_icon", ""),
                "is_active": True,
            },
        )
        category_cache[slug] = category
        return category

    def _upsert_feature(self, feature_spec: dict, category: FeatureCategory) -> FeatureDefinition:
        feature, _ = FeatureDefinition.objects.update_or_create(
            code=feature_spec["code"],
            defaults={
                "category": category,
                "name": feature_spec["name"],
                "short_description": feature_spec.get("short_description", feature_spec["name"]),
                "description": feature_spec.get("description", feature_spec["name"]),
                "feature_type": feature_spec["feature_type"],
                "default_boolean_value": feature_spec.get("default_boolean_value", False),
                "default_limit_value": feature_spec.get("default_limit_value", 0),
                "default_usage_value": feature_spec.get("default_usage_value", 0),
                "unit_label": feature_spec.get("unit_label", ""),
                "badge_label": feature_spec.get("badge_label", ""),
                "icon": feature_spec.get("icon", ""),
                "store_setting_key": feature_spec.get("store_setting_key", ""),
                "sidebar_key": feature_spec.get("sidebar_key", ""),
                "storefront_flag": feature_spec.get("storefront_flag", ""),
                "is_active": feature_spec.get("is_active", True),
                "is_purchasable": feature_spec.get("is_purchasable", True),
                "is_featured": feature_spec.get("is_featured", False),
                "display_order": feature_spec.get("display_order", 0),
                "metadata": feature_spec.get("metadata", {}),
            },
        )
        return feature

    def _upsert_prices(self, feature: FeatureDefinition, price_specs: list[dict]) -> None:
        active_keys = set()
        for spec in price_specs:
            active_keys.add((spec["currency"], spec["billing_cycle"]))
            FeaturePrice.objects.update_or_create(
                feature=feature,
                currency=spec["currency"],
                billing_cycle=spec["billing_cycle"],
                defaults={
                    "amount": Decimal(spec["amount"]),
                    "credits_included": spec.get("credits_included", 0),
                    "limit_increment": spec.get("limit_increment", 0),
                    "display_name": spec.get("display_name", ""),
                    "is_active": spec.get("is_active", True),
                },
            )
        for stale in feature.prices.all():
            key = (stale.currency, stale.billing_cycle)
            if key in active_keys:
                if not stale.is_active:
                    stale.is_active = True
                    stale.save(update_fields=["is_active", "updated_at"])
                continue
            if stale.is_active:
                stale.is_active = False
                stale.save(update_fields=["is_active", "updated_at"])

    def _upsert_bundle(self, bundle_spec: dict, features: dict[str, FeatureDefinition]) -> None:
        bundle, _ = FeatureBundle.objects.update_or_create(
            slug=bundle_spec["slug"],
            defaults={
                "name": bundle_spec["name"],
                "description": bundle_spec["description"],
                "tagline": bundle_spec.get("tagline", ""),
                "price": Decimal(bundle_spec["price"]),
                "currency": bundle_spec["currency"],
                "billing_cycle": bundle_spec["billing_cycle"],
                "discount_percentage": Decimal(bundle_spec.get("discount_percentage", "0.00")),
                "icon": bundle_spec.get("icon", ""),
                "is_active": bundle_spec.get("is_active", True),
                "is_featured": bundle_spec.get("is_featured", False),
                "display_order": bundle_spec.get("display_order", 0),
            },
        )

        seen_codes = set()
        for item_spec in bundle_spec["items"]:
            feature = features[item_spec["code"]]
            seen_codes.add(feature.code)
            BundleItem.objects.update_or_create(
                bundle=bundle,
                feature=feature,
                defaults={
                    "quantity_override": item_spec.get("quantity_override"),
                    "boolean_override": item_spec.get("boolean_override"),
                    "sort_order": item_spec.get("sort_order", 0),
                },
            )

        bundle.items.exclude(feature__code__in=seen_codes).delete()

    def _deactivate_stale_bundles(self, bundle_specs: list[dict]) -> None:
        active_bundle_slugs = {spec["slug"] for spec in bundle_specs}
        FeatureBundle.objects.filter(slug__in=STALE_PLAN_BUNDLE_SLUGS).exclude(
            slug__in=active_bundle_slugs
        ).update(is_active=False)

    def _upsert_campaign(self, campaign_spec: dict) -> None:
        campaign, _ = DiscountCampaign.objects.update_or_create(
            name=campaign_spec["name"],
            defaults={
                "description": campaign_spec.get("description", ""),
                "discount_type": campaign_spec["discount_type"],
                "discount_value": Decimal(campaign_spec["discount_value"]),
                "is_active": campaign_spec.get("is_active", True),
                "max_uses": campaign_spec.get("max_uses"),
            },
        )
        campaign.applicable_features.set(
            FeatureDefinition.objects.filter(code__in=campaign_spec.get("feature_codes", []))
        )
        campaign.applicable_bundles.set(
            FeatureBundle.objects.filter(slug__in=campaign_spec.get("bundle_slugs", []))
        )

    def _deactivate_stale_campaigns(self, campaign_specs: list[dict]) -> None:
        active_campaign_names = {spec["name"] for spec in campaign_specs}
        DiscountCampaign.objects.filter(name__in=STALE_PLAN_CAMPAIGN_NAMES).exclude(
            name__in=active_campaign_names
        ).update(is_active=False)

    def _upsert_coupon(self, coupon_spec: dict) -> None:
        coupon, _ = Coupon.objects.update_or_create(
            code=coupon_spec["code"],
            defaults={
                "description": coupon_spec.get("description", ""),
                "discount_type": coupon_spec["discount_type"],
                "discount_value": Decimal(coupon_spec["discount_value"]),
                "max_uses": coupon_spec.get("max_uses"),
                "max_uses_per_tenant": coupon_spec.get("max_uses_per_tenant", 1),
                "is_active": coupon_spec.get("is_active", True),
            },
        )
        coupon.applicable_features.set(
            FeatureDefinition.objects.filter(code__in=coupon_spec.get("feature_codes", []))
        )
        coupon.applicable_bundles.set(
            FeatureBundle.objects.filter(slug__in=coupon_spec.get("bundle_slugs", []))
        )
