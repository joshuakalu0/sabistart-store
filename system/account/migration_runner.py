"""
system/account/migration_runner.py
==================================
Celery-free, chunked tenant migration engine.

Designed for low-resource (1GB RAM) multi-tenant hosts. Instead of running a
single monolithic ``migrate_schemas`` inside a Celery worker, this module:

1. Partitions pending tenant migrations into dependency-ordered micro-chunks
   (via ``schema_inspector.plan_micro_chunks``).
2. Applies each chunk with Django's ``MigrationExecutor`` — every migration
   commits in its own transaction, so database locks are held only briefly.
3. Releases the database connection and runs ``gc.collect()`` between chunks
   so PostgreSQL backend memory is reclaimed on small instances.
4. Stops cleanly when a time budget / chunk budget is exhausted, making it
   safe to call from middleware, polling endpoints, or the CLI command
   ``manage.py run_tenant_chunked_migrations``.
5. Records a failure checkpoint so any retry (CLI, login guard, or poll)
   resumes from the exact last successfully applied migration file.

No Celery, no threads, no subprocesses — everything runs synchronously in
bounded micro-steps.
"""

from __future__ import annotations

import gc
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from django.conf import settings
from django.core.cache import cache
from django.db import connection

from system.account.schema_inspector import (
    STAGE_APP_MAPPINGS,
    get_tenant_migration_status,
    invalidate_tenant_ready_cache,
    plan_micro_chunks,
)
from system.account.throttler import AdaptiveThrottler, SystemHealthReport, default_throttler

logger = logging.getLogger("sabistart.provisioning.chunked")

LOCK_PREFIX = "tenant_migration_lock"
LOCK_TTL = 25  # seconds — short TTL so interrupted processes never lock up schemas
FAIL_COOLDOWN_PREFIX = "tenant_migration_fail_cooldown"

ProgressCallback = Callable[[Dict[str, Any], int, int, str], None]


class ChunkedMigrationError(Exception):
    """Raised when a migration chunk cannot be applied."""


# -----------------------------------------------------------------------------
# Locking — prevents two processes (CLI + web worker) migrating the same
# tenant schema concurrently.
# -----------------------------------------------------------------------------
def acquire_migration_lock(schema_name: str, timeout: int = LOCK_TTL, force: bool = False) -> bool:
    try:
        if force:
            cache.delete(f"{LOCK_PREFIX}:{schema_name}")
            cache.set(f"{LOCK_PREFIX}:{schema_name}", os.getpid(), timeout=timeout)
            return True
        return bool(cache.add(f"{LOCK_PREFIX}:{schema_name}", os.getpid(), timeout=timeout))
    except Exception as exc:  # cache backend unavailable — degrade gracefully
        logger.warning("[ChunkedRunner] Cache lock unavailable for '%s': %s", schema_name, exc)
        return True


def release_migration_lock(schema_name: str) -> None:
    try:
        cache.delete(f"{LOCK_PREFIX}:{schema_name}")
    except Exception:
        pass


def set_failure_cooldown(schema_name: str, timeout: Optional[int] = None) -> None:
    """Short cooldown after a chunk failure so failing tenants are not retried on every request."""
    ttl = timeout if timeout is not None else getattr(settings, "TENANT_PROVISIONING_FAIL_COOLDOWN", 60)
    try:
        cache.set(f"{FAIL_COOLDOWN_PREFIX}:{schema_name}", "1", timeout=max(5, int(ttl)))
    except Exception:
        pass


def in_failure_cooldown(schema_name: str) -> bool:
    try:
        return bool(cache.get(f"{FAIL_COOLDOWN_PREFIX}:{schema_name}"))
    except Exception:
        return False


def clear_failure_cooldown(schema_name: str) -> None:
    try:
        cache.delete(f"{FAIL_COOLDOWN_PREFIX}:{schema_name}")
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Schema helpers
# -----------------------------------------------------------------------------
def _ensure_schema_exists(schema_name: str) -> None:
    """
    Ensures the PostgreSQL schema and django_migrations table exist.
    Pre-populates shared apps migration records from the public schema so Django's
    migration dependency resolver recognizes shared dependencies (like auth.0012, contenttypes.0002)
    as already satisfied, allowing tenant-only migrations to execute instantly.
    """
    try:
        if connection.connection is not None:
            if getattr(connection.connection, "closed", False):
                connection.connection = None
            elif not connection.get_autocommit():
                connection.rollback()
    except Exception:
        connection.connection = None

    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";')
        # Ensure django_migrations table exists in the tenant schema
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS "{schema_name}"."django_migrations" (
                id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                app character varying(255) NOT NULL,
                name character varying(255) NOT NULL,
                applied timestamp with time zone NOT NULL
            );
        """)
        # Pre-seed shared apps migrations from public so cross-schema dependencies don't block tenant migrations
        cursor.execute(f"""
            INSERT INTO "{schema_name}"."django_migrations" (app, name, applied)
            SELECT p.app, p.name, p.applied
            FROM "public"."django_migrations" p
            WHERE p.app NOT IN (
                'userauth', 'category', 'product', 'cart', 'promotions',
                'search', 'checkout', 'store_settings', 'categories_settings',
                'product_settings', 'theme_manager', 'notification',
                'pricing', 'payments_tenant', 'pos', 'b2b', 'content',
                'shipping', 'support', 'legal', 'i18n', 'home'
            )
            AND NOT EXISTS (
                SELECT 1 FROM "{schema_name}"."django_migrations" t
                WHERE t.app = p.app AND t.name = p.name
            );
        """)
    connection.set_schema_to_public()


def _set_schema(schema_name: str) -> None:
    """Point the shared connection at a tenant schema (django-tenants aware)."""
    try:
        if connection.connection is not None and getattr(connection.connection, "closed", False):
            connection.connection = None
    except Exception:
        connection.connection = None

    if hasattr(connection, "set_schema"):
        connection.set_schema(schema_name)
    else:  # pragma: no cover — fallback for plain backends
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema_name}";')


def _release_connection() -> None:
    """
    Force-release the DB connection between chunks so the PostgreSQL backend
    memory is freed on small (1GB RAM) instances.
    """
    try:
        connection.set_schema_to_public()
    except Exception:
        pass
    try:
        connection.close()
    except Exception:
        pass
    connection.connection = None
    gc.collect()



def _stage_info_for_app(app_label: str) -> Dict[str, Any]:
    for stage_info in STAGE_APP_MAPPINGS:
        if app_label in stage_info["apps"]:
            return stage_info
    return {
        "stage": 9,
        "key": "stage_other",
        "name": f"Module: {app_label}",
        "description": f"Configuring {app_label} tables.",
        "apps": [app_label],
    }


# -----------------------------------------------------------------------------
# Core chunk executor
# -----------------------------------------------------------------------------
def _apply_chunk(schema_name: str, migrations: List[Tuple[str, str]]) -> None:
    """
    Applies one micro-chunk of migrations to the tenant schema.

    Django applies each migration inside its own atomic block, so every
    migration file commits individually — database lock times stay minimal
    and a failure mid-chunk leaves a clean, resumable state.
    """
    from django.db.migrations.executor import MigrationExecutor

    _set_schema(schema_name)
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()

    for app_label, migration_name in migrations:
        if (app_label, migration_name) not in executor.loader.disk_migrations:
            raise ChunkedMigrationError(
                f"Migration '{app_label}.{migration_name}' was not found on disk."
            )
        if (app_label, migration_name) in executor.loader.applied_migrations:
            logger.info("[ChunkedRunner][%s] Skipping already-applied %s.%s", schema_name, app_label, migration_name)
            continue
        logger.info("[ChunkedRunner][%s] Applying migration %s.%s...", schema_name, app_label, migration_name)
        try:
            _set_schema(schema_name)
            executor.migrate([(app_label, migration_name)])
        except Exception as exc:
            try:
                if not connection.get_autocommit():
                    connection.rollback()
            except Exception:
                pass
            err_str = str(exc).lower()
            # DDL already applied (column/table/index exists) but migration not recorded
            # — fake-record it and continue so the runner isn't permanently blocked
            if any(phrase in err_str for phrase in (
                "already exists", "duplicate column", "duplicate table",
                "duplizierter schlüssel",
            )):
                logger.warning(
                    "[ChunkedRunner][%s] DDL for %s.%s already in DB (%s) — faking as applied.",
                    schema_name, app_label, migration_name, type(exc).__name__,
                )
                _set_schema(schema_name)
                from django.db.migrations.recorder import MigrationRecorder
                recorder = MigrationRecorder(connection)
                recorder.record_applied(app_label, migration_name)
            else:
                raise
        logger.info("[ChunkedRunner][%s] ✓ Applied %s.%s", schema_name, app_label, migration_name)




def run_chunked_tenant_migrations(
    schema_name: str,
    *,
    chunk_size: Optional[int] = None,
    max_chunks: Optional[int] = None,
    time_budget: Optional[float] = None,
    progress_callback: Optional[ProgressCallback] = None,
    throttler: Optional[AdaptiveThrottler] = None,
) -> Dict[str, Any]:
    """
    Applies all (or a bounded number of) pending tenant migrations in
    dependency-ordered micro-chunks with dynamic CPU & RAM throttling.

    Args:
        schema_name: Target tenant schema.
        chunk_size: Max migrations per chunk (default from settings / 4).
        max_chunks: Stop after this many chunks (None = no limit).
        time_budget: Stop cleanly after this many seconds (None = no limit).
            Stopping only ever happens *between* chunks, so state is consistent.
        progress_callback: ``callback(stage_info, applied_total, total, detail)``.
        throttler: Optional custom AdaptiveThrottler instance.

    Returns:
        dict with keys: completed, chunks_applied, migrations_applied,
        remaining, failed_at, stopped_reason, system_health.
    """
    schema_name = schema_name.strip().lower()
    if chunk_size is None:
        chunk_size = getattr(settings, "TENANT_PROVISIONING_CHUNK_SIZE", 4)

    active_throttler = throttler if throttler is not None else default_throttler

    result: Dict[str, Any] = {
        "schema_name": schema_name,
        "completed": False,
        "chunks_applied": 0,
        "migrations_applied": [],
        "remaining": 0,
        "failed_at": None,
        "stopped_reason": None,
        "system_health": None,
    }

    _ensure_schema_exists(schema_name)

    chunks = plan_micro_chunks(schema_name, max_chunk_size=max(1, int(chunk_size)))
    if not chunks:
        result["completed"] = True
        result["stopped_reason"] = "already_up_to_date"
        invalidate_tenant_ready_cache(schema_name)
        return result

    status = get_tenant_migration_status(schema_name, use_cache=False)
    total_migrations = status["total_migrations"]
    applied_total = status["applied_count"]

    started_at = time.monotonic()

    try:
        for index, chunk in enumerate(chunks):
            # ── Bounded execution: stop cleanly between chunks ─────────────
            if max_chunks is not None and index >= max_chunks:
                result["stopped_reason"] = "max_chunks"
                break
            if time_budget is not None and (time.monotonic() - started_at) >= float(time_budget):
                result["stopped_reason"] = "time_budget"
                break

            # ── Adaptive CPU & RAM Throttling Check ────────────────────────
            backoff_timeout = getattr(settings, "TENANT_MIGRATION_BACKOFF_TIMEOUT", 10.0)
            health_report: SystemHealthReport = active_throttler.throttle_before_chunk(
                max_backoff_seconds=float(backoff_timeout),
                custom_logger=logger,
            )
            result["system_health"] = health_report.to_dict()

            if not health_report.is_safe_to_proceed:
                logger.warning(
                    "[ChunkedRunner][%s] Pausing chunk execution due to critical system load (CPU %.1f%%, RAM %.1f%%).",
                    schema_name, health_report.cpu_percent, health_report.ram_percent,
                )
                result["stopped_reason"] = "cpu_throttled_critical"
                break

            stage_info = _stage_info_for_app(chunk["migrations"][0][0])
            chunk_detail = ", ".join(f"{app}.{name}" for app, name in chunk["migrations"])
            logger.info(
                "[ChunkedRunner][%s] Chunk %d/%d (stage %s) [CPU: %.1f%% | RAM: %.1f%% -> %s]: applying %s",
                schema_name, index + 1, len(chunks), stage_info.get("key"),
                health_report.cpu_percent, health_report.ram_percent, health_report.status,
                chunk_detail,
            )

            try:
                _apply_chunk(schema_name, chunk["migrations"])
            except Exception as exc:
                failing_app, failing_name = chunk["migrations"][0]
                checkpoint = {
                    "stage_key": stage_info.get("key"),
                    "stage_name": stage_info.get("name"),
                    "app": failing_app,
                    "migration": failing_name,
                    "chunk": chunk_detail,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                result["failed_at"] = checkpoint
                result["stopped_reason"] = "failed"
                logger.exception(
                    "[ChunkedRunner][%s] Chunk FAILED at '%s.%s' — checkpoint recorded: %s",
                    schema_name, failing_app, failing_name, checkpoint["error"],
                )
                break

            result["chunks_applied"] += 1
            result["migrations_applied"].extend(chunk["migrations"])
            applied_total += len(chunk["migrations"])

            # Progress reporting happens on the public schema, between chunks.
            connection.set_schema_to_public()
            if progress_callback is not None:
                try:
                    progress_callback(stage_info, applied_total, total_migrations, chunk_detail)
                except Exception:
                    logger.debug("[ChunkedRunner] Progress callback failed (ignored).", exc_info=True)

            # ── Memory hygiene: release the DB connection between chunks ───
            _release_connection()

        # Final state inspection
        _ensure_schema_exists(schema_name)
        final_status = get_tenant_migration_status(schema_name, use_cache=False)
        result["remaining"] = final_status["pending_count"]
        result["completed"] = final_status["is_ready"]
        if result["completed"]:
            result["stopped_reason"] = "completed"
            invalidate_tenant_ready_cache(schema_name)
    finally:
        _release_connection()

    return result


# -----------------------------------------------------------------------------
# High-level provisioning step (lock + status + entitlements + READY flag)
# -----------------------------------------------------------------------------
def _shop_progress_writer(schema_name: str) -> ProgressCallback:
    """Persists live migration progress on Shop.provisioning_error (e.g. Migration 1/54: userauth.0001_initial)."""
    from system.core.models import Shop

    def callback(stage_info: Dict[str, Any], applied: int, total: int, detail: str = "") -> None:
        pct = int((applied / total) * 100) if total > 0 else 0
        msg = f"Migration {applied}/{total} ({pct}%): {detail}"
        try:
            connection.set_schema_to_public()
            Shop.objects.filter(schema_name=schema_name).update(provisioning_error=msg[:2900])
        except Exception:
            pass

    return callback


def advance_tenant_provisioning(
    schema_name: str,
    *,
    time_budget: Optional[float] = None,
    max_chunks: Optional[int] = None,
    chunk_size: Optional[int] = None,
    session_id: Optional[str] = None,
    source: str = "unknown",
    throttler: Optional[AdaptiveThrottler] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """
    Advances a tenant toward READY by applying a bounded slice of pending
    migration chunks (1 migration by 1 migration by default).
    Safe to call concurrently (cache lock) and repeatedly.
    """
    schema_name = (schema_name or "").strip().lower()
    outcome: Dict[str, Any] = {
        "schema_name": schema_name,
        "is_ready": False,
        "failed": False,
        "locked": False,
        "cooldown": False,
        "error": "",
        "run": None,
    }
    if not schema_name:
        return outcome

    from system.core.models import Shop
    from system.account.models import OnboardingSession

    shop = Shop.objects.filter(schema_name=schema_name).first()

    # Fast path: migrations already fully applied
    status = get_tenant_migration_status(schema_name, use_cache=False)
    if status["is_ready"]:
        _finalize_ready(shop)
        outcome["is_ready"] = True
        return outcome

    # A deterministically failing chunk should not be retried on every request.
    if in_failure_cooldown(schema_name):
        outcome["cooldown"] = True
        outcome["error"] = shop.provisioning_error if shop else ""
        return outcome

    # Always claim the lock for this invocation.
    acquire_migration_lock(schema_name, force=True)

    shop_cb = _shop_progress_writer(schema_name)
    def combined_callback(stage_info: Dict[str, Any], applied: int, total: int, detail: str = "") -> None:
        shop_cb(stage_info, applied, total, detail)
        if progress_callback is not None:
            try:
                progress_callback(stage_info, applied, total, detail)
            except Exception:
                logger.debug("[ChunkedRunner] Custom progress callback error (ignored).", exc_info=True)

    try:
        if shop and shop.provisioning_status != Shop.ProvisioningStatus.IN_PROGRESS:
            shop.provisioning_status = Shop.ProvisioningStatus.IN_PROGRESS
            shop.provisioning_error = shop.provisioning_error or "Starting tenant migrations..."
            shop.save(update_fields=["provisioning_status", "provisioning_error"])

        run = run_chunked_tenant_migrations(
            schema_name,
            chunk_size=chunk_size,
            max_chunks=max_chunks,
            time_budget=time_budget,
            progress_callback=combined_callback,
            throttler=throttler,
        )
        outcome["run"] = run


        # ── Failure: record checkpoint so retries resume from this file ─────
        if run["failed_at"]:
            checkpoint = run["failed_at"]
            fail_msg = (
                f"FAILED_CHUNK at {checkpoint['app']}.{checkpoint['migration']} "
                f"(stage: {checkpoint['stage_name']}) — resume point recorded. "
                f"Error: {checkpoint['error']}"
            )
            if shop:
                shop.provisioning_status = Shop.ProvisioningStatus.FAILED
                shop.provisioning_error = fail_msg[:2900]
                shop.save(update_fields=["provisioning_status", "provisioning_error"])
            set_failure_cooldown(schema_name)
            outcome["failed"] = True
            outcome["error"] = fail_msg
            return outcome

        # ── Completed: grant entitlements & flip tenant to READY ────────────
        if run["completed"]:
            session = None
            if session_id:
                session = OnboardingSession.objects.filter(id=session_id).first()
            elif shop:
                session = (
                    OnboardingSession.objects.filter(metadata__tenant_schema_name=schema_name)
                    .exclude(status__in=[
                        OnboardingSession.Status.COMPLETED,
                        OnboardingSession.Status.CANCELLED,
                    ])
                    .order_by("-updated_at")
                    .first()
                )

            if session and shop:
                try:
                    from system.account.services import TenantService
                    TenantService.provision_tenant_entitlements(session, shop)
                except Exception as exc:
                    logger.exception(
                        "[ChunkedRunner] Entitlement provisioning failed for '%s' (schema is ready): %s",
                        schema_name, exc,
                    )

            if shop and shop.owner:
                try:
                    from system.account.sso import ensure_tenant_admin_user, TenantSchemaNotReady
                    ensure_tenant_admin_user(shop, shop.owner)
                except TenantSchemaNotReady as admin_err:
                    logger.warning("[ChunkedRunner] Tenant schema not ready for admin user '%s': %s", schema_name, admin_err)
                    outcome["is_ready"] = False
                    outcome["error"] = str(admin_err)
                    return outcome
                except Exception as admin_err:
                    logger.warning("[ChunkedRunner] Could not provision tenant admin user for '%s': %s", schema_name, admin_err)

            # ── Seed default theme + singleton settings ───────────────────────
            try:
                _seed_tenant_defaults(schema_name)
            except Exception as seed_exc:
                logger.warning(
                    "[ChunkedRunner] Tenant defaults seeding failed for '%s' (non-fatal): %s",
                    schema_name, seed_exc,
                )

            _finalize_ready(shop)
            invalidate_tenant_ready_cache(schema_name)


            if session:
                try:
                    from django.utils import timezone
                    metadata = dict(session.metadata or {})
                    metadata["tenant_schema_name"] = schema_name
                    metadata["provisioned_at"] = timezone.now().isoformat()
                    metadata["provisioning_source"] = source
                    session.status = OnboardingSession.Status.COMPLETED
                    session.completed_at = timezone.now()
                    session.metadata = metadata
                    session.save(update_fields=["status", "completed_at", "metadata", "updated_at"])
                except Exception:
                    logger.debug("[ChunkedRunner] Could not finalize onboarding session.", exc_info=True)

            logger.info("[ChunkedRunner] Tenant '%s' is fully provisioned (source=%s).", schema_name, source)
            outcome["is_ready"] = True
            return outcome


        # ── Budget exhausted: tenant stays IN_PROGRESS for the next pass ────
        logger.info(
            "[ChunkedRunner] '%s' partial pass finished (source=%s, reason=%s, remaining=%d).",
            schema_name, source, run.get("stopped_reason"), run.get("remaining", 0),
        )
        return outcome
    finally:
        release_migration_lock(schema_name)
        _release_connection()


def _seed_tenant_defaults(schema_name: str) -> None:
    """
    Run once after all tenant migrations complete to ensure the tenant schema
    has every required default record so the storefront and dashboard work
    out-of-the-box without any manual configuration step.

    Covers:
    1. Default theme — acquires, installs, and activates the built-in default
       theme so the storefront renders immediately.
    2. Singleton settings — creates StoreSettings, HeaderSettings,
       FooterSettings, HomepageLayout, ProductDisplaySettings,
       CheckoutSettings, SearchSettings, SocialMediaLinks, and the rest of
       the singleton setting rows if they are missing.
    """
    from django_tenants.utils import schema_context

    logger.info("[Seed] Seeding tenant defaults for schema '%s'.", schema_name)

    # ── 1. Default theme ─────────────────────────────────────────────────────
    try:
        from system.theme_marketplace.services import (
            bootstrap_default_theme_for_schemas,
            sync_theme_catalog,
            get_default_theme,
        )
        # Ensure the default theme record exists in the public catalogue.
        if get_default_theme() is None:
            sync_theme_catalog(actor=None, bootstrap_access=False)

        result = bootstrap_default_theme_for_schemas([schema_name])
        logger.info(
            "[Seed] Theme bootstrap for '%s': activated=%d, already_active=%d, failed=%d",
            schema_name,
            result.get("activated", 0),
            result.get("already_active", 0),
            result.get("failed", 0),
        )
    except Exception as exc:
        logger.warning("[Seed] Could not bootstrap default theme for '%s': %s", schema_name, exc)

    # ── 2. Singleton settings ─────────────────────────────────────────────────
    try:
        with schema_context(schema_name):
            _create_singleton_settings(schema_name)
    except Exception as exc:
        logger.warning("[Seed] Could not seed singleton settings for '%s': %s", schema_name, exc)


def _create_singleton_settings(schema_name: str) -> None:
    """Create all singleton settings records inside the active tenant schema context."""
    try:
        from dashboard.store_settings.models.store_settings import StoreSettings
        if not StoreSettings.objects.exists():
            StoreSettings.objects.create(
                store_name=f"Store - {schema_name}",
                contact_email="contact@example.com",
            )
            logger.info("[Seed] ✓ Created StoreSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] StoreSettings: %s", exc)

    try:
        from dashboard.store_settings.models.theme_settings import ThemeSettings
        if not ThemeSettings.objects.exists():
            ThemeSettings.objects.create(theme_name="Default Theme", is_active=True)
            logger.info("[Seed] ✓ Created ThemeSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] ThemeSettings: %s", exc)

    try:
        from dashboard.store_settings.models.header_settings import HeaderSettings
        if not HeaderSettings.objects.exists():
            HeaderSettings.objects.create()
            logger.info("[Seed] ✓ Created HeaderSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] HeaderSettings: %s", exc)

    try:
        from dashboard.store_settings.models.footer_settings import FooterSettings
        if not FooterSettings.objects.exists():
            FooterSettings.objects.create()
            logger.info("[Seed] ✓ Created FooterSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] FooterSettings: %s", exc)

    try:
        from dashboard.store_settings.models.homepage_layout import HomepageLayout
        if not HomepageLayout.objects.exists():
            HomepageLayout.objects.create()
            logger.info("[Seed] ✓ Created HomepageLayout for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] HomepageLayout: %s", exc)

    try:
        from dashboard.store_settings.models.product_display_settings import ProductDisplaySettings
        if not ProductDisplaySettings.objects.exists():
            ProductDisplaySettings.objects.create()
            logger.info("[Seed] ✓ Created ProductDisplaySettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] ProductDisplaySettings: %s", exc)

    try:
        from dashboard.store_settings.models.product_page_settings import ProductPageSettings
        if not ProductPageSettings.objects.exists():
            ProductPageSettings.objects.create()
            logger.info("[Seed] ✓ Created ProductPageSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] ProductPageSettings: %s", exc)

    try:
        from dashboard.store_settings.models.cart_settings import CartSettings
        if not CartSettings.objects.exists():
            CartSettings.objects.create()
            logger.info("[Seed] ✓ Created CartSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] CartSettings: %s", exc)

    try:
        from dashboard.store_settings.models.checkout_settings import CheckoutSettings
        if not CheckoutSettings.objects.exists():
            CheckoutSettings.objects.create()
            logger.info("[Seed] ✓ Created CheckoutSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] CheckoutSettings: %s", exc)

    try:
        from dashboard.store_settings.models.search_settings import SearchSettings
        if not SearchSettings.objects.exists():
            SearchSettings.objects.create()
            logger.info("[Seed] ✓ Created SearchSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] SearchSettings: %s", exc)

    try:
        from dashboard.store_settings.models.email_template_settings import EmailTemplateSettings
        if not EmailTemplateSettings.objects.exists():
            EmailTemplateSettings.objects.create()
            logger.info("[Seed] ✓ Created EmailTemplateSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] EmailTemplateSettings: %s", exc)

    try:
        from dashboard.store_settings.models.social_media_links import SocialMediaLinks
        if not SocialMediaLinks.objects.exists():
            SocialMediaLinks.objects.create()
            logger.info("[Seed] ✓ Created SocialMediaLinks for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] SocialMediaLinks: %s", exc)

    try:
        from dashboard.store_settings.models.notification_settings import NotificationSettings
        if not NotificationSettings.objects.exists():
            NotificationSettings.objects.create()
            logger.info("[Seed] ✓ Created NotificationSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] NotificationSettings: %s", exc)

    try:
        from dashboard.store_settings.models.mobile_app_settings import MobileAppSettings
        if not MobileAppSettings.objects.exists():
            MobileAppSettings.objects.create(app_name=f"Store App - {schema_name}")
            logger.info("[Seed] ✓ Created MobileAppSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] MobileAppSettings: %s", exc)

    try:
        from dashboard.store_settings.models.blog_settings import BlogSettings
        if not BlogSettings.objects.exists():
            BlogSettings.objects.create()
            logger.info("[Seed] ✓ Created BlogSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] BlogSettings: %s", exc)

    try:
        from dashboard.store_settings.models.popup_settings import PopupSettings
        if not PopupSettings.objects.exists():
            PopupSettings.objects.create()
            logger.info("[Seed] ✓ Created PopupSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] PopupSettings: %s", exc)

    try:
        from dashboard.store_settings.models.performance_settings import PerformanceSettings
        if not PerformanceSettings.objects.exists():
            PerformanceSettings.objects.create()
            logger.info("[Seed] ✓ Created PerformanceSettings for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] PerformanceSettings: %s", exc)

    try:
        from dashboard.store_settings.models.navigation import NavigationMenu
        if not NavigationMenu.objects.filter(location="header").exists():
            NavigationMenu.objects.create(name="Main Menu", location="header", is_active=True)
            logger.info("[Seed] ✓ Created default navigation menu for '%s'", schema_name)
    except Exception as exc:
        logger.warning("[Seed] NavigationMenu: %s", exc)

    logger.info("[Seed] ✅ Singleton settings seeding complete for '%s'.", schema_name)


def _finalize_ready(shop) -> None:
    from django.utils import timezone
    from system.core.models import Shop

    if shop is None:
        return
    if shop.provisioning_status != Shop.ProvisioningStatus.READY:
        shop.provisioning_status = Shop.ProvisioningStatus.READY
        shop.provisioning_error = ""
        shop.provisioned_at = timezone.now()
        shop.save(update_fields=["provisioning_status", "provisioning_error", "provisioned_at"])
