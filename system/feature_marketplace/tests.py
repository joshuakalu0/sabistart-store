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

        starter = FeatureBundle.objects.get(slug="starter-pack-monthly")
        premium = FeatureBundle.objects.get(slug="premium-pack-monthly")
        pro_annual = FeatureBundle.objects.get(slug="pro-pack-annual")
        self.assertEqual(starter.name, "Starter Pack Monthly")
        self.assertEqual(premium.price, 15000)
        self.assertTrue(premium.is_featured)
        self.assertEqual(starter.items.get(feature__code="max_products").quantity_override, 50)
        self.assertEqual(premium.items.get(feature__code="staff_management").quantity_override, 5)
        self.assertEqual(pro_annual.items.get(feature__code="ai_credits").quantity_override, 300000)

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
        self.assertTrue(FeatureBundle.objects.filter(slug="starter-pack-monthly", is_active=True).exists())
        self.assertTrue(FeatureBundle.objects.filter(slug="premium-pack-monthly", is_active=True).exists())
        self.assertTrue(FeatureBundle.objects.filter(slug="pro-pack-monthly", is_active=True).exists())

        call_command("seed_feature_catalog", profile="realistic-plus", verbosity=0)

        second_counts = {
            "features": FeatureDefinition.objects.count(),
            "prices": FeaturePrice.objects.count(),
            "bundles": FeatureBundle.objects.count(),
            "bundle_items": BundleItem.objects.count(),
            "coupons": Coupon.objects.count(),
        }

        self.assertEqual(first_counts, second_counts)
