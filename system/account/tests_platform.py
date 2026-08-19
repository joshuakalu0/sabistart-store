from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.db.utils import ProgrammingError
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve, reverse

from public.storefront.context_processors import global_storefront_context
from public.storefront.services import get_or_create_customer_profile
from sabistart.navigation import build_platform_navigation
from system.account.platform_support import safe_platform_call, setup_warning_for


class PlatformNavigationTests(SimpleTestCase):
    def test_platform_navigation_contains_live_platform_sections(self):
        sections = build_platform_navigation("platform_dashboard")
        items = [item["key"] for section in sections for item in section["items"]]

        self.assertIn("platform_dashboard", items)
        self.assertIn("platform_stores", items)
        self.assertIn("platform_features", items)
        self.assertIn("platform_payments", items)

    @override_settings(ROOT_URLCONF="sabistart.urls_public")
    def test_platform_namespace_exists_in_public_urlconf(self):
        self.assertEqual(reverse("platform:login"), "/platform/login/")

    @override_settings(ROOT_URLCONF="sabistart.urls_public")
    def test_public_platform_theme_route_resolves(self):
        match = resolve("/platform/themes/")

        self.assertEqual(match.namespace, "platform_themes")
        self.assertEqual(match.url_name, "home")

    @override_settings(ROOT_URLCONF="sabistart.urls_public")
    def test_dashboard_namespace_exists_in_public_urlconf(self):
        self.assertEqual(
            reverse("dashboard:dashboard_home:home", args=["demo-store"]),
            "/dashboard/demo-store/",
        )


class PlatformStorefrontIsolationTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("public.storefront.context_processors.get_store_settings_cached")
    def test_global_storefront_context_skips_public_schema_requests(self, mocked_store_settings):
        request = self.factory.get("/platform/payments/")
        request.user = SimpleNamespace(is_authenticated=True, email="admin@example.com")

        with patch("public.storefront.context_processors.connection", SimpleNamespace(schema_name="public")):
            context = global_storefront_context(request)

        self.assertEqual(context, {})
        mocked_store_settings.assert_not_called()

    @patch("public.storefront.services.Customer.objects.get_or_create")
    def test_platform_like_user_does_not_create_customer_profile(self, mocked_get_or_create):
        user = SimpleNamespace(is_authenticated=True, email="admin@example.com")

        profile = get_or_create_customer_profile(user)

        self.assertIsNone(profile)
        mocked_get_or_create.assert_not_called()


class PlatformSupportHelperTests(SimpleTestCase):
    def test_safe_platform_call_returns_default_on_db_error(self):
        result = safe_platform_call(lambda: (_ for _ in ()).throw(ProgrammingError("broken")), [])

        self.assertEqual(result, [])

    @patch("system.account.platform_support.connection.introspection.table_names", return_value=["existing_table"])
    def test_setup_warning_mentions_missing_tables(self, mocked_table_names):
        existing_model = SimpleNamespace(_meta=SimpleNamespace(db_table="existing_table"))
        missing_model = SimpleNamespace(_meta=SimpleNamespace(db_table="missing_table"))

        warning = setup_warning_for("Feature marketplace", existing_model, missing_model)

        self.assertIn("Feature marketplace setup is incomplete.", warning)
        self.assertIn("missing_table", warning)
        mocked_table_names.assert_called_once()
