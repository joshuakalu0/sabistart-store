from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from dashboard.pricing.models import (
    BuyXGetYItem,
    BuyXGetYPromotion,
    Currency,
    DiscountCode,
    DiscountRule,
    ExchangeRate,
    FlashSale,
    FlashSaleItem,
    VolumePricingTier,
)
from dashboard.pricing.utiles.discount import (
    record_discount_usage,
    reverse_discount_usage_for_order,
    validate_discount_code,
)
from dashboard.pricing.utiles.price_resolver import PricingContext, resolve_price
from dashboard.pricing.views import analytics as analytics_views
from dashboard.pricing.views import discount as discount_views
from dashboard.pricing.views import promotions as promotion_views
from public.storefront.tests import StorefrontTestCase, attach_session
from public.userauth.models import Customer, CustomerGroup, TenantUser


class PricingEngineTests(StorefrontTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.customer = Customer.objects.get(user=self.user)

    def _unwrap(self, view):
        while hasattr(view, "__wrapped__"):
            view = view.__wrapped__
        return view

    def _build_cart_items(self, *, quantity=1, unit_price=Decimal("60.00"), line_subtotal=None):
        subtotal = line_subtotal if line_subtotal is not None else (unit_price * quantity)
        return [
            {
                "id": str(self.sale_variant.id),
                "variant": self.sale_variant,
                "product": self.sale_product,
                "quantity": quantity,
                "unit_price": Decimal(unit_price),
                "line_subtotal": Decimal(subtotal),
                "compare_at_price": Decimal("90.00"),
                "sku": self.sale_variant.sku,
                "product_title": self.sale_product.name,
            }
        ]

    def _configure_fx(self):
        usd = Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_base_currency=True,
            is_enabled=True,
        )
        ngn = Currency.objects.create(
            code="NGN",
            name="Naira",
            symbol="₦",
            is_enabled=True,
        )
        ExchangeRate.objects.create(
            base_currency=usd,
            target_currency=ngn,
            rate=Decimal("100.000000"),
            provider="manual",
        )
        return usd, ngn

    def test_fixed_amount_discount_converts_to_cart_currency(self):
        self._configure_fx()
        discount = DiscountCode.objects.create(
            code="SAVE10",
            title="Save 10 Dollars",
            value_type=DiscountCode.ValueType.FIXED_AMOUNT,
            fixed_amount=Decimal("10.00"),
            currency="USD",
        )

        result = validate_discount_code(
            code=discount.code,
            cart_subtotal=Decimal("6000.00"),
            customer=self.customer,
            cart_items=self._build_cart_items(unit_price=Decimal("6000.00"), line_subtotal=Decimal("6000.00")),
            currency_code="NGN",
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.discount_amount, Decimal("1000.00"))

    def test_fixed_amount_discount_fails_cleanly_when_conversion_is_missing(self):
        Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_base_currency=True,
            is_enabled=True,
        )
        Currency.objects.create(
            code="NGN",
            name="Naira",
            symbol="₦",
            is_enabled=True,
        )
        discount = DiscountCode.objects.create(
            code="SAVE10",
            title="Save 10 Dollars",
            value_type=DiscountCode.ValueType.FIXED_AMOUNT,
            fixed_amount=Decimal("10.00"),
            currency="USD",
        )

        result = validate_discount_code(
            code=discount.code,
            cart_subtotal=Decimal("6000.00"),
            customer=self.customer,
            cart_items=self._build_cart_items(unit_price=Decimal("6000.00"), line_subtotal=Decimal("6000.00")),
            currency_code="NGN",
        )

        self.assertFalse(result.valid)
        self.assertIn("Exchange rate from USD to NGN is not configured", result.message)

    def test_group_targeted_discount_respects_customer_segment(self):
        vip_group = CustomerGroup.objects.create(name="VIP", slug="vip")
        self.customer.groups.add(vip_group)

        other_user = TenantUser.objects.create_user(
            email="other-shopper@example.com",
            password="StrongPass123!",
            first_name="Other",
            last_name="Buyer",
            account_status=TenantUser.AccountStatus.ACTIVE,
        )
        other_customer = Customer.objects.create(user=other_user, status=Customer.Status.ACTIVE)

        discount = DiscountCode.objects.create(
            code="VIPONLY",
            title="VIP Only",
            value_type=DiscountCode.ValueType.PERCENTAGE,
            percentage_value=Decimal("15.00"),
            customer_eligibility="group",
        )
        DiscountRule.objects.create(
            discount_code=discount,
            rule_type=DiscountRule.RuleType.CUSTOMER_GROUP,
            customer_group=vip_group,
        )

        eligible = validate_discount_code(
            code=discount.code,
            cart_subtotal=Decimal("60.00"),
            customer=self.customer,
            cart_items=self._build_cart_items(),
            currency_code="USD",
        )
        blocked = validate_discount_code(
            code=discount.code,
            cart_subtotal=Decimal("60.00"),
            customer=other_customer,
            cart_items=self._build_cart_items(),
            currency_code="USD",
        )

        self.assertTrue(eligible.valid)
        self.assertFalse(blocked.valid)
        self.assertIn("customer segment", blocked.message.lower())

    def test_record_and_reverse_discount_usage_is_idempotent(self):
        discount = DiscountCode.objects.create(
            code="ONEUSE",
            title="Single use",
            value_type=DiscountCode.ValueType.FIXED_AMOUNT,
            fixed_amount=Decimal("5.00"),
        )
        order_ref = SimpleNamespace(id=uuid4())

        usage = record_discount_usage(
            discount_code_id=discount.id,
            order_id=order_ref.id,
            order_number="ORD-000001",
            discount_amount=Decimal("5.00"),
            order_subtotal=Decimal("60.00"),
            customer=self.customer,
            customer_email=self.user.email,
            currency="USD",
        )
        discount.refresh_from_db()
        self.assertEqual(discount.usage_count, 1)

        duplicate = record_discount_usage(
            discount_code_id=discount.id,
            order_id=order_ref.id,
            order_number="ORD-000001",
            discount_amount=Decimal("5.00"),
            order_subtotal=Decimal("60.00"),
            customer=self.customer,
            customer_email=self.user.email,
            currency="USD",
        )
        discount.refresh_from_db()
        self.assertEqual(usage.id, duplicate.id)
        self.assertEqual(discount.usage_count, 1)
        self.assertEqual(discount.usages.count(), 1)

        reversed_count = reverse_discount_usage_for_order(order_ref, reason="cancelled")
        usage.refresh_from_db()
        discount.refresh_from_db()
        self.assertEqual(reversed_count, 1)
        self.assertTrue(usage.is_reversed)
        self.assertEqual(discount.usage_count, 0)

        restored = record_discount_usage(
            discount_code_id=discount.id,
            order_id=order_ref.id,
            order_number="ORD-000001",
            discount_amount=Decimal("5.00"),
            order_subtotal=Decimal("60.00"),
            customer=self.customer,
            customer_email=self.user.email,
            currency="USD",
        )
        restored.refresh_from_db()
        discount.refresh_from_db()
        self.assertEqual(restored.id, usage.id)
        self.assertFalse(restored.is_reversed)
        self.assertEqual(discount.usage_count, 1)
        self.assertEqual(discount.usages.count(), 1)

    def test_flash_sale_sold_out_items_fall_back_to_regular_price(self):
        sale = FlashSale.objects.create(
            name="Midnight Drop",
            slug="midnight-drop",
            badge_label="FLASH SALE",
            is_active=True,
            starts_at=timezone.now() - timezone.timedelta(hours=1),
            ends_at=timezone.now() + timezone.timedelta(hours=1),
        )
        item = FlashSaleItem.objects.create(
            flash_sale=sale,
            variant=self.sale_variant,
            sale_price=Decimal("40.00"),
            stock_limit=1,
            is_active=True,
        )

        cache.clear()
        live_price = resolve_price(self.sale_variant, PricingContext(currency_code="USD"))
        self.assertEqual(live_price.applied_layer, "flash_sale")
        self.assertEqual(live_price.final_price, Decimal("40.00"))

        item.units_sold = 1
        item.save(update_fields=["units_sold", "updated_at"])
        cache.clear()

        sold_out_price = resolve_price(self.sale_variant, PricingContext(currency_code="USD"))
        self.assertNotEqual(sold_out_price.applied_layer, "flash_sale")
        self.assertEqual(sold_out_price.final_price, self.sale_variant.effective_price)

    def test_coupon_landing_applies_discount_query_param_to_cart(self):
        DiscountCode.objects.create(
            code="WELCOME10",
            title="Welcome 10",
            description="Welcome discount",
            value_type=DiscountCode.ValueType.PERCENTAGE,
            percentage_value=Decimal("10.00"),
        )

        self.client.post(
            reverse("product:product_detail", kwargs={"product_slug": self.sale_product.slug}),
            {"action": "add_to_cart", "variant_id": str(self.sale_variant.id), "quantity": "1"},
            follow=True,
        )
        response = self.client.get(
            f"{reverse('promotions:coupon_landing')}?discount=WELCOME10",
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "WELCOME10")
        self.assertContains(response, "Active code")

    def test_storefront_templates_show_volume_pricing_and_countdown(self):
        VolumePricingTier.objects.create(
            variant=self.sale_variant,
            min_quantity=3,
            price_type="fixed",
            price=Decimal("50.00"),
            is_active=True,
        )
        FlashSale.objects.create(
            name="Flash Friday",
            slug="flash-friday",
            badge_label="FLASH FRIDAY",
            is_active=True,
            starts_at=timezone.now() - timezone.timedelta(hours=1),
            ends_at=timezone.now() + timezone.timedelta(hours=1),
        )
        FlashSaleItem.objects.create(
            flash_sale=FlashSale.objects.get(slug="flash-friday"),
            variant=self.sale_variant,
            sale_price=Decimal("45.00"),
            is_active=True,
        )

        response = self.client.get(reverse("product:product_detail", kwargs={"product_slug": self.sale_product.slug}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quantity Breaks")
        self.assertContains(response, "3+ units")
        self.assertContains(response, "data-countdown", html=False)

    def test_discount_dashboard_detail_template_renders_with_current_models(self):
        discount = DiscountCode.objects.create(
            code="DETAIL10",
            title="Detail Discount",
            description="Detail view coverage",
            value_type=DiscountCode.ValueType.PERCENTAGE,
            percentage_value=Decimal("10.00"),
        )
        request = attach_session(self.factory.get("/dashboard/store/pricing/discount-codes/"))
        request.user = self.user

        response = self._unwrap(discount_views.discount_code_detail)(
            request,
            prefix=self.tenant.schema_name,
            pk=discount.id,
        )
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertIn("DETAIL10", response.content.decode("utf-8"))

    def test_promotions_dashboard_templates_render_with_current_models(self):
        promotion = BuyXGetYPromotion.objects.create(
            title="Buy Two Get One",
            buy_quantity=2,
            get_quantity=1,
            get_discount_percentage=Decimal("100.00"),
            is_active=True,
        )
        BuyXGetYItem.objects.create(
            promotion=promotion,
            side=BuyXGetYItem.Side.BUY,
            product=self.sale_product,
        )
        sale = FlashSale.objects.create(
            name="Weekend Rush",
            slug="weekend-rush",
            badge_label="RUSH",
            is_active=True,
            starts_at=timezone.now() - timezone.timedelta(hours=1),
            ends_at=timezone.now() + timezone.timedelta(hours=2),
        )
        FlashSaleItem.objects.create(
            flash_sale=sale,
            variant=self.sale_variant,
            sale_price=Decimal("42.00"),
            stock_limit=5,
            is_active=True,
        )
        VolumePricingTier.objects.create(
            variant=self.sale_variant,
            min_quantity=5,
            max_quantity=9,
            price_type="fixed_discount",
            fixed_discount=Decimal("4.00"),
            is_active=True,
        )

        request = attach_session(self.factory.get("/dashboard/store/pricing/promotions/"))
        request.user = self.user

        bxgy_response = self._unwrap(promotion_views.bxgy_detail)(
            request,
            prefix=self.tenant.schema_name,
            pk=promotion.id,
        )
        bxgy_response.render()
        flash_response = self._unwrap(promotion_views.flash_sale_detail)(
            request,
            prefix=self.tenant.schema_name,
            pk=sale.id,
        )
        flash_response.render()
        volume_response = self._unwrap(promotion_views.volume_tier_list)(
            request,
            prefix=self.tenant.schema_name,
        )
        volume_response.render()

        self.assertEqual(bxgy_response.status_code, 200)
        self.assertIn("Buy Two Get One", bxgy_response.content.decode("utf-8"))
        self.assertEqual(flash_response.status_code, 200)
        self.assertIn("Weekend Rush", flash_response.content.decode("utf-8"))
        self.assertEqual(volume_response.status_code, 200)
        self.assertIn("Volume Tier Pricing", volume_response.content.decode("utf-8"))

    def test_pricing_analytics_views_and_reconcile_command_render_without_errors(self):
        request = attach_session(self.factory.get("/dashboard/store/pricing/analytics/"))
        request.user = self.user

        html_response = self._unwrap(analytics_views.pricing_analytics)(
            request,
            prefix=self.tenant.schema_name,
        )
        html_response.render()
        json_response = self._unwrap(analytics_views.pricing_analytics_data)(
            request,
            prefix=self.tenant.schema_name,
        )

        self.assertEqual(html_response.status_code, 200)
        self.assertIn("Pricing Analytics", html_response.content.decode("utf-8"))
        self.assertEqual(json_response.status_code, 200)
        self.assertIn("kpis", json_response.json())

        call_command("reconcile_pricing_integrity", "--dry-run", verbosity=0)
