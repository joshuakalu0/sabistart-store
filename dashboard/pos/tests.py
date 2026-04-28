import json
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name, schema_context

from dashboard.feature_marketplace.models import ResourceQuota, TenantEntitlement
from dashboard.feature_marketplace.services import FeatureEntitlementEngine
from public.product.models import Product
from public.userauth.models import TenantUser
from system.account.models import PlatformUser
from system.feature_marketplace.models import BillingCycle, FeatureCategory, FeatureDefinition

from .models import (
    InventoryAdjustment,
    POSCatalogItem,
    POSDiscount,
    POSPayment,
    POSProduct,
    POSSession,
    POSTerminal,
    POSTransaction,
    POSTransactionItem,
    Store,
    StoreInventory,
)
from .services import (
    adjust_inventory,
    create_sale_transaction,
    get_or_create_default_register,
    open_register_session,
    sync_catalog_bridge,
)


@override_settings(ALLOWED_HOSTS=["*", ".tenant.test.com", "tenant.test.com", "localhost", "127.0.0.1"])
class PosTenantTestCase(TenantTestCase):
    platform_owner = None
    _test_schema_name = None

    @classmethod
    def get_test_schema_name(cls):
        if cls._test_schema_name is None:
            cls._test_schema_name = f"pos{cls.__name__.lower().replace('_', '')[:12]}{uuid4().hex[:8]}"
        return cls._test_schema_name

    @classmethod
    def get_test_tenant_domain(cls):
        return f"{cls.get_test_schema_name()}.tenant.test.com"

    @classmethod
    def setup_tenant(cls, tenant):
        cls.platform_owner, _ = PlatformUser.objects.get_or_create(
            email=f"{cls.__name__.lower()}@example.com",
            defaults={
                "first_name": "Store",
                "last_name": "Owner",
                "account_status": PlatformUser.AccountStatus.ACTIVE,
            },
        )
        cls.platform_owner.set_password("OwnerPass123!")
        cls.platform_owner.account_status = PlatformUser.AccountStatus.ACTIVE
        cls.platform_owner.save()
        tenant.owner = cls.platform_owner
        tenant.name = "POS Test Shop"
        return tenant

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.tenant is not None:
            call_command(
                "migrate_schemas",
                schema=cls.tenant.schema_name,
                tenant=True,
                interactive=False,
                verbosity=0,
            )
            for model in (
                FeatureCategory,
                FeatureDefinition,
            ):
                cls._ensure_public_model_table_exists(model)
            for model in (
                TenantUser,
                TenantEntitlement,
                ResourceQuota,
                POSDiscount,
                Store,
                POSTerminal,
                POSSession,
                POSProduct,
                POSTransaction,
                StoreInventory,
                POSTransactionItem,
                POSPayment,
                InventoryAdjustment,
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
        for model in (
            TenantUser,
            TenantEntitlement,
            ResourceQuota,
            POSDiscount,
            Store,
            POSTerminal,
            POSSession,
            POSProduct,
            POSTransaction,
            StoreInventory,
            POSTransactionItem,
            POSPayment,
            InventoryAdjustment,
        ):
            self._ensure_model_table_exists(model)

        with schema_context(get_public_schema_name()):
            category, _ = FeatureCategory.objects.get_or_create(name="Operations", slug="operations")
            self.pos_feature, _ = FeatureDefinition.objects.update_or_create(
                code="max_pos_locations",
                defaults={
                    "category": category,
                    "name": "POS Locations",
                    "feature_type": "limit",
                    "default_limit_value": 0,
                    "is_active": True,
                    "is_purchasable": True,
                },
            )

        self.client = TenantClient(self.tenant)
        self.prefix = "admin"

        self.staff_user = TenantUser.objects.create_user(
            email="cashier@example.com",
            password="StrongPass123!",
            first_name="Casey",
            last_name="Cashier",
            user_type=TenantUser.UserType.STAFF,
            is_staff=True,
            account_status=TenantUser.AccountStatus.ACTIVE,
        )
        self.client.force_login(
            self.staff_user,
            backend="sabistart_store.auth_backends.SchemaAwareAuthenticationBackend",
        )

        self.store = Store.objects.create(
            name="Victoria Island Store",
            code="VIS-001",
            address="14 Adeola Odeku Street",
            manager=self.staff_user,
            tax_rate=Decimal("0.0750"),
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )
        self.register = get_or_create_default_register(store=self.store, user=self.staff_user)
        self.session = open_register_session(
            cashier=self.staff_user,
            store=self.store,
            terminal=self.register,
            opening_cash=Decimal("5000.00"),
            notes="Morning session",
        )
        self.product = POSProduct.objects.create(
            name="Titanium Notebook",
            sku="POS-NOTEBOOK-001",
            barcode="1234567890123",
            category="Electronics",
            brand="Orbit",
            cost_price=Decimal("200.00"),
            selling_price=Decimal("300.00"),
            is_taxable=True,
            is_active=True,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )
        self.inventory = StoreInventory.objects.create(
            store=self.store,
            product=self.product,
            quantity=10,
            low_stock_threshold=3,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )
        TenantEntitlement.objects.create(
            feature_id=self.pos_feature.id,
            feature_code=self.pos_feature.code,
            feature_name=self.pos_feature.name,
            feature_type=self.pos_feature.feature_type,
            source=TenantEntitlement.Source.MANUAL,
            quantity_granted=1,
            limit_value=1,
            status=TenantEntitlement.Status.ACTIVE,
            activated_at=self.store.created_at,
            billing_cycle=BillingCycle.MONTHLY,
        )
        FeatureEntitlementEngine(self.tenant.schema_name).rebuild_quota("max_pos_locations")

        session = self.client.session
        session["pos_store_id"] = str(self.store.id)
        session["pos_register_id"] = str(self.register.id)
        session.save()


class PosServiceTests(PosTenantTestCase):
    def test_create_sale_transaction_updates_inventory_payment_and_adjustments(self):
        transaction = create_sale_transaction(
            cashier=self.staff_user,
            store=self.store,
            session=self.session,
            terminal=self.register,
            items_data=[{"inventory_id": self.inventory.id, "quantity": 2}],
            payment_method="cash",
            customer_name="In Store Buyer",
        )

        self.inventory.refresh_from_db()

        self.assertEqual(transaction.status, "completed")
        self.assertEqual(transaction.total_amount, Decimal("645.00"))
        self.assertEqual(self.inventory.quantity, 8)
        self.assertEqual(transaction.items.count(), 1)
        self.assertEqual(POSPayment.objects.filter(transaction=transaction).count(), 1)
        self.assertIsNotNone(transaction.authoritative_order)
        self.assertEqual(transaction.authoritative_order.source, transaction.authoritative_order.OrderSource.POS)
        self.assertEqual(transaction.authoritative_order.total_price, transaction.total_amount)
        self.assertTrue(
            InventoryAdjustment.objects.filter(
                store_inventory=self.inventory,
                adjustment_type="sale",
                reference_number=transaction.transaction_number,
            ).exists()
        )

    def test_sync_catalog_bridge_only_includes_pos_ready_catalog_products(self):
        ready_product = Product.objects.create(
            name="Bridgeable Mug",
            sku="CAT-BRIDGE-001",
            product_type="simple",
            price=Decimal("1500.00"),
            cost_price=Decimal("900.00"),
            status="published",
            is_active=True,
            is_pos_available=True,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )
        Product.objects.create(
            name="Hidden Lamp",
            sku="CAT-HIDDEN-001",
            product_type="simple",
            price=Decimal("5000.00"),
            cost_price=Decimal("3200.00"),
            status="published",
            is_active=True,
            is_pos_available=False,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )

        summary = sync_catalog_bridge(user=self.staff_user)

        self.assertGreaterEqual(summary["created_items"], 1)
        self.assertTrue(POSCatalogItem.objects.filter(product=ready_product).exists())
        self.assertEqual(POSCatalogItem.objects.filter(product__sku="CAT-HIDDEN-001").count(), 0)

    def test_insufficient_inventory_rolls_back_sale(self):
        with self.assertRaises(ValidationError):
            create_sale_transaction(
                cashier=self.staff_user,
                store=self.store,
                session=self.session,
                terminal=self.register,
                items_data=[{"inventory_id": self.inventory.id, "quantity": 50}],
                payment_method="cash",
            )

        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.quantity, 10)
        self.assertEqual(POSTransaction.objects.count(), 0)
        self.assertEqual(POSPayment.objects.count(), 0)
        self.assertEqual(InventoryAdjustment.objects.count(), 0)

    def test_adjust_inventory_updates_stock_and_logs_adjustment(self):
        updated_inventory, adjustment = adjust_inventory(
            inventory=self.inventory,
            adjustment_type="restock",
            quantity_change=5,
            reason="Weekly replenishment",
            user=self.staff_user,
            reference_number="RESTOCK-001",
        )

        self.assertEqual(updated_inventory.quantity, 15)
        self.assertEqual(adjustment.quantity_before, 10)
        self.assertEqual(adjustment.quantity_after, 15)
        self.assertEqual(adjustment.reference_number, "RESTOCK-001")

    def test_create_sale_transaction_supports_split_payments(self):
        transaction = create_sale_transaction(
            cashier=self.staff_user,
            store=self.store,
            session=self.session,
            terminal=self.register,
            items_data=[{"inventory_id": self.inventory.id, "quantity": 1}],
            payment_method="split",
            payments_data=[
                {
                    "payment_method": "cash",
                    "amount": "300.00",
                    "amount_received": "350.00",
                },
                {
                    "payment_method": "card_terminal",
                    "amount": "22.50",
                    "terminal_reference": "TERM-001",
                },
            ],
        )

        self.assertEqual(transaction.total_amount, Decimal("322.50"))
        self.assertEqual(transaction.change_amount, Decimal("27.50"))
        self.assertEqual(transaction.payments.count(), 2)
        self.assertTrue(transaction.payments.filter(payment_method="card_terminal", terminal_reference="TERM-001").exists())

    def test_sync_offline_transaction_is_idempotent(self):
        payload = {
            "client_transaction_id": "offline-sale-001",
            "items": [{"inventory_id": self.inventory.id, "quantity": 1}],
            "payment_method": "cash",
            "payments": [{"payment_method": "cash", "amount": "322.50", "amount_received": "322.50"}],
            "customer_name": "Offline Buyer",
        }

        from .services import sync_offline_transaction

        first = sync_offline_transaction(
            cashier=self.staff_user,
            store=self.store,
            terminal=self.register,
            session=self.session,
            payload=payload,
        )
        second = sync_offline_transaction(
            cashier=self.staff_user,
            store=self.store,
            terminal=self.register,
            session=self.session,
            payload=payload,
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(POSTransaction.objects.filter(client_transaction_id="offline-sale-001").count(), 1)


class PosRouteTests(PosTenantTestCase):
    def test_dashboard_routes_render_inside_dashboard_shell(self):
        response = self.client.get(reverse("dashboard:pos:dashboard", kwargs={"prefix": self.prefix}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Branch-aware workspace for physical store sales.")
        self.assertContains(response, reverse("dashboard:pos:sales", kwargs={"prefix": self.prefix}))
        self.assertContains(response, reverse("dashboard:pos:stores", kwargs={"prefix": self.prefix}))

    def test_dashboard_redirects_without_pos_entitlement(self):
        TenantEntitlement.objects.filter(feature_code="max_pos_locations").delete()
        FeatureEntitlementEngine(self.tenant.schema_name).rebuild_quota("max_pos_locations")

        response = self.client.get(reverse("dashboard:pos:dashboard", kwargs={"prefix": self.prefix}))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("dashboard:feature_marketplace:catalog", kwargs={"prefix": self.prefix}), response.url)

    def test_search_products_excludes_inactive_products(self):
        inactive_product = POSProduct.objects.create(
            name="Inactive Cable",
            sku="POS-CABLE-002",
            cost_price=Decimal("20.00"),
            selling_price=Decimal("35.00"),
            is_active=False,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )
        StoreInventory.objects.create(
            store=self.store,
            product=inactive_product,
            quantity=9,
            created_by=self.staff_user,
            updated_by=self.staff_user,
        )

        response = self.client.get(
            reverse("dashboard:pos:search_products", kwargs={"prefix": self.prefix}),
            {"q": "Cable", "store_id": self.store.id},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["products"], [])

    def test_receipt_route_renders_transaction_snapshot(self):
        transaction = create_sale_transaction(
            cashier=self.staff_user,
            store=self.store,
            session=self.session,
            terminal=self.register,
            items_data=[{"inventory_id": self.inventory.id, "quantity": 1}],
            payment_method="cash",
        )

        response = self.client.get(
            reverse("dashboard:pos:receipt", kwargs={"prefix": self.prefix, "transaction_id": transaction.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, transaction.transaction_number)
        self.assertContains(response, "Titanium Notebook")

    def test_invoice_route_alias_renders_transaction_snapshot(self):
        transaction = create_sale_transaction(
            cashier=self.staff_user,
            store=self.store,
            session=self.session,
            terminal=self.register,
            items_data=[{"inventory_id": self.inventory.id, "quantity": 1}],
            payment_method="cash",
            customer_name="Walk In Buyer",
        )

        response = self.client.get(
            reverse("dashboard:pos:invoice", kwargs={"prefix": self.prefix, "transaction_id": transaction.id})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, transaction.transaction_number)
        self.assertContains(response, "Walk In Buyer")

    def test_cart_checkout_returns_receipt_detail_and_invoice_urls(self):
        add_response = self.client.post(
            reverse("dashboard:pos:cart_add", kwargs={"prefix": self.prefix}),
            data=json.dumps({"inventory_id": str(self.inventory.id)}),
            content_type="application/json",
        )
        self.assertEqual(add_response.status_code, 200)
        self.assertTrue(add_response.json()["success"])

        checkout_response = self.client.post(
            reverse("dashboard:pos:cart_checkout", kwargs={"prefix": self.prefix}),
            data=json.dumps(
                {
                    "payment_method": "cash",
                    "amount_received": "400.00",
                    "customer_name": "Checkout Buyer",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(checkout_response.status_code, 200)
        payload = checkout_response.json()
        self.assertTrue(payload["success"])
        self.assertIn("/receipt/", payload["receipt_url"])
        self.assertIn("/sales/", payload["detail_url"])
        self.assertIn("/invoice/", payload["invoice_url"])

    def test_offline_sync_returns_sale_urls(self):
        response = self.client.post(
            reverse("dashboard:pos:offline_sync", kwargs={"prefix": self.prefix}),
            data=json.dumps(
                {
                    "transactions": [
                        {
                            "client_transaction_id": "offline-route-001",
                            "items": [{"inventory_id": str(self.inventory.id), "quantity": 1}],
                            "payment_method": "cash",
                            "payments": [{"payment_method": "cash", "amount": "322.50", "amount_received": "322.50"}],
                            "customer_name": "Offline Route Buyer",
                        }
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(len(payload["transactions"]), 1)
        synced = payload["transactions"][0]
        self.assertEqual(synced["client_transaction_id"], "offline-route-001")
        self.assertIn("/receipt/", synced["receipt_url"])
        self.assertIn("/invoice/", synced["invoice_url"])
        self.assertIn("/sales/", synced["detail_url"])

    def test_pos_dashboard_shows_setup_page_when_schema_is_behind(self):
        with patch(
            "dashboard.pos.views.get_pos_schema_issues",
            return_value=[
                {
                    "table": "pos_stores",
                    "missing_table": False,
                    "missing_columns": ["contact_name", "contact_phone"],
                }
            ],
        ):
            response = self.client.get(reverse("dashboard:pos:dashboard", kwargs={"prefix": self.prefix}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "POS Setup Required")
        self.assertContains(response, "pos_stores")

    def test_register_redirects_to_places_with_query_when_no_active_register_exists(self):
        self.register.is_active = False
        self.register.save(update_fields=["is_active"])

        session = self.client.session
        session.pop("pos_register_id", None)
        session.save()

        response = self.client.get(reverse("dashboard:pos:register", kwargs={"prefix": self.prefix}))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("dashboard:pos:stores", kwargs={"prefix": self.prefix}), response.url)
        self.assertIn(f"store={self.store.id}", response.url)
