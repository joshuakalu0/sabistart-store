from django.core.management import call_command
from django.test import TestCase

from system.feature_marketplace.models import BillingCycle, BundleItem, Coupon, FeatureBundle, FeatureDefinition, FeaturePrice


class FeatureCatalogSeedCommandTests(TestCase):
    def test_realistic_plus_seed_is_idempotent_and_rich(self):
        call_command("seed_feature_catalog", profile="realistic-plus", verbosity=0)

        first_counts = {
            "features": FeatureDefinition.objects.count(),
            "prices": FeaturePrice.objects.count(),
            "bundles": FeatureBundle.objects.count(),
            "bundle_items": BundleItem.objects.count(),
            "coupons": Coupon.objects.count(),
        }

        self.assertGreaterEqual(first_counts["features"], 16)
        self.assertGreaterEqual(first_counts["bundles"], 6)
        self.assertGreaterEqual(first_counts["coupons"], 3)

        analytics = FeatureDefinition.objects.get(code="advanced_analytics")
        self.assertTrue(
            FeaturePrice.objects.filter(
                feature=analytics,
                billing_cycle=BillingCycle.MONTHLY,
                currency="NGN",
                is_active=True,
            ).exists()
        )
        self.assertTrue(
            FeaturePrice.objects.filter(
                feature=analytics,
                billing_cycle=BillingCycle.ANNUAL,
                currency="NGN",
                is_active=True,
            ).exists()
        )

        booster = FeatureBundle.objects.get(slug="ai-credit-booster")
        booster_item = booster.items.get(feature__code="ai_credits")
        self.assertEqual(booster_item.quantity_override, 3500)

        max_products = FeatureDefinition.objects.get(code="max_products")
        pos_locations = FeatureDefinition.objects.get(code="max_pos_locations")
        custom_domains = FeatureDefinition.objects.get(code="max_custom_domains")
        self.assertEqual(max_products.default_limit_value, 50)
        self.assertEqual(
            FeaturePrice.objects.get(feature=pos_locations, billing_cycle=BillingCycle.MONTHLY, currency="NGN").limit_increment,
            1,
        )
        self.assertFalse(
            FeaturePrice.objects.filter(feature=pos_locations, billing_cycle=BillingCycle.ANNUAL, currency="NGN", is_active=True).exists()
        )
        self.assertEqual(custom_domains.default_limit_value, 0)
        self.assertEqual(
            FeaturePrice.objects.get(feature=custom_domains, billing_cycle=BillingCycle.ANNUAL, currency="NGN").limit_increment,
            1,
        )
        self.assertTrue(FeatureBundle.objects.filter(slug="operations-plus").exists())
        self.assertTrue(FeatureBundle.objects.filter(slug="storefront-plus").exists())
        self.assertTrue(FeatureBundle.objects.filter(slug="integrations-plus").exists())

        call_command("seed_feature_catalog", profile="realistic-plus", verbosity=0)

        second_counts = {
            "features": FeatureDefinition.objects.count(),
            "prices": FeaturePrice.objects.count(),
            "bundles": FeatureBundle.objects.count(),
            "bundle_items": BundleItem.objects.count(),
            "coupons": Coupon.objects.count(),
        }

        self.assertEqual(first_counts, second_counts)
