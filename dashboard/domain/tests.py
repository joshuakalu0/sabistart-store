import uuid
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory
from django.urls import resolve, reverse
from django.utils import timezone
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import get_public_schema_name, schema_context
from datetime import timedelta

from dashboard.domain.models import (
    ACMEChallenge,
    CustomDomain,
    DomainDNSRecord,
    DomainEventLog,
    DomainHealthCheck,
    DomainQuota,
    DomainRedirectRule,
    DomainResolutionCache,
    DomainVerificationAttempt,
    NginxVhostConfig,
    SSLCertificate,
    SSLProvisioningLog,
)
from dashboard.feature_marketplace.models import ResourceQuota, TenantEntitlement
from dashboard.feature_marketplace.services import FeatureEntitlementEngine
from dashboard.domain.views import acme_challenge
from public.userauth.models import TenantUser
from system.account.models import PlatformUser
from system.feature_marketplace.models import BillingCycle, FeatureCategory, FeatureDefinition


class DomainDashboardTenantTestCase(TenantTestCase):
    platform_owner = None

    @classmethod
    def get_test_schema_name(cls):
        return f"domain_{uuid.uuid4().hex[:16]}"

    @classmethod
    def get_test_tenant_domain(cls):
        return f"{cls.get_test_schema_name()}.tenant.test.com"

    @classmethod
    def setup_tenant(cls, tenant):
        cls.platform_owner, _ = PlatformUser.objects.get_or_create(
            email=f"{cls.__name__.lower()}@example.com",
            defaults={
                "first_name": "Domain",
                "last_name": "Owner",
                "account_status": PlatformUser.AccountStatus.ACTIVE,
            },
        )
        cls.platform_owner.set_password("OwnerPass123!")
        cls.platform_owner.save()
        tenant.owner = cls.platform_owner
        tenant.name = "Domain Test Shop"
        return tenant

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.tenant is not None:
            call_command("migrate_schemas", schema=cls.tenant.schema_name, tenant=True, interactive=False, verbosity=0)
            for model in (
                FeatureCategory,
                FeatureDefinition,
            ):
                cls._ensure_public_model_table_exists(model)
            for model in (
                CustomDomain,
                DomainDNSRecord,
                DomainVerificationAttempt,
                SSLCertificate,
                SSLProvisioningLog,
                DomainRedirectRule,
                DomainEventLog,
                DomainHealthCheck,
                DomainQuota,
                NginxVhostConfig,
                DomainResolutionCache,
                ACMEChallenge,
            ):
                cls._ensure_public_model_table_exists(model)
            for model in (TenantUser, TenantEntitlement, ResourceQuota):
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
        for model in (TenantUser, TenantEntitlement, ResourceQuota):
            self._ensure_tenant_model_table_exists(model)
        self.client = TenantClient(self.tenant)
        self.factory = RequestFactory()
        self.prefix = "admin"
        self.user = TenantUser.objects.create_user(
            email="domains-staff@example.com",
            password="StrongPass123!",
            first_name="Domain",
            last_name="Manager",
            user_type=TenantUser.UserType.STAFF,
            is_staff=True,
            account_status=TenantUser.AccountStatus.ACTIVE,
        )
        self.client.force_login(
            self.user,
            backend="sabistart_store.auth_backends.SchemaAwareAuthenticationBackend",
        )
        with schema_context(get_public_schema_name()):
            category, _ = FeatureCategory.objects.get_or_create(name="Operations", slug="operations")
            self.domain_feature, _ = FeatureDefinition.objects.update_or_create(
                code="max_custom_domains",
                defaults={
                    "category": category,
                    "name": "Custom Domain Slots",
                    "feature_type": "limit",
                    "default_limit_value": 0,
                    "is_active": True,
                    "is_purchasable": True,
                },
            )
        TenantEntitlement.objects.create(
            feature_id=self.domain_feature.id,
            feature_code=self.domain_feature.code,
            feature_name=self.domain_feature.name,
            feature_type=self.domain_feature.feature_type,
            source=TenantEntitlement.Source.MANUAL,
            quantity_granted=1,
            limit_value=1,
            status=TenantEntitlement.Status.ACTIVE,
            activated_at=timezone.now(),
            billing_cycle=BillingCycle.ANNUAL,
        )
        FeatureEntitlementEngine(self.tenant.schema_name).rebuild_quota("max_custom_domains")


class DomainRouteTests(DomainDashboardTenantTestCase):
    def test_domain_dashboard_route_renders_under_prefix(self):
        url = reverse("dashboard:domain:list", kwargs={"prefix": self.prefix})
        match = resolve(url)
        response = self.client.get(url)

        self.assertEqual(url, "/dashboard/admin/domains/")
        self.assertEqual(match.url_name, "list")
        self.assertEqual(match.namespace, "dashboard:domain")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Connect a custom domain")


class DomainFlowTests(DomainDashboardTenantTestCase):
    @patch("dashboard.domain.views.verify_domain_dns.delay")
    def test_add_domain_creates_records_and_primary_domain(self, mocked_verify):
        response = self.client.post(
            reverse("dashboard:domain:add", kwargs={"prefix": self.prefix}),
            {"domain": "brand-example.com"},
            follow=True,
        )

        custom_domain = CustomDomain.objects.get(domain="brand-example.com")
        quota = DomainQuota.objects.get(tenant=self.tenant)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(custom_domain.is_primary)
        self.assertEqual(custom_domain.status, CustomDomain.Status.PENDING)
        self.assertEqual(custom_domain.dns_records.count(), 3)
        self.assertEqual(quota.max_custom_domains, 1)
        mocked_verify.assert_called_once_with(str(custom_domain.id))

    def test_domain_dashboard_redirects_without_domain_entitlement(self):
        TenantEntitlement.objects.filter(feature_code="max_custom_domains").delete()
        FeatureEntitlementEngine(self.tenant.schema_name).rebuild_quota("max_custom_domains")

        response = self.client.get(reverse("dashboard:domain:list", kwargs={"prefix": self.prefix}))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("dashboard:feature_marketplace:catalog", kwargs={"prefix": self.prefix}), response.url)

    def test_acme_challenge_returns_key_authorization(self):
        custom_domain = CustomDomain.objects.create(
            tenant=self.tenant,
            domain="ssl-ready.example.com",
            status=CustomDomain.Status.SSL_PENDING,
        )
        challenge = ACMEChallenge.objects.create(
            custom_domain=custom_domain,
            token="token-123",
            key_auth="token-123.thumbprint",
            is_active=True,
            expires_at=timezone.now() + timedelta(minutes=10),
        )

        request = self.factory.get(
            reverse("acme_challenge", kwargs={"token": challenge.token}),
            HTTP_HOST=custom_domain.domain,
        )
        request.hostname = custom_domain.domain

        response = acme_challenge(request, challenge.token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode("utf-8"), challenge.key_auth)
