from datetime import timedelta
from datetime import timedelta
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
from public.monitoring.models import PageVisit, VisitorSession
from public.userauth.models import TenantUser
from system.account.models import PlatformUser
from system.feature_marketplace.models import BillingCycle, FeatureCategory, FeatureDefinition, TenantFeatureOverride


@override_settings(ALLOWED_HOSTS=["*", ".tenant.test.com", "tenant.test.com", "localhost", "127.0.0.1"])
class MonitoringTenantTestCase(TenantTestCase):
    platform_owner = None

    @classmethod
    def get_test_schema_name(cls):
        if not hasattr(cls, "_test_schema_name"):
            cls._test_schema_name = f"monitor{uuid4().hex[:16]}"
        return cls._test_schema_name

    @classmethod
    def get_test_tenant_domain(cls):
        return f"{cls.get_test_schema_name()}.tenant.test.com"

    @classmethod
    def setup_tenant(cls, tenant):
        cls.platform_owner, _ = PlatformUser.objects.get_or_create(
            email=f"{cls.__name__.lower()}@example.com",
            defaults={
                "first_name": "Monitor",
                "last_name": "Owner",
                "account_status": PlatformUser.AccountStatus.ACTIVE,
            },
        )
        cls.platform_owner.set_password("OwnerPass123!")
        cls.platform_owner.save()
        tenant.owner = cls.platform_owner
        tenant.name = "Monitoring Test Shop"
        return tenant

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.tenant is not None:
            call_command("migrate_schemas", schema=cls.tenant.schema_name, tenant=True, interactive=False, verbosity=0)
            for model in (FeatureCategory, FeatureDefinition, TenantFeatureOverride):
                cls._ensure_public_model_table_exists(model)
            for model in (TenantUser, TenantEntitlement, VisitorSession, PageVisit):
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
        for model in (TenantUser, TenantEntitlement, VisitorSession, PageVisit):
            self._ensure_tenant_model_table_exists(model)

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

        session = VisitorSession.objects.create(
            session_key="tenant-monitor-session",
            schema_name=self.tenant.schema_name,
            source=VisitorSession.Source.STOREFRONT,
            user_identifier=str(self.user.pk),
            landing_path="/",
            last_path="/products/widget/",
            visit_count=3,
            last_seen_at=timezone.now(),
        )
        PageVisit.objects.create(
            visitor_session=session,
            schema_name=self.tenant.schema_name,
            source=VisitorSession.Source.STOREFRONT,
            path="/products/widget/",
            route_name="product:detail",
            status_code=200,
            server_duration_ms=180,
            client_duration_ms=640,
            engaged_seconds=22,
            created_at=timezone.now() - timedelta(days=1),
        )


class MonitoringRouteTests(MonitoringTenantTestCase):
    def test_monitoring_overview_renders(self):
        response = self.client.get(reverse("dashboard:monitoring:overview", kwargs={"prefix": self.prefix}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Traffic analytics")
        self.assertContains(response, "/products/widget/")

    def test_monitoring_pages_and_sessions_routes_render(self):
        pages_response = self.client.get(reverse("dashboard:monitoring:pages", kwargs={"prefix": self.prefix}))
        sessions_response = self.client.get(reverse("dashboard:monitoring:sessions", kwargs={"prefix": self.prefix}))

        self.assertEqual(pages_response.status_code, 200)
        self.assertEqual(sessions_response.status_code, 200)
        self.assertContains(pages_response, "Most visited pages")
        self.assertContains(sessions_response, "Active sessions")

    def test_monitoring_routes_redirect_without_analytics_entitlement(self):
        TenantEntitlement.objects.filter(feature_code="advanced_analytics").delete()
        FeatureEntitlementEngine(self.tenant.schema_name).invalidate_cache("advanced_analytics")

        response = self.client.get(reverse("dashboard:monitoring:overview", kwargs={"prefix": self.prefix}))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("dashboard:feature_marketplace:catalog", kwargs={"prefix": self.prefix}), response.url)
