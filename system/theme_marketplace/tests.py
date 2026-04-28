from __future__ import annotations

from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from system.theme_marketplace.models import TenantActiveTheme, TenantInstalledTheme, TenantThemeAccess, Theme, ThemeSwitchLog
from system.theme_marketplace.services import (
    DEFAULT_THEME_SLUG,
    acquire_theme_for_schema,
    activate_theme_for_schema,
    get_active_theme_cache_key,
    install_theme_for_schema,
    sync_theme_catalog,
)
from themes.loader import Loader


VISIBLE_THEME_SLUGS = {
    "creative-showcase",
    "developer-pro",
    "writer-journal",
    "agency-grid",
}


class ThemeCatalogSyncTests(TestCase):
    def test_sync_theme_catalog_is_idempotent(self):
        first = sync_theme_catalog(actor=None, bootstrap_access=False)
        second = sync_theme_catalog(actor=None, bootstrap_access=False)

        self.assertEqual(Theme.objects.count(), 5)
        self.assertEqual(first["created"], 5)
        self.assertEqual(second["created"], 0)
        self.assertGreaterEqual(second["updated"], 5)

        visible = set(
            Theme.objects.filter(is_internal=False, is_published=True).values_list("slug", flat=True)
        )
        self.assertSetEqual(visible, VISIBLE_THEME_SLUGS)
        self.assertTrue(Theme.objects.filter(slug=DEFAULT_THEME_SLUG, is_internal=True).exists())

    def test_management_command_syncs_catalog(self):
        buffer = StringIO()
        call_command("sync_theme_catalog", stdout=buffer)
        output = buffer.getvalue()

        self.assertIn("Synced shared theme catalog", output)
        self.assertEqual(Theme.objects.count(), 5)


class ThemeActivationTests(TestCase):
    def setUp(self):
        sync_theme_catalog(actor=None, bootstrap_access=False)

    def test_new_tenant_has_no_access_or_active_theme_by_default(self):
        schema_name = "tenant_new"

        self.assertFalse(TenantThemeAccess.objects.filter(schema_name=schema_name).exists())
        self.assertFalse(TenantInstalledTheme.objects.filter(schema_name=schema_name).exists())
        self.assertFalse(TenantActiveTheme.objects.filter(schema_name=schema_name).exists())

    def test_activation_requires_acquisition_and_installation(self):
        schema_name = "tenant_alpha"
        theme = Theme.objects.get(slug="creative-showcase")

        with self.assertRaises(ValueError):
            activate_theme_for_schema(schema_name, theme, reason="test_activation_without_access")

        acquire_theme_for_schema(schema_name, theme)

        with self.assertRaises(ValueError):
            activate_theme_for_schema(schema_name, theme, reason="test_activation_without_install")

        install_theme_for_schema(schema_name, theme)
        activate_theme_for_schema(schema_name, theme, reason="test_activation")

        active = TenantActiveTheme.objects.get(schema_name=schema_name)
        self.assertEqual(active.theme.slug, "creative-showcase")
        self.assertTrue(
            ThemeSwitchLog.objects.filter(
                schema_name=schema_name,
                from_theme__isnull=True,
                to_theme=theme,
                reason="test_activation",
            ).exists()
        )

    def test_revoking_active_access_clears_active_theme(self):
        schema_name = "tenant_bravo"
        theme = Theme.objects.get(slug="developer-pro")

        access = acquire_theme_for_schema(schema_name, theme)
        install_theme_for_schema(schema_name, theme)
        activate_theme_for_schema(schema_name, theme, reason="test_activation")

        access.is_active = False
        access.save(update_fields=["is_active", "updated_at"])

        self.assertFalse(TenantActiveTheme.objects.filter(schema_name=schema_name).exists())

    def test_activation_clears_cached_theme_slug(self):
        schema_name = "tenant_cache"
        theme = Theme.objects.get(slug="writer-journal")
        cache_key = get_active_theme_cache_key(schema_name)

        acquire_theme_for_schema(schema_name, theme)
        install_theme_for_schema(schema_name, theme)
        cache.set(cache_key, DEFAULT_THEME_SLUG, 60)

        activate_theme_for_schema(schema_name, theme, reason="cache_invalidation")

        self.assertIsNone(cache.get(cache_key))


class ThemeLoaderTests(TestCase):
    def setUp(self):
        sync_theme_catalog(actor=None, bootstrap_access=False)

    def test_loader_prefers_active_theme_then_internal_default(self):
        schema_name = "tenant_loader"
        theme = Theme.objects.get(slug="agency-grid")

        acquire_theme_for_schema(schema_name, theme)
        install_theme_for_schema(schema_name, theme)
        activate_theme_for_schema(schema_name, theme, reason="loader_test")

        original_schema_name = getattr(connection, "schema_name", None)
        connection.schema_name = schema_name
        try:
            loader = Loader(None)
            dirs = loader.get_dirs()
        finally:
            connection.schema_name = original_schema_name

        self.assertTrue(dirs[0].endswith("themes\\agency-grid\\templates"))
        self.assertTrue(any(path.endswith("themes\\default\\templates") for path in dirs))
