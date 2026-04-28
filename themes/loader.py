"""Shared storefront theme loader.

This loader serves tenant storefront templates from a single shared central
``themes/<slug>/templates`` directory. Theme activation changes only database records
and cache state; no per-tenant theme files are ever created or copied.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.template.loaders.filesystem import Loader as FilesystemLoader

logger = logging.getLogger(__name__)


class Loader(FilesystemLoader):
    """Resolve templates from the active shared tenant theme with graceful fallback."""

    def get_dirs(self):
        from system.theme_marketplace.services import DEFAULT_THEME_SLUG, get_theme_slug_for_schema

        themes_root = Path(getattr(settings, "THEMES_ROOT", Path(settings.BASE_DIR) / "themes"))
        try:
            schema_name = getattr(connection, "schema_name", None) or "public"
        except Exception:  # pragma: no cover - defensive
            schema_name = "public"

        try:
            active_slug = get_theme_slug_for_schema(schema_name)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Theme loader could not resolve active theme for %s: %s", schema_name, exc)
            active_slug = DEFAULT_THEME_SLUG

        ordered_dirs = []
        for slug in (active_slug, DEFAULT_THEME_SLUG):
            theme_dir = themes_root / slug / "templates"
            if theme_dir.exists():
                candidate = str(theme_dir)
                if candidate not in ordered_dirs:
                    ordered_dirs.append(candidate)

        if not ordered_dirs:
            logger.error("No shared theme template directories are available under %s", themes_root)
        return ordered_dirs
