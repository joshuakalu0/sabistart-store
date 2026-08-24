from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from system.core.models import Shop
from system.theme_marketplace.models import (
    TenantInstalledTheme,
    TenantActiveTheme,
    TenantThemeAsset,
    TenantThemeAccess,
    TenantThemeContent,
    Theme,
    ThemeBasePage,
    ThemeCategory,
    ThemeOffer,
    ThemeRelease,
    ThemeReview,
    ThemeSwitchLog,
)

DEFAULT_THEME_SLUG = "default"
THEME_CACHE_TTL = 60


@dataclass
class ThemeManifest:
    slug: str
    path: Path
    data: dict
    schema: dict
    changelog: str


def get_themes_root() -> Path:
    return Path(getattr(settings, "THEMES_ROOT", settings.BASE_DIR / "themes"))


def shared_theme_manifest_exists(slug: str) -> bool:
    normalized = (slug or "").strip()
    if not normalized:
        return False
    manifest_path = get_themes_root() / normalized / "theme.json"
    return manifest_path.exists()


def get_active_theme_cache_key(schema_name: str) -> str:
    normalized = (schema_name or "public").strip() or "public"
    return f"sabistart:theme:active:{normalized}"


def clear_active_theme_cache(schema_name: str) -> None:
    cache.delete(get_active_theme_cache_key(schema_name))


def get_default_theme() -> Theme | None:
    return Theme.objects.filter(slug=DEFAULT_THEME_SLUG, is_internal=True).first()


def has_active_theme_for_schema(schema_name: str) -> bool:
    schema_name = (schema_name or "").strip()
    if not schema_name or schema_name == "public":
        return True
    return TenantActiveTheme.objects.filter(schema_name=schema_name).exists()


def get_theme_slug_for_schema(schema_name: str) -> str:
    schema_name = (schema_name or "").strip()
    if not schema_name or schema_name == "public":
        return DEFAULT_THEME_SLUG

    cache_key = get_active_theme_cache_key(schema_name)
    cached = cache.get(cache_key)
    if cached:
        return cached

    try:
        active = TenantActiveTheme.objects.select_related("theme").filter(schema_name=schema_name).first()
        slug = active.theme.slug if active and active.theme_id else DEFAULT_THEME_SLUG
    except Exception:
        slug = DEFAULT_THEME_SLUG

    cache.set(cache_key, slug, THEME_CACHE_TTL)
    return slug


def list_builtin_theme_manifests() -> list[ThemeManifest]:
    manifests: list[ThemeManifest] = []
    themes_root = get_themes_root()
    if not themes_root.exists():
        return manifests
    for theme_dir in sorted(themes_root.iterdir()):
        if not theme_dir.is_dir():
            continue
        if theme_dir.name.startswith("__"):
            continue
        manifest_path = theme_dir / "theme.json"
        if not manifest_path.exists():
            continue
        schema_path = theme_dir / "schema.json"
        changelog_path = theme_dir / "CHANGELOG.md"
        manifests.append(
            ThemeManifest(
                slug=theme_dir.name,
                path=theme_dir,
                data=json.loads(manifest_path.read_text(encoding="utf-8")),
                schema=json.loads(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else {},
                changelog=changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else "",
            )
        )
    return manifests


def _page_entries_from_manifest(theme_slug: str, manifest_data: dict) -> list[dict]:
    entries = []
    for item in manifest_data.get("pages", []):
        if isinstance(item, str):
            page_name = item
            title = ""
            description = ""
            css_path = ""
            required = True
        else:
            page_name = str(item.get("path", "")).strip()
            title = item.get("title", "")
            description = item.get("description", "")
            css_path = item.get("css_path", "")
            required = item.get("is_required", True)
        if not page_name:
            continue
        entries.append(
            {
                "page_name": page_name,
                "file_path": page_name,
                "css_path": css_path,
                "title": title,
                "description": description,
                "is_required": required,
            }
        )
    return entries


def sync_theme_base_pages(theme: Theme, page_data: list[dict]) -> None:
    names = [item["page_name"] for item in page_data]
    ThemeBasePage.objects.filter(theme=theme).exclude(page_name__in=names).delete()
    for item in page_data:
        ThemeBasePage.objects.update_or_create(
            theme=theme,
            page_name=item["page_name"],
            defaults={
                "file_path": item["file_path"],
                "css_path": item.get("css_path", ""),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "is_required": item.get("is_required", True),
            },
        )


def _sync_theme_offers(theme: Theme, offer_data: list[dict]) -> None:
    names = []
    for item in offer_data:
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        names.append(name)
        ThemeOffer.objects.update_or_create(
            theme=theme,
            name=name,
            defaults={
                "offer_type": item.get("offer_type", ThemeOffer.OfferType.FREE),
                "billing_interval": item.get("billing_interval", ThemeOffer.BillingInterval.NONE),
                "currency": item.get("currency", theme.currency),
                "price": item.get("price", theme.price),
                "compare_at_price": item.get("compare_at_price") or None,
                "is_default": item.get("is_default", False),
                "is_active": item.get("is_active", True),
                "metadata": item.get("metadata", {}),
            },
        )
    ThemeOffer.objects.filter(theme=theme).exclude(name__in=names).delete()


def _sync_theme_releases(theme: Theme, release_data: list[dict], manifest_changelog: str) -> None:
    seen_versions = []
    for item in release_data:
        version = str(item.get("version", "")).strip()
        if not version:
            continue
        seen_versions.append(version)
        ThemeRelease.objects.update_or_create(
            theme=theme,
            version=version,
            defaults={
                "title": item.get("title", ""),
                "changelog": item.get("changelog", manifest_changelog),
                "released_at": item.get("released_at") or timezone.now(),
                "metadata": item.get("metadata", {}),
            },
        )
    if not seen_versions and theme.version:
        ThemeRelease.objects.update_or_create(
            theme=theme,
            version=theme.version,
            defaults={
                "title": "Current packaged release",
                "changelog": manifest_changelog,
                "released_at": timezone.now(),
            },
        )


@transaction.atomic
def sync_theme_catalog(*, actor=None, bootstrap_access: bool = False) -> dict[str, int]:
    created = 0
    updated = 0
    category_created = 0
    pages_synced = 0
    bootstrap_result = {"checked": 0, "activated": 0, "already_active": 0, "failed": 0}

    manifests = list_builtin_theme_manifests()
    seen_slugs = {manifest.slug for manifest in manifests}

    for manifest in manifests:
        data = manifest.data
        visibility = str(data.get("catalog_visibility", "listed")).strip().lower()
        if visibility == "hidden" and manifest.slug != DEFAULT_THEME_SLUG:
            continue
        category_data = data.get("category", {}) or {}
        category = None
        if category_data:
            category_defaults = {
                "name": category_data.get("name", category_data.get("slug", "").replace("-", " ").title()),
                "description": category_data.get("description", ""),
                "sort_order": category_data.get("sort_order", 0),
                "is_active": category_data.get("is_active", True),
            }
            category, was_created = ThemeCategory.objects.update_or_create(
                slug=category_data.get("slug", "general"),
                defaults=category_defaults,
            )
            if was_created:
                category_created += 1

        defaults = {
            "category": category,
            "name": data.get("name", manifest.slug.replace("-", " ").title()),
            "description": data.get("description", ""),
            "version": data.get("version", "1.0.0"),
            "currency": data.get("currency", "NGN"),
            "price": data.get("price", "0.00"),
            "is_free": data.get("is_free", True),
            "source": Theme.Source.BUILTIN,
            "status": data.get("status", Theme.Status.APPROVED),
            "is_published": data.get("is_published", True),
            "is_featured": data.get("is_featured", manifest.slug != DEFAULT_THEME_SLUG),
            "preview_image_path": data.get("preview_image_path", ""),
            "thumbnail_path": data.get("thumbnail_path", data.get("preview_image_path", "")),
            "demo_url": data.get("demo_url", ""),
            "schema_path": data.get("schema_path", "schema.json" if manifest.schema else ""),
            "changelog_path": data.get("changelog_path", "CHANGELOG.md" if manifest.changelog else ""),
            "feature_bullets": data.get("features", []),
            "preview_gallery": data.get("preview_gallery", []),
            "manifest": data,
            "metadata": {
                **(data.get("metadata") or {}),
                "theme_schema": manifest.schema,
                "managed_by": "sync_theme_catalog",
                "shared_theme_directory": manifest.slug,
            },
            "folder_path": manifest.slug,
            "published_at": timezone.now() if data.get("is_published", True) else None,
            "is_internal": data.get("is_internal", manifest.slug == DEFAULT_THEME_SLUG),
        }
        if getattr(actor, "pk", None):
            defaults["creator"] = actor
        theme, was_created = Theme.objects.update_or_create(slug=manifest.slug, defaults=defaults)
        if was_created:
            created += 1
        else:
            updated += 1

        page_entries = _page_entries_from_manifest(manifest.slug, data)
        sync_theme_base_pages(theme, page_entries)
        _sync_theme_offers(theme, data.get("offers", []))
        _sync_theme_releases(theme, data.get("releases", []), manifest.changelog)
        pages_synced += len(page_entries)

    Theme.objects.filter(source=Theme.Source.BUILTIN).exclude(slug__in=seen_slugs).update(
        status=Theme.Status.SUSPENDED,
        is_published=False,
        updated_at=timezone.now(),
    )

    if bootstrap_access:
        bootstrap_result = bootstrap_default_theme_for_schemas()

    return {
        "created": created,
        "updated": updated,
        "category_created": category_created,
        "pages_synced": pages_synced,
        "bootstrap_checked": bootstrap_result["checked"],
        "bootstrap_activated": bootstrap_result["activated"],
        "bootstrap_already_active": bootstrap_result["already_active"],
        "bootstrap_failed": bootstrap_result["failed"],
    }


def get_shop_for_schema(schema_name: str) -> Shop | None:
    return Shop.objects.filter(schema_name=schema_name).first()


def _tenant_schema_names() -> list[str]:
    return [
        schema_name
        for schema_name in Shop.objects.exclude(schema_name="public").values_list("schema_name", flat=True)
        if schema_name
    ]


@transaction.atomic
def ensure_theme_access(schema_name: str, theme: Theme, *, access_type: str = TenantThemeAccess.AccessType.FREE) -> TenantThemeAccess:
    shop = get_shop_for_schema(schema_name)
    access, _ = TenantThemeAccess.objects.get_or_create(
        schema_name=schema_name,
        theme=theme,
        defaults={
            "shop": shop,
            "access_type": access_type,
            "acquired_at": timezone.now(),
            "purchase_date": timezone.now() if access_type == TenantThemeAccess.AccessType.PURCHASED else None,
            "purchase_price": theme.price if access_type == TenantThemeAccess.AccessType.PURCHASED else None,
            "is_active": True,
        },
    )
    changed = []
    if access.shop_id is None and shop is not None:
        access.shop = shop
        changed.append("shop")
    if not access.is_active:
        access.is_active = True
        access.revoked_at = None
        changed.append("is_active")
        changed.append("revoked_at")
    if changed:
        access.save(update_fields=changed + ["updated_at"])
    return access


@transaction.atomic
def acquire_theme_for_schema(schema_name: str, theme: Theme, *, actor=None, access_type: str | None = None) -> TenantThemeAccess:
    resolved_access_type = access_type or (
        TenantThemeAccess.AccessType.FREE if theme.is_free else TenantThemeAccess.AccessType.PURCHASED
    )
    access = ensure_theme_access(schema_name, theme, access_type=resolved_access_type)
    if resolved_access_type == TenantThemeAccess.AccessType.PURCHASED and not access.purchase_date:
        access.purchase_date = timezone.now()
        access.purchase_price = theme.price
        access.payment_reference = access.payment_reference or f"theme-acq:{theme.slug}:{schema_name}"
        access.save(update_fields=["purchase_date", "purchase_price", "payment_reference", "updated_at"])
    return access


@transaction.atomic
def install_theme_for_schema(schema_name: str, theme: Theme) -> TenantInstalledTheme:
    access = TenantThemeAccess.objects.filter(schema_name=schema_name, theme=theme, is_active=True).first()
    if access is None:
        raise ValueError("Acquire this theme before installing it.")
    shop = get_shop_for_schema(schema_name)
    installed, _ = TenantInstalledTheme.objects.update_or_create(
        schema_name=schema_name,
        theme=theme,
        defaults={
            "shop": shop,
            "installed_version": theme.version,
            "schema_version": str(theme.metadata.get("theme_schema", {}).get("version", "")),
            "install_status": TenantInstalledTheme.InstallStatus.INSTALLED,
            "default_config": theme.metadata.get("default_config", {}),
            "removed_at": None,
        },
    )
    TenantThemeContent.objects.get_or_create(
        schema_name=schema_name,
        theme=theme,
        defaults={
            "shop": shop,
            "universal_content": {
                "name": getattr(shop, "name", ""),
                "bio": "",
                "profile_image": "",
                "social_links": [],
            },
            "theme_content": theme.metadata.get("default_config", {}),
        },
    )
    return installed


@transaction.atomic
def configure_theme_content_for_schema(
    schema_name: str,
    theme: Theme,
    *,
    universal_content: dict | None = None,
    theme_content: dict | None = None,
) -> TenantThemeContent:
    shop = get_shop_for_schema(schema_name)
    record, _ = TenantThemeContent.objects.get_or_create(
        schema_name=schema_name,
        theme=theme,
        defaults={"shop": shop, "universal_content": {}, "theme_content": {}},
    )
    if universal_content is not None:
        record.universal_content = universal_content
    if theme_content is not None:
        record.theme_content = theme_content
    if record.shop_id is None and shop is not None:
        record.shop = shop
    record.save()
    return record


def list_listed_themes():
    return Theme.objects.filter(
        is_internal=False,
        is_published=True,
        status=Theme.Status.APPROVED,
    ).select_related("category", "creator")


@transaction.atomic
def activate_theme_for_schema(
    schema_name: str,
    theme: Theme,
    *,
    actor=None,
    reason: str = "tenant_activation",
) -> TenantActiveTheme:
    access = TenantThemeAccess.objects.filter(schema_name=schema_name, theme=theme).first()
    if access is None:
        raise ValueError("This tenant does not have access to that theme.")
    if not access.is_active:
        raise ValueError("This tenant does not currently have access to that theme.")
    installed = TenantInstalledTheme.objects.filter(
        schema_name=schema_name,
        theme=theme,
        install_status=TenantInstalledTheme.InstallStatus.INSTALLED,
    ).first()
    if installed is None:
        raise ValueError("Install this theme before activating it.")

    shop = get_shop_for_schema(schema_name)
    active = TenantActiveTheme.objects.filter(schema_name=schema_name).select_related("theme").first()
    previous_theme = active.theme if active else None
    if active is None:
        active = TenantActiveTheme.objects.create(schema_name=schema_name, shop=shop, theme=theme)
    else:
        changed = []
        if active.theme_id != theme.id:
            active.theme = theme
            changed.append("theme")
        if active.shop_id is None and shop is not None:
            active.shop = shop
            changed.append("shop")
        if changed:
            active.save(update_fields=changed + ["updated_at"])

    ThemeSwitchLog.objects.create(
        shop=shop,
        schema_name=schema_name,
        from_theme=previous_theme,
        to_theme=theme,
        switched_by_user_id=str(getattr(actor, "pk", "") or ""),
        switched_by_email=getattr(actor, "email", "") or "",
        reason=reason,
    )
    clear_active_theme_cache(schema_name)
    return active


@transaction.atomic
def bootstrap_default_theme_for_schemas(schema_names: list[str] | None = None) -> dict[str, int]:
    theme = get_default_theme()
    if theme is None:
        sync_theme_catalog(actor=None, bootstrap_access=False)
        theme = get_default_theme()
    if theme is None:
        return {"checked": 0, "activated": 0, "already_active": 0, "failed": 0}

    checked = 0
    activated = 0
    already_active = 0
    failed = 0
    for schema_name in schema_names or _tenant_schema_names():
        normalized_schema = str(schema_name or "").strip()
        if not normalized_schema or normalized_schema == "public":
            continue
        checked += 1
        if has_active_theme_for_schema(normalized_schema):
            already_active += 1
            continue
        try:
            acquire_theme_for_schema(normalized_schema, theme)
            install_theme_for_schema(normalized_schema, theme)
            activate_theme_for_schema(normalized_schema, theme, reason="deployment_bootstrap")
            activated += 1
        except Exception:
            failed += 1
    return {
        "checked": checked,
        "activated": activated,
        "already_active": already_active,
        "failed": failed,
    }


@transaction.atomic
def deactivate_theme_for_schema(schema_name: str, *, actor=None, reason: str = "tenant_deactivation") -> TenantActiveTheme | None:
    active = TenantActiveTheme.objects.filter(schema_name=schema_name).select_related("theme").first()
    if active is None:
        return None
    previous_theme = active.theme
    shop = get_shop_for_schema(schema_name)
    active.delete()
    ThemeSwitchLog.objects.create(
        shop=shop,
        schema_name=schema_name,
        from_theme=previous_theme,
        to_theme=previous_theme,
        switched_by_user_id=str(getattr(actor, "pk", "") or ""),
        switched_by_email=getattr(actor, "email", "") or "",
        reason=reason,
    )
    clear_active_theme_cache(schema_name)
    return None


@transaction.atomic
def disable_installed_theme_for_schema(schema_name: str, theme: Theme) -> TenantInstalledTheme:
    installed = TenantInstalledTheme.objects.filter(schema_name=schema_name, theme=theme).first()
    if installed is None:
        raise ValueError("This theme is not installed.")
    installed.install_status = TenantInstalledTheme.InstallStatus.DISABLED
    installed.save(update_fields=["install_status", "updated_at"])
    active = TenantActiveTheme.objects.filter(schema_name=schema_name, theme=theme).first()
    if active:
        active.delete()
        clear_active_theme_cache(schema_name)
    return installed


@transaction.atomic
def remove_theme_for_schema(schema_name: str, theme: Theme) -> TenantInstalledTheme:
    installed = TenantInstalledTheme.objects.filter(schema_name=schema_name, theme=theme).first()
    if installed is None:
        raise ValueError("This theme is not installed.")
    installed.install_status = TenantInstalledTheme.InstallStatus.REMOVED
    installed.removed_at = timezone.now()
    installed.save(update_fields=["install_status", "removed_at", "updated_at"])
    TenantThemeAccess.objects.filter(schema_name=schema_name, theme=theme).update(
        is_active=False,
        revoked_at=timezone.now(),
        updated_at=timezone.now(),
    )
    active = TenantActiveTheme.objects.filter(schema_name=schema_name, theme=theme).first()
    if active:
        active.delete()
        clear_active_theme_cache(schema_name)
    return installed
