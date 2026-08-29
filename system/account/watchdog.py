"""
system/account/watchdog.py
==========================
Guiding Watchdog Service for Tenant Migrations (Dual-Engine)

1. Dispatches Celery migration tasks if ENABLE_CELERY_MIGRATIONS=True.
2. Monitors Celery progress heartbeats to detect silent hangs such as dying/leaking
   workers or deadlocks on 1GB RAM systems.
3. Forcibly revokes stalled Celery tasks and seamlessly transfers execution to the
   local CPU-aware chunked runner.
4. Falls back to local runner immediately if Celery broker is down or throws an error.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("sabistart.provisioning.watchdog")

WATCHDOG_KEY_PREFIX = "celery_migration_watchdog"
DEFAULT_STALL_TIMEOUT = 40.0


def get_celery_watchdog_state(schema_name: str) -> Optional[Dict[str, Any]]:
    try:
        return cache.get(f"{WATCHDOG_KEY_PREFIX}:{schema_name}")
    except Exception:
        return None


def revoke_celery_task(task_id: str) -> None:
    if not task_id:
        return
    try:
        from sabistart.celery import app
        app.control.revoke(task_id, terminate=True, signal="SIGKILL")
        logger.warning("[Watchdog] Revoked Celery task %s via SIGKILL.", task_id)
    except Exception as exc:
        logger.debug("[Watchdog] Could not revoke Celery task %s: %s", task_id, exc)


def kill_existing_migration_process(schema_name: str) -> None:
    """
    Kills any existing Celery task, clears stale locks, and resets watchdog state
    when a user refreshes or re-enters an unfinished migration page.
    """
    schema_name = (schema_name or "").strip().lower()
    if not schema_name:
        return

    from system.account.migration_runner import clear_failure_cooldown, release_migration_lock

    watchdog = get_celery_watchdog_state(schema_name)
    if watchdog:
        task_id = watchdog.get("task_id", "")
        if task_id:
            revoke_celery_task(task_id)
        try:
            cache.delete(f"{WATCHDOG_KEY_PREFIX}:{schema_name}")
        except Exception:
            pass

    release_migration_lock(schema_name)
    clear_failure_cooldown(schema_name)
    logger.info("[Watchdog] User refresh/reconnect: killed existing migration processes and reset state for '%s'.", schema_name)


def execute_tenant_migrations_with_watchdog(

    schema_name: str,
    *,
    time_budget: Optional[float] = None,
    max_chunks: Optional[int] = None,
    chunk_size: Optional[int] = None,
    session_id: Optional[str] = None,
    source: str = "poll_endpoint",
) -> Dict[str, Any]:
    """
    Main entry point for Dual-Engine Tenant Migration Execution.

    1. If ENABLE_CELERY_MIGRATIONS=False: Executes directly via local CPU-aware runner.
    2. If ENABLE_CELERY_MIGRATIONS=True: Dispatches Celery task, monitors heartbeat,
       and AUTOMATICALLY FALLS BACK to local runner upon silent hang or broker failure.
    """
    schema_name = (schema_name or "").strip().lower()
    if not schema_name:
        return {"schema_name": "", "is_ready": False, "engine": "none"}

    enable_celery = getattr(settings, "ENABLE_CELERY_MIGRATIONS", False)
    stall_timeout = float(getattr(settings, "CELERY_MIGRATION_STALL_TIMEOUT", DEFAULT_STALL_TIMEOUT))

    from system.account.migration_runner import advance_tenant_provisioning

    # Case 1: Celery is Disabled — Execute locally
    if not enable_celery:
        result = advance_tenant_provisioning(
            schema_name,
            time_budget=time_budget,
            max_chunks=max_chunks,
            chunk_size=chunk_size,
            session_id=session_id,
            source=source,
        )
        result["engine"] = "local_direct"
        return result

    # Case 2: Celery is Enabled — Check watchdog status
    watchdog = get_celery_watchdog_state(schema_name)
    now = time.time()

    if watchdog:
        status = watchdog.get("status")
        task_id = watchdog.get("task_id", "")
        last_heartbeat = float(watchdog.get("last_heartbeat_at", now))
        elapsed = now - last_heartbeat

        # ── Sub-case A: Task is DISPATCHED but worker hasn't picked it up in 12s ──
        if status == "DISPATCHED":
            if elapsed > 12.0:
                logger.warning(
                    "[Watchdog] Celery worker did not pick up task %s for '%s' after %.1fs (Celery worker offline or busy). Triggering automatic local fallback.",
                    task_id, schema_name, elapsed,
                )
                revoke_celery_task(task_id)
                watchdog["status"] = "FALLBACK"
                try:
                    cache.set(f"{WATCHDOG_KEY_PREFIX}:{schema_name}", watchdog, timeout=600)
                except Exception:
                    pass

                result = advance_tenant_provisioning(
                    schema_name,
                    time_budget=time_budget,
                    max_chunks=max_chunks,
                    chunk_size=chunk_size,
                    session_id=session_id,
                    source="celery_offline_fallback",
                )
                result["engine"] = "celery_offline_fallback"
                result["worker_offline"] = True
                return result
            else:
                # Still within 12s pickup grace period — do NOT dispatch duplicate tasks!
                return {
                    "schema_name": schema_name,
                    "is_ready": False,
                    "engine": "celery_waiting_pickup",
                    "task_id": task_id,
                    "watchdog": watchdog,
                }

        # ── Sub-case B: Task is RUNNING in Celery ─────────────────────────────
        elif status == "RUNNING":
            if elapsed > stall_timeout:
                logger.warning(
                    "[Watchdog] Celery execution STALLED for '%s' (no heartbeat for %.1fs > %.1fs). Revoking task %s and triggering automatic local fallback.",
                    schema_name, elapsed, stall_timeout, task_id,
                )
                revoke_celery_task(task_id)
                watchdog["status"] = "STALLED"
                try:
                    cache.set(f"{WATCHDOG_KEY_PREFIX}:{schema_name}", watchdog, timeout=600)
                except Exception:
                    pass

                result = advance_tenant_provisioning(
                    schema_name,
                    time_budget=time_budget,
                    max_chunks=max_chunks,
                    chunk_size=chunk_size,
                    session_id=session_id,
                    source="celery_stall_fallback",
                )
                result["engine"] = "celery_stall_fallback"
                result["stall_detected"] = True
                return result
            else:
                from system.account.schema_inspector import get_tenant_migration_status
                mig_status = get_tenant_migration_status(schema_name, use_cache=False)
                return {
                    "schema_name": schema_name,
                    "is_ready": mig_status["is_ready"],
                    "failed": False,
                    "locked": False,
                    "cooldown": False,
                    "error": "",
                    "engine": "celery_active",
                    "watchdog": watchdog,
                }

        # ── Sub-case C: Already in FALLBACK or STALLED mode ────────────────────
        elif status in {"FALLBACK", "STALLED"}:
            result = advance_tenant_provisioning(
                schema_name,
                time_budget=time_budget,
                max_chunks=max_chunks,
                chunk_size=chunk_size,
                session_id=session_id,
                source="local_fallback_resume",
            )
            result["engine"] = "local_fallback_resume"
            return result

    # No active Celery task — dispatch once and record state in Redis
    try:
        from system.account.tasks import (
            record_watchdog_heartbeat,
            run_chunked_tenant_migrations_celery_task,
        )
        async_result = run_chunked_tenant_migrations_celery_task.delay(
            schema_name,
            chunk_size=chunk_size,
            max_chunks=max_chunks,
            time_budget=time_budget,
            session_id=session_id,
        )
        record_watchdog_heartbeat(
            schema_name=schema_name,
            task_id=async_result.id,
            status="DISPATCHED",
            current_chunk="Dispatched to Celery queue",
        )
        logger.info("[Watchdog] Dispatched Celery migration task for '%s' (task_id=%s)", schema_name, async_result.id)
        return {
            "schema_name": schema_name,
            "is_ready": False,
            "engine": "celery_dispatched",
            "task_id": async_result.id,
        }
    except Exception as dispatch_err:
        logger.warning("[Watchdog] Celery dispatch failed for '%s' (%s) — falling back to local engine.", schema_name, dispatch_err)
        result = advance_tenant_provisioning(
            schema_name,
            time_budget=time_budget,
            max_chunks=max_chunks,
            chunk_size=chunk_size,
            session_id=session_id,
            source="celery_broker_fallback",
        )
        result["engine"] = "celery_broker_fallback"
        return result

