import uuid
from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.contrib.sessions.middleware import SessionMiddleware
from django.urls import resolve, reverse
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient, TenantRequestFactory
from django_tenants.utils import get_public_schema_name, schema_context

from dashboard.feature_marketplace.views import catalog as marketplace_catalog_view
from dashboard.feature_marketplace.models import (
    CouponRedemption,
    FeaturePurchase,
    FeaturePurchaseItem,
    ResourceQuota,
    TenantEntitlement,
    UsageRecord,
)
from dashboard.feature_marketplace.services import (
    FeatureEntitlementEngine,
    QuotaExceededError,
    activate_purchase,
    create_purchase,
    enforce_quota,
    grandfather_legacy_entitlements,
)
from dashboard.store_settings.forms.StoreSettings import StoreSettingsForm
from dashboard.store_settings.models import StoreSettings
from public.userauth.models import TenantUser
from system.account.models import PlatformUser
from system.feature_marketplace.models import (
    BillingCycle,
    BundleItem,
    Coupon,
    DiscountCampaign,
    FeatureBundle,
    FeatureCategory,
    FeatureDefinition,
    FeaturePrice,
    FeaturePurchaseIndex,
)
from system.feature_marketplace.services import process_marketplace_payment_event
from system.system_pay.models import PaymentGatewayDefinition, PlatformGatewayCredential


class FeatureMarketplaceTenantTestCase(TenantTestCase):
    platform_owner = None

    @classmethod
    def get_test_schema_name(cls):
        if not hasattr(cls, "_test_schema_name"):
            cls._test_schema_name = f"fm_{uuid.uuid4().hex[:18]}"
        return cls._test_schema_name

    @classmethod
    def get_test_tenant_domain(cls):
        return f"{cls.get_test_schema_name()}.tenant.test.com"

    @classmethod
    def setup_tenant(cls, tenant):
        cls.platform_owner, _ = PlatformUser.objects.get_or_create(
            email=f"{cls.__name__.lower()}@example.com",
            defaults={"first_name": "Feature", "last_name": "Owner", "account_status": PlatformUser.AccountStatus.ACTIVE},
        )
        cls.platform_owner.set_password("OwnerPass123!")
        cls.platform_owner.save()
        tenant.owner = cls.platform_owner
        tenant.name = "Feature Test Shop"
        return tenant

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.tenant is not None:
            call_command("migrate_schemas", schema=cls.tenant.schema_name, tenant=True, interactive=False, verbosity=0)
            cls._ensure_public_model_table_exists(FeatureCategory)
            cls._ensure_public_model_table_exists(FeatureDefinition)
            cls._ensure_public_model_table_exists(FeaturePrice)
            cls._ensure_public_model_table_exists(FeatureBundle)
            cls._ensure_public_model_table_exists(BundleItem)
            cls._ensure_public_model_table_exists(DiscountCampaign)
            cls._ensure_public_model_table_exists(Coupon)
            cls._ensure_public_model_table_exists(FeaturePurchaseIndex)
            cls._ensure_public_model_table_exists(PaymentGatewayDefinition)
            cls._ensure_public_model_table_exists(PlatformGatewayCredential)
            for model in (
                TenantUser,
                FeaturePurchase,
                FeaturePurchaseItem,
                TenantEntitlement,
                ResourceQuota,
                UsageRecord,
                CouponRedemption,
            ):
                cls._ensure_tenant_model_table_exists(model)

    @classmethod
    def _ensure_public_model_table_exists(cls, model):
        table_name = model._meta.db_table
        with schema_context(get_public_schema_name()):
            if table_name not in connection.introspection.table_names():
                with connection.schema_editor() as editor:
                    editor.create_model(model)

    @classmethod
    def _ensure_tenant_model_table_exists(cls, model):
        table_name = model._meta.db_table
        with schema_context(cls.tenant.schema_name):
            if table_name not in connection.introspection.table_names():
                with connection.schema_editor() as editor:
                    editor.create_model(model)

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        for model in (
            TenantUser,
            FeaturePurchase,
            FeaturePurchaseItem,
            TenantEntitlement,
            ResourceQuota,
            UsageRecord,
            CouponRedemption,
        ):
            self._ensure_tenant_model_table_exists(model)
        self.client = TenantClient(self.tenant)
        self.prefix = "admin"
        self.user = TenantUser.objects.create_user(
            email="feature-staff@example.com",
            password="StrongPass123!",
            first_name="Feature",
            last_name="Manager",
            user_type=TenantUser.UserType.STAFF,
            is_staff=True,
            account_status=TenantUser.AccountStatus.ACTIVE,
        )
        self.client.force_login(self.user, backend="sabistart.auth_backends.SchemaAwareAuthenticationBackend")


class FeatureMarketplaceRouteTests(FeatureMarketplaceTenantTestCase):
    def test_marketplace_catalog_route_renders(self):
        url = reverse("dashboard:feature_marketplace:catalog", kwargs={"prefix": self.prefix})
        match = resolve(url)
        request = TenantRequestFactory(self.tenant).get(url)
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request.user = self.user
        response = marketplace_catalog_view(request, prefix=self.prefix)

        self.assertEqual(url, "/dashboard/admin/marketplace/catalog/")
        self.assertEqual(match.url_name, "catalog")
        self.assertEqual(match.namespace, "dashboard:feature_marketplace")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Marketplace Catalog")


class FeatureMarketplaceServiceTests(FeatureMarketplaceTenantTestCase):
    def setUp(self):
        super().setUp()
        with schema_context(get_public_schema_name()):
            category, _ = FeatureCategory.objects.get_or_create(name="Analytics", slug="analytics")
            self.feature, _ = FeatureDefinition.objects.update_or_create(
                code="advanced_analytics",
                defaults={
                    "category": category,
                    "name": "Advanced Analytics",
                    "feature_type": "boolean",
                    "is_active": True,
                    "is_purchasable": True,
                },
            )
            FeaturePrice.objects.update_or_create(
                feature=self.feature,
                currency="NGN",
                billing_cycle="monthly",
                defaults={"amount": Decimal("7500.00"), "is_active": True},
            )
            gateway, _ = PaymentGatewayDefinition.objects.update_or_create(
                provider="paystack",
                defaults={
                    "name": "Paystack",
                    "is_enabled": True,
                    "supported_currencies": ["NGN"],
                },
            )
            PlatformGatewayCredential.objects.update_or_create(
                gateway=gateway,
                name="Primary",
                environment="test",
                defaults={
                    "is_active": True,
                    "priority": 10,
                    "secret_key": "sk_test_feature_marketplace",
                },
            )

    def test_create_and_activate_purchase_creates_entitlement_and_public_index(self):
        purchase = create_purchase(
            schema_name=self.tenant.schema_name,
            feature_code="advanced_analytics",
            currency="NGN",
            billing_cycle="monthly",
            quantity=1,
            initiated_by=self.user,
        )

        self.assertEqual(purchase.status, FeaturePurchase.Status.PENDING)
        self.assertTrue(
            FeaturePurchaseIndex.objects.filter(
                purchase_id=purchase.id,
                purchase_reference=purchase.purchase_reference,
                schema_name=self.tenant.schema_name,
            ).exists()
        )

        activate_purchase(purchase, gateway_reference="gw_ref_123", gateway_transaction_id="gw_tx_123")
        purchase.refresh_from_db()

        self.assertEqual(purchase.status, FeaturePurchase.Status.COMPLETED)
        self.assertTrue(
            TenantEntitlement.objects.filter(
                purchase_id=purchase.id,
                feature_code="advanced_analytics",
                status=TenantEntitlement.Status.ACTIVE,
            ).exists()
        )

    def test_grandfather_legacy_toggle_is_visible_to_entitlement_engine(self):
        settings_obj = StoreSettings.objects.get_settings()
        settings_obj.enable_reviews = True
        settings_obj.save(update_fields=["enable_reviews"])

        with schema_context(get_public_schema_name()):
            category = FeatureCategory.objects.create(name="Storefront", slug="storefront")
            FeatureDefinition.objects.create(
                category=category,
                name="Reviews",
                code="reviews",
                feature_type="boolean",
                is_active=True,
                is_purchasable=True,
                store_setting_key="enable_reviews",
                storefront_flag="enable_reviews",
            )

        created = grandfather_legacy_entitlements()
        engine = FeatureEntitlementEngine(self.tenant.schema_name)

        self.assertGreaterEqual(created, 1)
        self.assertTrue(engine.has_feature("reviews"))
        self.assertTrue(TenantEntitlement.objects.filter(feature_code="reviews").exists())

    def test_bundle_activation_expands_items_and_rebuilds_limit_quota(self):
        with schema_context(get_public_schema_name()):
            ops_category = FeatureCategory.objects.create(name="Operations", slug="operations")
            limit_feature = FeatureDefinition.objects.create(
                category=ops_category,
                name="Max Products",
                code="max_products",
                feature_type="limit",
                is_active=True,
                is_purchasable=True,
            )
            FeaturePrice.objects.create(
                feature=limit_feature,
                currency="NGN",
                billing_cycle=BillingCycle.MONTHLY,
                amount=Decimal("4000.00"),
                limit_increment=100,
                is_active=True,
            )
            bundle = FeatureBundle.objects.create(
                name="Growth Pack",
                slug="growth-pack",
                price=Decimal("12000.00"),
                currency="NGN",
                billing_cycle=BillingCycle.MONTHLY,
                is_active=True,
            )
            BundleItem.objects.create(bundle=bundle, feature=self.feature, sort_order=1)
            BundleItem.objects.create(bundle=bundle, feature=limit_feature, quantity_override=50, sort_order=2)

        purchase = create_purchase(
            schema_name=self.tenant.schema_name,
            bundle_slug="growth-pack",
            currency="NGN",
            billing_cycle=BillingCycle.MONTHLY,
            quantity=1,
            initiated_by=self.user,
        )
        activate_purchase(purchase, gateway_reference="gw_bundle_123", gateway_transaction_id="gw_bundle_tx_123")

        self.assertEqual(
            TenantEntitlement.objects.filter(purchase_id=purchase.id, status=TenantEntitlement.Status.ACTIVE).count(),
            2,
        )
        self.assertEqual(FeaturePurchaseItem.objects.filter(purchase=purchase).count(), 2)
        quota = ResourceQuota.objects.get(resource_type="max_products")
        self.assertEqual(quota.total_quota, 50)

    def test_zero_limit_quota_blocks_new_allocations(self):
        with schema_context(get_public_schema_name()):
            ops_category = FeatureCategory.objects.create(name="Operations", slug="ops-limit")
            FeatureDefinition.objects.create(
                category=ops_category,
                name="Staff Management",
                code="staff_management",
                feature_type="limit",
                is_active=True,
                is_purchasable=True,
                default_limit_value=0,
            )

        with self.assertRaises(QuotaExceededError):
            enforce_quota("staff_management")

    def test_default_limit_baseline_applies_before_any_purchase(self):
        with schema_context(get_public_schema_name()):
            ops_category = FeatureCategory.objects.create(name="Operations", slug="ops-defaults")
            FeatureDefinition.objects.create(
                category=ops_category,
                name="Max Products",
                code="max_products",
                feature_type="limit",
                is_active=True,
                is_purchasable=True,
                default_limit_value=50,
            )

        engine = FeatureEntitlementEngine(self.tenant.schema_name)
        quota = engine.rebuild_quota("max_products")

        self.assertEqual(engine.get_feature_limit("max_products"), 50)
        self.assertEqual(quota.total_quota, 50)

    def test_limit_entitlements_stack_on_top_of_default_baseline(self):
        with schema_context(get_public_schema_name()):
            ops_category = FeatureCategory.objects.create(name="Operations", slug="ops-stacked")
            feature = FeatureDefinition.objects.create(
                category=ops_category,
                name="Max Products",
                code="max_products",
                feature_type="limit",
                is_active=True,
                is_purchasable=True,
                default_limit_value=50,
            )

        TenantEntitlement.objects.create(
            feature_id=feature.id,
            feature_code=feature.code,
            feature_name=feature.name,
            feature_type=feature.feature_type,
            source=TenantEntitlement.Source.MANUAL,
            quantity_granted=100,
            limit_value=100,
            status=TenantEntitlement.Status.ACTIVE,
            activated_at=timezone.now(),
            billing_cycle=BillingCycle.MONTHLY,
        )

        engine = FeatureEntitlementEngine(self.tenant.schema_name)
        self.assertEqual(engine.get_feature_limit("max_products"), 150)

    def test_store_settings_form_disables_locked_premium_fields_without_entitlement(self):
        with schema_context(get_public_schema_name()):
            category = FeatureCategory.objects.create(name="Locked Features", slug="locked-features")
            FeatureDefinition.objects.create(
                category=category,
                name="Wishlist",
                code="wishlist",
                feature_type="boolean",
                is_active=True,
                is_purchasable=True,
                default_boolean_value=False,
                store_setting_key="enable_wishlist",
            )

        form = StoreSettingsForm(instance=StoreSettings.objects.get_settings())

        self.assertTrue(form.fields["enable_wishlist"].disabled)
        self.assertTrue(any(item["feature_code"] == "wishlist" for item in form.locked_feature_fields))

    def test_usage_consumption_spans_multiple_entitlements(self):
        with schema_context(get_public_schema_name()):
            usage_category = FeatureCategory.objects.create(name="AI", slug="ai")
            feature = FeatureDefinition.objects.create(
                category=usage_category,
                name="AI Credits",
                code="ai_credits",
                feature_type="usage",
                is_active=True,
                is_purchasable=True,
            )

        TenantEntitlement.objects.create(
            feature_id=feature.id,
            feature_code=feature.code,
            feature_name=feature.name,
            feature_type=feature.feature_type,
            source=TenantEntitlement.Source.MANUAL,
            quantity_granted=3,
            status=TenantEntitlement.Status.ACTIVE,
            activated_at=timezone.now(),
            billing_cycle=BillingCycle.ONE_TIME,
        )
        TenantEntitlement.objects.create(
            feature_id=feature.id,
            feature_code=feature.code,
            feature_name=feature.name,
            feature_type=feature.feature_type,
            source=TenantEntitlement.Source.MANUAL,
            quantity_granted=4,
            status=TenantEntitlement.Status.ACTIVE,
            activated_at=timezone.now(),
            billing_cycle=BillingCycle.ONE_TIME,
        )

        engine = FeatureEntitlementEngine(self.tenant.schema_name)
        consumed = engine.consume_feature_usage("ai_credits", amount=5, description="AI image generation")

        self.assertTrue(consumed)
        self.assertEqual(engine.get_usage_remaining("ai_credits"), 2)
        self.assertEqual(UsageRecord.objects.filter(feature_code="ai_credits").count(), 2)
        self.assertEqual(
            TenantEntitlement.objects.filter(feature_code="ai_credits", status=TenantEntitlement.Status.EXHAUSTED).count(),
            1,
        )

    def test_global_disable_override_beats_active_entitlement(self):
        with schema_context(get_public_schema_name()):
            category = FeatureCategory.objects.create(name="Storefront", slug="storefront-override")
            feature = FeatureDefinition.objects.create(
                category=category,
                name="Wishlist",
                code="wishlist",
                feature_type="boolean",
                is_active=True,
                is_purchasable=True,
                is_globally_disabled=True,
            )

        TenantEntitlement.objects.create(
            feature_id=feature.id,
            feature_code=feature.code,
            feature_name=feature.name,
            feature_type=feature.feature_type,
            source=TenantEntitlement.Source.MANUAL,
            boolean_value=True,
            status=TenantEntitlement.Status.ACTIVE,
            activated_at=timezone.now(),
            billing_cycle=BillingCycle.PERPETUAL,
        )

        engine = FeatureEntitlementEngine(self.tenant.schema_name)
        self.assertFalse(engine.has_feature("wishlist"))

    def test_payment_resolution_uses_public_purchase_index(self):
        purchase = create_purchase(
            schema_name=self.tenant.schema_name,
            feature_code="advanced_analytics",
            currency="NGN",
            billing_cycle=BillingCycle.MONTHLY,
            quantity=1,
            initiated_by=self.user,
        )

        result = process_marketplace_payment_event(
            payment_status="success",
            purchase_reference=purchase.purchase_reference,
            gateway_reference="gw_resolved_123",
            gateway_transaction_id="gw_tx_resolved_123",
            metadata={"source": "test"},
        )
        purchase.refresh_from_db()
        index = FeaturePurchaseIndex.objects.get(purchase_reference=purchase.purchase_reference)

        self.assertTrue(result.success)
        self.assertEqual(purchase.status, FeaturePurchase.Status.COMPLETED)
        self.assertEqual(index.status, FeaturePurchaseIndex.PurchaseStatus.COMPLETED)
        self.assertEqual(index.schema_name, self.tenant.schema_name)
        self.assertEqual(purchase.gateway_reference, "gw_resolved_123")
