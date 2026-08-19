from decimal import Decimal
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name, schema_context

from dashboard.feature_marketplace.models import TenantEntitlement
from dashboard.feature_marketplace.services import FeatureEntitlementEngine
from dashboard.pos.models import POSProduct, POSTransaction, Store, StoreInventory
from public.cart.models import Order, OrderItem
from public.monitoring.models import PageVisit, VisitorSession
from public.product.models import Product
from public.userauth.models import Customer, CustomerSession, TenantUser
from system.account.models import PlatformUser
from system.feature_marketplace.models import BillingCycle, FeatureCategory, FeatureDefinition


@override_settings(ALLOWED_HOSTS=["*", ".tenant.test.com", "tenant.test.com", "localhost", "127.0.0.1"])
class AnalyticsTenantTestCase(TenantTestCase):
    platform_owner = None
    _test_schema_name = None

    @classmethod
    def get_test_schema_name(cls):
        if cls._test_schema_name is None:
            cls._test_schema_name = f"analytics{uuid4().hex[:12]}"
        return cls._test_schema_name

    @classmethod
    def get_test_tenant_domain(cls):
        return f"{cls.get_test_schema_name()}.tenant.test.com"

    @classmethod
    def setup_tenant(cls, tenant):
        cls.platform_owner, _ = PlatformUser.objects.get_or_create(
            email=f"{cls.__name__.lower()}@example.com",
            defaults={
                "first_name": "Ada",
                "last_name": "Analyst",
                "account_status": PlatformUser.AccountStatus.ACTIVE,
            },
        )
        cls.platform_owner.set_password("OwnerPass123!")
        cls.platform_owner.save()
        tenant.owner = cls.platform_owner
        tenant.name = "Analytics Test Shop"
        return tenant

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.tenant is not None:
            call_command("migrate_schemas", schema=cls.tenant.schema_name, tenant=True, interactive=False, verbosity=0)
            for model in (FeatureCategory, FeatureDefinition):
                cls._ensure_public_model_table_exists(model)
            for model in (
                TenantUser,
                TenantEntitlement,
                Customer,
                CustomerSession,
                Product,
                Order,
                OrderItem,
                Store,
                POSProduct,
                StoreInventory,
                POSTransaction,
                VisitorSession,
                PageVisit,
            ):
                cls._ensure_model_table_exists(model)

    @classmethod
    def _ensure_public_model_table_exists(cls, model):
        table_name = model._meta.db_table
        with schema_context(get_public_schema_name()):
            if table_name not in connection.introspection.table_names():
                with connection.schema_editor() as editor:
                    editor.create_model(model)

    @classmethod
    def _ensure_model_table_exists(cls, model):
        table_name = model._meta.db_table
        with schema_context(cls.tenant.schema_name):
            if table_name not in connection.introspection.table_names():
                with connection.schema_editor() as editor:
                    editor.create_model(model)

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.client = TenantClient(self.tenant)
        self.prefix = "admin"
        self.user = TenantUser.objects.create_user(
            email="analytics@example.com",
            password="StrongPass123!",
            first_name="Amina",
            last_name="Analyst",
            user_type=TenantUser.UserType.STAFF,
            is_staff=True,
            account_status=TenantUser.AccountStatus.ACTIVE,
        )
        self.client.force_login(
            self.user,
            backend="sabistart.auth_backends.SchemaAwareAuthenticationBackend",
        )

        with schema_context(get_public_schema_name()):
            category, _ = FeatureCategory.objects.get_or_create(name="Analytics", slug="analytics")
            self.analytics_feature, _ = FeatureDefinition.objects.update_or_create(
                code="advanced_analytics",
                defaults={
                    "category": category,
                    "name": "Advanced Analytics",
                    "feature_type": "boolean",
                    "default_boolean_value": False,
                    "is_active": True,
                    "is_purchasable": True,
                },
            )

        TenantEntitlement.objects.create(
            feature_id=self.analytics_feature.id,
            feature_code=self.analytics_feature.code,
            feature_name=self.analytics_feature.name,
            feature_type=self.analytics_feature.feature_type,
            source=TenantEntitlement.Source.MANUAL,
            boolean_value=True,
            status=TenantEntitlement.Status.ACTIVE,
            activated_at=timezone.now(),
            billing_cycle=BillingCycle.PERPETUAL,
        )
        FeatureEntitlementEngine(self.tenant.schema_name).invalidate_cache("advanced_analytics")

        self.customer = Customer.objects.create(
            status=Customer.Status.ACTIVE,
            total_orders=2,
            total_spent=Decimal("720.00"),
            average_order_value=Decimal("360.00"),
            first_order_at=timezone.now() - timedelta(days=15),
            last_order_at=timezone.now() - timedelta(days=1),
            created_at=timezone.now() - timedelta(days=10),
        )
        CustomerSession.objects.create(
            customer=self.customer,
            session_token="customer-analytics-session",
            device_name="Chrome on Windows",
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.product = Product.objects.create(
            name="Analytics Widget",
            slug="analytics-widget",
            sku="AN-WIDGET-001",
            price=Decimal("250.00"),
            stock_quantity=2,
            low_stock_threshold=5,
            status="published",
            is_active=True,
        )
        self.order = Order.objects.create(
            order_number="ORD-AN-001",
            order_number_sequence=1001,
            customer=self.customer,
            customer_email="buyer@example.com",
            customer_name="Buyer One",
            status=Order.OrderStatus.COMPLETED,
            financial_status=Order.FinancialStatus.PAID,
            subtotal_price=Decimal("500.00"),
            total_price=Decimal("540.00"),
            total_paid=Decimal("540.00"),
            total_tax=Decimal("40.00"),
            placed_at=timezone.now() - timedelta(days=2),
        )
        OrderItem.objects.create(
            order=self.order,
            product_title="Analytics Widget",
            quantity=2,
            unit_price=Decimal("250.00"),
            subtotal=Decimal("500.00"),
            total=Decimal("540.00"),
        )

        self.store = Store.objects.create(
            name="Main Branch",
            code="MAIN-001",
            address="1 Example Street",
            manager=self.user,
            tax_rate=Decimal("0.0750"),
            created_by=self.user,
            updated_by=self.user,
        )
        self.pos_product = POSProduct.objects.create(
            name="POS Widget",
            sku="POS-WIDGET-001",
            cost_price=Decimal("90.00"),
            selling_price=Decimal("120.00"),
            is_active=True,
            created_by=self.user,
            updated_by=self.user,
        )
        self.inventory = StoreInventory.objects.create(
            store=self.store,
            product=self.pos_product,
            quantity=3,
            low_stock_threshold=5,
            created_by=self.user,
            updated_by=self.user,
        )
        POSTransaction.objects.create(
            store=self.store,
            cashier=self.user,
            transaction_number="POS-AN-001",
            status="completed",
            subtotal=Decimal("120.00"),
            total_amount=Decimal("129.00"),
            amount_paid=Decimal("129.00"),
            tax_amount=Decimal("9.00"),
            created_by=self.user,
            updated_by=self.user,
        )

        visitor_session = VisitorSession.objects.create(
            session_key="analytics-session",
            schema_name=self.tenant.schema_name,
            source=VisitorSession.Source.STOREFRONT,
            user_identifier=str(self.user.pk),
            landing_path="/",
            last_path="/products/analytics-widget/",
            visit_count=2,
            last_seen_at=timezone.now(),
        )
        PageVisit.objects.create(
            visitor_session=visitor_session,
            schema_name=self.tenant.schema_name,
            source=VisitorSession.Source.STOREFRONT,
            path="/products/analytics-widget/",
            route_name="product:detail",
            status_code=200,
            server_duration_ms=180,
            client_duration_ms=620,
            engaged_seconds=20,
            created_at=timezone.now() - timedelta(days=1),
        )


class AnalyticsRouteTests(AnalyticsTenantTestCase):
    def test_overview_page_renders(self):
        response = self.client.get(reverse("dashboard:analytics:overview", kwargs={"prefix": self.prefix}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business Analytics")
        self.assertContains(response, "Revenue Trend")

    def test_module_pages_render(self):
        for name in ("orders", "products", "inventory", "customers"):
            response = self.client.get(reverse(f"dashboard:analytics:{name}", kwargs={"prefix": self.prefix}))
            self.assertEqual(response.status_code, 200)

    def test_data_endpoint_returns_standard_shape(self):
        response = self.client.get(reverse("dashboard:analytics:data", kwargs={"prefix": self.prefix, "page_key": "overview"}))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("filters", payload)
        self.assertIn("kpis", payload)
        self.assertIn("charts", payload)
        self.assertIn("table_rows", payload)

    def test_exports_return_files(self):
        base_url = reverse("dashboard:analytics:overview", kwargs={"prefix": self.prefix})

        csv_response = self.client.get(f"{base_url}?export=csv")
        xlsx_response = self.client.get(f"{base_url}?export=xlsx")
        pdf_response = self.client.get(f"{base_url}?export=pdf")

        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response["Content-Type"])
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertIn("spreadsheetml", xlsx_response["Content-Type"])
        self.assertEqual(pdf_response.status_code, 200)
        self.assertIn("application/pdf", pdf_response["Content-Type"])

    def test_redirects_without_entitlement(self):
        TenantEntitlement.objects.filter(feature_code="advanced_analytics").delete()
        FeatureEntitlementEngine(self.tenant.schema_name).invalidate_cache("advanced_analytics")
        response = self.client.get(reverse("dashboard:analytics:overview", kwargs={"prefix": self.prefix}))
        self.assertEqual(response.status_code, 302)
