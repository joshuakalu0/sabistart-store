from decimal import Decimal

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient, TenantRequestFactory
from django_tenants.utils import schema_context

from public.category.models import Brand, Category
from public.product.models import Attribute, AttributeValue, Product, ProductVariant
from dashboard.store_settings.models import ThemeSettings
from public.storefront.services import build_catalog_page, build_theme_tokens, get_navigation_categories
from public.userauth.models import Customer, TenantUser
from system.account.models import PlatformUser


def attach_session(request):
    middleware = SessionMiddleware(lambda req: None)
    middleware.process_request(request)
    request.session.save()
    request.user = AnonymousUser()
    return request


class StorefrontTestCase(TenantTestCase):
    platform_owner = None

    @classmethod
    def get_test_schema_name(cls):
        return f"test_{cls.__name__.lower()[:20]}"

    @classmethod
    def get_test_tenant_domain(cls):
        return f"{cls.get_test_schema_name()}.tenant.test.com"

    @classmethod
    def setup_tenant(cls, tenant):
        cls.platform_owner = PlatformUser.objects.create_user(
            email=f"{cls.__name__.lower()}@example.com",
            password="OwnerPass123!",
            first_name="Store",
            last_name="Owner",
            account_status=PlatformUser.AccountStatus.ACTIVE,
        )
        tenant.owner = cls.platform_owner
        tenant.name = "Nara Test Shop"
        return tenant

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()

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
            cls._ensure_model_table_exists(Brand)

    @classmethod
    def _ensure_model_table_exists(cls, model):
        table_name = model._meta.db_table
        with schema_context(cls.tenant.schema_name):
            if table_name not in connection.introspection.table_names():
                with connection.schema_editor() as editor:
                    editor.create_model(model)

    def setUp(self):
        super().setUp()
        cache.clear()
        self.factory = TenantRequestFactory(self.tenant)
        self.client = TenantClient(self.tenant)

        self.brand_one = Brand.objects.create(name="Atelier One", slug="atelier-one")
        self.brand_two = Brand.objects.create(name="Studio Two", slug="studio-two")

        self.category_parent = Category.objects.create(name="Women", slug="women", show_in_menu=True, menu_order=1)
        self.category_child = Category.objects.create(name="Shoes", slug="shoes", parent=self.category_parent, show_in_menu=True, menu_order=1)

        self.color = Attribute.objects.create(name="Color", slug="color", is_variant_option=True, is_filterable=True)
        self.size = Attribute.objects.create(name="Size", slug="size", is_variant_option=True, is_filterable=True)

        self.red = AttributeValue.objects.create(attribute=self.color, value="Red", slug="red")
        self.blue = AttributeValue.objects.create(attribute=self.color, value="Blue", slug="blue")
        self.large = AttributeValue.objects.create(attribute=self.size, value="Large", slug="large")
        self.small = AttributeValue.objects.create(attribute=self.size, value="Small", slug="small")

        self.sale_product = Product.objects.create(
            name="Red Runner",
            slug="red-runner",
            sku="SKU-RED-RUNNER",
            product_type="variable",
            brand=self.brand_one,
            status="published",
            is_active=True,
            is_featured=True,
            is_new=True,
            is_on_sale=True,
            short_description="Primary sale test product.",
            price=Decimal("60.00"),
            compare_at_price=Decimal("90.00"),
        )
        self.sale_product.categories.add(self.category_parent)
        self.sale_variant = ProductVariant.objects.create(
            product=self.sale_product,
            sku="SKU-RED-RUNNER-L",
            variant_name="Red / Large",
            price=Decimal("60.00"),
            compare_at_price=Decimal("90.00"),
            stock_quantity=10,
            is_default=True,
        )
        self.sale_variant.option_values.add(self.red, self.large)

        self.regular_product = Product.objects.create(
            name="Blue Loafer",
            slug="blue-loafer",
            sku="SKU-BLUE-LOAFER",
            product_type="variable",
            brand=self.brand_two,
            status="published",
            is_active=True,
            short_description="Regular priced product.",
            price=Decimal("20.00"),
        )
        self.regular_product.categories.add(self.category_child)
        self.regular_variant = ProductVariant.objects.create(
            product=self.regular_product,
            sku="SKU-BLUE-LOAFER-L",
            variant_name="Blue / Large",
            price=Decimal("20.00"),
            stock_quantity=8,
            is_default=True,
        )
        self.regular_variant.option_values.add(self.blue, self.large)

        self.other_red_product = Product.objects.create(
            name="Red Mule",
            slug="red-mule",
            sku="SKU-RED-MULE",
            product_type="variable",
            brand=self.brand_two,
            status="published",
            is_active=True,
            short_description="Alternate red product.",
            price=Decimal("35.00"),
        )
        self.other_red_product.categories.add(self.category_child)
        self.other_red_variant = ProductVariant.objects.create(
            product=self.other_red_product,
            sku="SKU-RED-MULE-S",
            variant_name="Red / Small",
            price=Decimal("35.00"),
            stock_quantity=4,
            is_default=True,
        )
        self.other_red_variant.option_values.add(self.red, self.small)

        self.out_of_stock_product = Product.objects.create(
            name="Stone Sandal",
            slug="stone-sandal",
            sku="SKU-STONE-SANDAL",
            product_type="variable",
            brand=self.brand_one,
            status="published",
            is_active=True,
            short_description="Out of stock product.",
            price=Decimal("48.00"),
        )
        self.out_of_stock_product.categories.add(self.category_parent)
        self.out_of_stock_variant = ProductVariant.objects.create(
            product=self.out_of_stock_product,
            sku="SKU-STONE-SANDAL-STD",
            variant_name="Stone / Standard",
            price=Decimal("48.00"),
            stock_quantity=0,
            is_default=True,
        )

        self.user = TenantUser.objects.create_user(
            email="shopper@example.com",
            password="StrongPass123!",
            first_name="Nara",
            last_name="Buyer",
            account_status=TenantUser.AccountStatus.ACTIVE,
        )
        Customer.objects.create(user=self.user, status=Customer.Status.ACTIVE)


class StorefrontServiceTests(StorefrontTestCase):
    def test_build_theme_tokens_uses_defaults_when_no_theme_exists(self):
        request = attach_session(self.factory.get("/"))

        ThemeSettings.objects.all().delete()
        tokens = build_theme_tokens(request)

        self.assertEqual(tokens["primary_color"], "#0F172A")
        self.assertIn("Plus Jakarta Sans", tokens["heading_font"])

    def test_navigation_categories_include_nested_children(self):
        request = attach_session(self.factory.get("/"))

        tree = get_navigation_categories(request, limit=12)

        self.assertEqual(tree[0]["slug"], "women")
        self.assertEqual(tree[0]["children"][0]["slug"], "shoes")

    def test_catalog_filters_support_attribute_and_group_semantics(self):
        request = attach_session(
            self.factory.get(
                "/shop/",
                {
                    "brand": ["atelier-one", "studio-two"],
                    "category": ["women", "shoes"],
                    "attribute_color": ["red"],
                    "attribute_size": ["large"],
                },
            )
        )

        context = build_catalog_page(
            request,
            queryset=Product.objects.all(),
            page_title="Shop",
            page_description="All products",
            breadcrumbs=[],
        )

        self.assertEqual(context["result_count"], 1)
        self.assertEqual(context["products"][0]["slug"], "red-runner")

    def test_discounted_items_are_sorted_first_even_with_price_sort(self):
        request = attach_session(self.factory.get("/shop/", {"sort": "price_asc"}))

        context = build_catalog_page(
            request,
            queryset=Product.objects.all(),
            page_title="Shop",
            page_description="All products",
            breadcrumbs=[],
        )

        self.assertEqual(context["products"][0]["slug"], "red-runner")

    def test_catalog_hides_out_of_stock_products_by_default(self):
        request = attach_session(self.factory.get("/shop/"))

        context = build_catalog_page(
            request,
            queryset=Product.objects.all(),
            page_title="Shop",
            page_description="All products",
            breadcrumbs=[],
        )

        product_slugs = [product["slug"] for product in context["products"]]
        self.assertNotIn("stone-sandal", product_slugs)


class StorefrontRouteTests(StorefrontTestCase):
    def test_shop_all_ajax_returns_partial_markup(self):
        response = self.client.get(
            reverse("category:shop_all"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Curated for your current filter mix.")
        self.assertNotContains(response, "<html", html=False)

    def test_core_route_family_smoke(self):
        home = self.client.get(reverse("home:index"))
        shop = self.client.get(reverse("category:shop_all"))
        product = self.client.get(reverse("product:product_detail", kwargs={"product_slug": self.sale_product.slug}))
        cart = self.client.get(reverse("cart:cart_page"))
        support = self.client.get(reverse("support:help_center"))
        login = self.client.get(reverse("tenant:login"))

        self.assertEqual(home.status_code, 200)
        self.assertEqual(shop.status_code, 200)
        self.assertEqual(product.status_code, 200)
        self.assertEqual(cart.status_code, 200)
        self.assertEqual(support.status_code, 200)
        self.assertEqual(login.status_code, 200)

    def test_out_of_stock_product_hidden_from_shop_but_available_directly(self):
        shop_response = self.client.get(reverse("category:shop_all"))
        detail_response = self.client.get(
            reverse("product:product_detail", kwargs={"product_slug": self.out_of_stock_product.slug})
        )

        self.assertEqual(shop_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertNotContains(shop_response, "Stone Sandal")
        self.assertContains(detail_response, "Stone Sandal")

    def test_guest_can_add_to_cart_and_reach_checkout_auth(self):
        add_response = self.client.post(
            reverse("product:product_detail", kwargs={"product_slug": self.sale_product.slug}),
            {"action": "add_to_cart", "variant_id": str(self.sale_variant.id), "quantity": "1"},
            follow=True,
        )
        checkout_response = self.client.get(reverse("checkout:checkout_auth"))

        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(checkout_response.status_code, 200)
        self.assertContains(checkout_response, "Choose how you want to continue.")

    def test_authenticated_customer_account_dashboard_loads(self):
        login_ok = self.client.login(email="shopper@example.com", password="StrongPass123!")
        self.assertTrue(login_ok, "Tenant login failed")

        response = self.client.get(reverse("tenant:account_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Everything tied to your storefront profile.")
