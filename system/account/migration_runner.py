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

logger = logging.getLogger("sabistart.provisioning.chunked")

LOCK_PREFIX = "tenant_migration_lock"
LOCK_TTL = 900  # seconds — a single chunked run must never hold the lock longer
FAIL_COOLDOWN_PREFIX = "tenant_migration_fail_cooldown"

ProgressCallback = Callable[[Dict[str, Any], int, int, str], None]


class ChunkedMigrationError(Exception):
    """Raised when a migration chunk cannot be applied."""


# -----------------------------------------------------------------------------
# Locking — prevents two processes (CLI + web worker) migrating the same
# tenant schema concurrently.
# -----------------------------------------------------------------------------
def acquire_migration_lock(schema_name: str, timeout: int = LOCK_TTL) -> bool:
    try:
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
    with connection.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";')
    connection.set_schema_to_public()


def _set_schema(schema_name: str) -> None:
    """Point the shared connection at a tenant schema (django-tenants aware)."""
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

    for app_label, migration_name in migrations:
        if (app_label, migration_name) not in executor.loader.disk_migrations:
            raise ChunkedMigrationError(
                f"Migration '{app_label}.{migration_name}' was not found on disk."
            )
        _set_schema(schema_name)
        executor.loader.build_graph()
        executor.migrate([(app_label, migration_name)])


def run_chunked_tenant_migrations(
    schema_name: str,
    *,
    chunk_size: Optional[int] = None,
    max_chunks: Optional[int] = None,
    time_budget: Optional[float] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """
    Applies all (or a bounded number of) pending tenant migrations in
    dependency-ordered micro-chunks.

    Args:
        schema_name: Target tenant schema.
        chunk_size: Max migrations per chunk (default from settings / 4).
        max_chunks: Stop after this many chunks (None = no limit).
        time_budget: Stop cleanly after this many seconds (None = no limit).
            Stopping only ever happens *between* chunks, so state is consistent.
        progress_callback: ``callback(stage_info, applied_total, total, detail)``.

    Returns:
        dict with keys: completed, chunks_applied, migrations_applied,
        remaining, failed_at, stopped_reason.
    """
    schema_name = schema_name.strip().lower()
    if chunk_size is None:
        chunk_size = getattr(settings, "TENANT_PROVISIONING_CHUNK_SIZE", 4)

    result: Dict[str, Any] = {
        "schema_name": schema_name,
        "completed": False,
        "chunks_applied": 0,
        "migrations_applied": [],
        "remaining": 0,
        "failed_at": None,
        "stopped_reason": None,
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

            stage_info = _stage_info_for_app(chunk["migrations"][0][0])
            chunk_detail = ", ".join(f"{app}.{name}" for app, name in chunk["migrations"])
            logger.info(
                "[ChunkedRunner][%s] Chunk %d/%d (stage %s): applying %s",
                schema_name, index + 1, len(chunks), stage_info.get("key"), chunk_detail,
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
    """Persists live stage progress on Shop.provisioning_error (same format the poll UI parses)."""
    from system.core.models import Shop

    def callback(stage_info: Dict[str, Any], applied: int, total: int, detail: str = "") -> None:
        pct = int((applied / total) * 100) if total > 0 else 0
        stage_num = stage_info.get("stage", "?")
        msg = f"Stage {stage_num}/7: {stage_info.get('name', 'Migrating')} ({pct}% — {applied}/{total} applied)"
        if detail:
            msg += f" ▶ {detail}"
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
) -> Dict[str, Any]:
    """
    Advances a tenant toward READY by applying a bounded slice of pending
    migration chunks. Safe to call concurrently (cache lock) and repeatedly
    (each call resumes from the last applied migration file).

    Used by:
    - ``TenantProvisioningGuardMiddleware`` (on-login self-healing)
    - the provisioning status polling endpoint (waiting screen)
    - the platform admin retry action

    Returns:
        dict with keys: is_ready, failed, locked, cooldown, error, run.
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

    if not acquire_migration_lock(schema_name):
        logger.info("[ChunkedRunner] '%s' is already being migrated by another process.", schema_name)
        outcome["locked"] = True
        return outcome

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
            progress_callback=_shop_progress_writer(schema_name),
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
