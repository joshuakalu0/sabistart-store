"""
system/account/schema_inspector.py
==================================
Lightweight, high-speed schema status inspector & migration chunk planner.

Designed for low-resource (1GB RAM) multi-tenant environments.
Inspects disk vs database migrations for tenant schemas, calculates exact
progress percentages, partitions pending migrations into memory-safe
micro-batches, and caches readiness status for 0ms middleware checks.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set, Tuple
from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)

CACHE_TTL_READY = 3600  # 1 hour cache for ready tenant schemas
CACHE_PREFIX = "tenant_ready_status"

# Micro-chunk stage definitions — TENANT-ONLY apps in strict dependency order.
# NOTE: contenttypes, auth, sessions, admin are in SHARED_APPS and are NOT included here.
# They are already applied to the public schema by django-tenants and must not be re-run.
STAGE_APP_MAPPINGS = [
    {
        "stage": 1,
        "key": "stage_1_user_auth",
        "name": "Tenant User Auth",
        "description": "Tenant staff authentication and user session structures.",
        "apps": ["userauth"],
    },
    {
        "stage": 2,
        "key": "stage_2_catalog_core",
        "name": "Store Catalog & Products",
        "description": "Categories, product catalog, variants, and inventory tracking.",
        "apps": ["category", "product"],
    },
    {
        "stage": 3,
        "key": "stage_3_cart_storefront",
        "name": "Cart & Storefront Operations",
        "description": "Shopping carts, checkout models, promotions, and visitor monitoring.",
        "apps": ["cart", "promotions", "search", "checkout", "monitoring"],
    },
    {
        "stage": 4,
        "key": "stage_4_store_settings",
        "name": "Store & Theme Settings",
        "description": "Storefront configuration, branding, and active theme settings.",
        "apps": ["store_settings", "categories_settings", "product_settings", "theme_manager"],
    },
    {
        "stage": 5,
        "key": "stage_5_notifications_pricing",
        "name": "Notifications & Multi-Currency",
        "description": "Notification delivery channels and multi-currency pricing engine.",
        "apps": ["notification", "pricing"],
    },
    {
        "stage": 6,
        "key": "stage_6_payments",
        "name": "Tenant Payment Gateways",
        "description": "Tenant-specific payment modes, payouts, and transaction ledgers.",
        "apps": ["payments_tenant"],
    },
    {
        "stage": 7,
        "key": "stage_7_pos_features",
        "name": "POS & Feature Marketplace",
        "description": "Point of Sale terminals, registers, and tenant feature entitlements.",
        "apps": ["pos", "feature_marketplace"],
    },
]


def _resolve_app_label(app_entry: str) -> str:
    """Resolve an app string from SHARED_APPS or TENANT_APPS to its registered AppConfig label."""
    for cfg in apps.get_app_configs():
        if cfg.name == app_entry or f"{cfg.__module__}.{cfg.__class__.__name__}" == app_entry or cfg.label == app_entry:
            return cfg.label
    return app_entry.split(".")[-1]


def get_tenant_app_labels() -> Set[str]:
    """
    Returns the set of Django app labels belonging exclusively to TENANT_APPS
    (excluding any app configured in SHARED_APPS).
    """
    shared_labels = {_resolve_app_label(entry) for entry in getattr(settings, "SHARED_APPS", [])}
    tenant_labels = {
        _resolve_app_label(entry)
        for entry in getattr(settings, "TENANT_APPS", [])
        if _resolve_app_label(entry) not in shared_labels
    }
    return tenant_labels



def get_disk_tenant_migrations() -> List[Tuple[str, str]]:
    """
    Returns all migrations defined on disk for tenant apps, ordered topologically
    by the true Django migration dependency graph. Does not require an active database connection.
    """
    from django.db.migrations.loader import MigrationLoader

    loader = MigrationLoader(None, ignore_no_migrations=True)
    loader.load_disk()

    tenant_labels = get_tenant_app_labels()
    tenant_leaves = [k for k in loader.graph.leaf_nodes() if k[0] in tenant_labels]

    ordered_plan: List[Tuple[str, str]] = []
    seen: Set[Tuple[str, str]] = set()

    for leaf in tenant_leaves:
        for target in loader.graph.forwards_plan(leaf):
            if target[0] in tenant_labels and target not in seen:
                seen.add(target)
                ordered_plan.append(target)

    # In case any orphaned migration was not reachable from leaf nodes:
    for key in loader.disk_migrations.keys():
        if key[0] in tenant_labels and key not in seen:
            seen.add(key)
            ordered_plan.append(key)

    return ordered_plan



def get_applied_tenant_migrations(schema_name: str) -> Set[Tuple[str, str]]:
    """
    Directly queries '{schema_name}'.django_migrations table to fetch applied migrations.
    Fast and bypasses full Django ORM loading.
    """
    schema_name = schema_name.strip().lower()
    if not schema_name:
        return set()

    try:
        with connection.cursor() as cursor:
            # Verify the django_migrations table exists in the tenant schema
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s AND table_name = 'django_migrations'
                LIMIT 1;
                """,
                [schema_name],
            )
            if not cursor.fetchone():
                return set()

            cursor.execute(f'SELECT app, name FROM "{schema_name}"."django_migrations";')
            rows = cursor.fetchall()
            return {(row[0], row[1]) for row in rows}
    except Exception as exc:
        logger.warning("[schema_inspector] Could not query applied migrations for %s: %s", schema_name, exc)
        return set()


def get_tenant_migration_status(schema_name: str, use_cache: bool = True) -> Dict[str, Any]:
    """
    Calculates detailed migration completion stats for a tenant schema.
    Returns:
        is_ready: bool
        total_migrations: int
        applied_count: int
        pending_count: int
        progress_percent: int (0 to 100)
        current_stage: dict
        pending_migrations: list of (app, name)
    """
    cache_key = f"{CACHE_PREFIX}:{schema_name}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None and cached.get("is_ready") is True:
            return cached

    disk_migrations = get_disk_tenant_migrations()
    total_count = len(disk_migrations)
    if total_count == 0:
        return {
            "is_ready": True,
            "total_migrations": 0,
            "applied_count": 0,
            "pending_count": 0,
            "progress_percent": 100,
            "current_stage": None,
            "pending_migrations": [],
        }

    applied_set = get_applied_tenant_migrations(schema_name)
    pending = [m for m in disk_migrations if m not in applied_set]
    applied_count = total_count - len(pending)
    progress_percent = int((applied_count / total_count) * 100) if total_count > 0 else 100
    is_ready = len(pending) == 0

    # Determine which stage is currently active
    current_stage = None
    if pending:
        first_pending_app = pending[0][0]
        for stage_info in STAGE_APP_MAPPINGS:
            if first_pending_app in stage_info["apps"]:
                current_stage = stage_info
                break
        if not current_stage:
            current_stage = {
                "stage": 9,
                "key": "stage_other",
                "name": "Additional Components",
                "description": f"Configuring {first_pending_app} module.",
                "apps": [first_pending_app],
            }

    result = {
        "is_ready": is_ready,
        "total_migrations": total_count,
        "applied_count": applied_count,
        "pending_count": len(pending),
        "progress_percent": progress_percent,
        "current_stage": current_stage,
        "pending_migrations": pending,
    }

    if is_ready:
        cache.set(cache_key, result, timeout=CACHE_TTL_READY)
    else:
        # Cache for a short duration while migrating
        cache.set(cache_key, result, timeout=3)

    return result


def is_tenant_ready(schema_name: str) -> bool:
    """Fast check whether a tenant schema has 0 pending migrations."""
    status = get_tenant_migration_status(schema_name, use_cache=True)
    return status.get("is_ready", False)


def invalidate_tenant_ready_cache(schema_name: str) -> None:
    """Invalidate cached status when migrations change."""
    cache.delete(f"{CACHE_PREFIX}:{schema_name}")


def plan_micro_chunks(schema_name: str, max_chunk_size: int = 1) -> List[Dict[str, Any]]:
    """
    Partitions all pending migrations for a schema into discrete micro-batches
    of maximum `max_chunk_size` migrations (default: 1 migration per chunk).
    """

    status = get_tenant_migration_status(schema_name, use_cache=False)
    pending = status["pending_migrations"]
    if not pending:
        return []

    chunks: List[Dict[str, Any]] = []

    # Map app to stage
    app_to_stage = {}
    for stage_info in STAGE_APP_MAPPINGS:
        for app in stage_info["apps"]:
            app_to_stage[app] = stage_info

    current_chunk_migrations: List[Tuple[str, str]] = []
    current_stage_key = None

    for app, name in pending:
        stage_info = app_to_stage.get(app, {
            "stage": 9,
            "key": "stage_other",
            "name": f"Module: {app}",
            "description": f"Configuring {app} tables.",
            "apps": [app],
        })

        # Start a new chunk if stage changes or chunk exceeds max_chunk_size
        if current_chunk_migrations and (
            len(current_chunk_migrations) >= max_chunk_size
            or current_stage_key != stage_info["key"]
        ):
            chunks.append({
                "stage_key": current_stage_key,
                "stage_name": current_chunk_migrations[0][0],
                "migrations": list(current_chunk_migrations),
                "apps": list({m[0] for m in current_chunk_migrations}),
            })
            current_chunk_migrations = []

        current_stage_key = stage_info["key"]
        current_chunk_migrations.append((app, name))

    if current_chunk_migrations:
        chunks.append({
            "stage_key": current_stage_key,
            "stage_name": current_chunk_migrations[0][0],
            "migrations": list(current_chunk_migrations),
            "apps": list({m[0] for m in current_chunk_migrations}),
        })

    return chunks
