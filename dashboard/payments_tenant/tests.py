import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase
from django.urls import resolve, reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient, TenantRequestFactory
from django_tenants.utils import get_public_schema_name, schema_context

from dashboard.payments_tenant.services.provider_checkout import _format_provider_error, _initialize_paystack
from dashboard.payments_tenant.models import (
    SupportedCurrency,
    TenantBalance,
    TenantGatewayCredential,
    TenantGatewayMode,
    TenantPaymentProfile,
    Transaction,
)
from dashboard.payments_tenant.view_utils import get_payment_profile
from public.userauth.models import TenantUser
from system.account.models import PlatformUser
from system.system_pay.models import PaymentGatewayDefinition, PlatformGatewayCredential


class PaymentsTenantTestCase(TenantTestCase):
    platform_owner = None

    @classmethod
    def get_test_schema_name(cls):
        if not hasattr(cls, "_test_schema_name"):
            cls._test_schema_name = f"test_{uuid.uuid4().hex[:20]}"
        return cls._test_schema_name

    @classmethod
    def get_test_tenant_domain(cls):
        return f"{cls.get_test_schema_name()}.tenant.test.com"

    @classmethod
    def setup_tenant(cls, tenant):
        cls.platform_owner, _ = PlatformUser.objects.get_or_create(
            email=f"{cls.__name__.lower()}@example.com",
            defaults={
                "first_name": "Payments",
                "last_name": "Owner",
                "account_status": PlatformUser.AccountStatus.ACTIVE,
            },
        )
        cls.platform_owner.set_password("OwnerPass123!")
        cls.platform_owner.account_status = PlatformUser.AccountStatus.ACTIVE
        cls.platform_owner.save()
        tenant.owner = cls.platform_owner
        tenant.name = "Payments Test Shop"
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
            cls._ensure_public_model_table_exists(PaymentGatewayDefinition)
            cls._ensure_public_model_table_exists(PlatformGatewayCredential)
            for model in (
                TenantUser,
                TenantPaymentProfile,
                TenantGatewayCredential,
                TenantGatewayMode,
                SupportedCurrency,
                TenantBalance,
                Transaction,
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
            TenantPaymentProfile,
            TenantGatewayCredential,
            TenantGatewayMode,
            SupportedCurrency,
            TenantBalance,
            Transaction,
        ):
            self._ensure_tenant_model_table_exists(model)

        self.client = TenantClient(self.tenant)
        self.factory = TenantRequestFactory(self.tenant)
        self.prefix = "admin"
        self.staff_user = TenantUser.objects.create_user(
            email="payments-staff@example.com",
            password="StrongPass123!",
            first_name="Pay",
            last_name="Manager",
            user_type=TenantUser.UserType.STAFF,
            is_staff=True,
            account_status=TenantUser.AccountStatus.ACTIVE,
        )
        self.client.force_login(
            self.staff_user,
            backend="sabistart_store.auth_backends.SchemaAwareAuthenticationBackend",
        )


class PaymentsTenantRouteTests(PaymentsTenantTestCase):
    def test_tenant_payments_home_resolves_under_dashboard_prefix(self):
        url = reverse("dashboard:payments_tenant:tenant_home", kwargs={"prefix": self.prefix})
        match = resolve(url)

        self.assertEqual(url, "/dashboard/admin/payments/")
        self.assertEqual(match.url_name, "tenant_home")
        self.assertEqual(match.namespace, "dashboard:payments_tenant")


class PaymentsTenantBootstrapTests(PaymentsTenantTestCase):
    def test_get_payment_profile_bootstraps_currency_and_gateway_mode(self):
        with schema_context(get_public_schema_name()):
            gateway = PaymentGatewayDefinition.objects.create(
                provider="paystack",
                name="Paystack",
                is_enabled=True,
                supported_currencies=["NGN"],
            )
            PlatformGatewayCredential.objects.create(
                gateway=gateway,
                name="Primary credential",
                environment="test",
                is_active=True,
                priority=10,
                secret_key="sk_test_123",
            )

        request = self.factory.get(
            reverse("dashboard:payments_tenant:tenant_home", kwargs={"prefix": self.prefix})
        )
        request.user = self.staff_user
        request.tenant = self.tenant

        profile = get_payment_profile(request)
        gateway_mode = TenantGatewayMode.objects.get(payment_profile=profile, gateway__name="Paystack")

        self.assertEqual(TenantPaymentProfile.objects.count(), 1)
        self.assertEqual(profile.account_status, TenantPaymentProfile.AccountStatus.ACTIVE)
        self.assertTrue(
            SupportedCurrency.objects.filter(
                payment_profile=profile,
                currency_code=profile.default_currency,
                is_default=True,
            ).exists()
        )
        self.assertEqual(gateway_mode.mode, "platform")
        self.assertEqual(gateway_mode.status, gateway_mode.ActivationStatus.ACTIVE)
        self.assertTrue(gateway_mode.is_default)


class ProviderCheckoutUnitTests(SimpleTestCase):
    def test_initialize_paystack_uses_minor_units_once_for_transaction_charge(self):
        captured = {}

        def fake_json_request(method, url, *, headers=None, json_body=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["json_body"] = json_body or {}
            return {
                "status": True,
                "data": {
                    "reference": "FM-TEST-123",
                    "authorization_url": "https://checkout.paystack.com/test",
                    "access_code": "ACCESS123",
                },
            }

        intent = SimpleNamespace(
            id=uuid.uuid4(),
            amount=Decimal("2500.00"),
            currency="NGN",
            customer_email="buyer@example.com",
            gateway_intent_id="FM-TEST-123",
            callback_url="https://example.com/payments/callback/",
            success_url="https://example.com/payments/success/",
            cancel_url="https://example.com/payments/cancel/",
            metadata={},
        )
        gateway_mode = SimpleNamespace(gateway=SimpleNamespace(provider="paystack"))

        with patch(
            "dashboard.payments_tenant.services.provider_checkout.get_effective_credentials",
            return_value={"secret_key": "sk_test_123", "public_key": "pk_test_123"},
        ), patch(
            "dashboard.payments_tenant.services.provider_checkout._json_request",
            side_effect=fake_json_request,
        ):
            result = _initialize_paystack(
                intent,
                gateway_mode,
                {
                    "subaccount": "ACCT_platform",
                    "transaction_charge": Decimal("62.50"),
                    "transaction_charge_minor": 6250,
                    "bearer": "account",
                },
            )

        self.assertTrue(result.success)
        self.assertEqual(captured["json_body"]["amount"], 250000)
        self.assertEqual(captured["json_body"]["transaction_charge"], 6250)
        self.assertEqual(captured["json_body"]["subaccount"], "ACCT_platform")
        self.assertEqual(captured["json_body"]["bearer"], "account")

    def test_format_provider_error_explains_local_callback_issue(self):
        message = _format_provider_error(
            "paystack",
            {"message": "Gateway rejected request", "code": "1010"},
            "Paystack initialization failed.",
            callback_url="http://shop.localhost:8000/payments/callback/",
        )

        self.assertIn("code: 1010", message)
        self.assertIn("local development host", message)
