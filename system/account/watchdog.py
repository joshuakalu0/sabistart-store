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

    if watchdog and watchdog.get("status") == "RUNNING":
        last_heartbeat = float(watchdog.get("last_heartbeat_at", now))
        elapsed_since_heartbeat = now - last_heartbeat

        if elapsed_since_heartbeat > stall_timeout:
            # Silent Hang Detected!
            task_id = watchdog.get("task_id", "")
            logger.warning(
                "[Watchdog] Celery execution STALLED for '%s' (no heartbeat for %.1fs > %.1fs). Revoking task %s and triggering automatic local fallback.",
                schema_name, elapsed_since_heartbeat, stall_timeout, task_id,
            )
            revoke_celery_task(task_id)
            watchdog["status"] = "STALLED"
            try:
                cache.set(f"{WATCHDOG_KEY_PREFIX}:{schema_name}", watchdog, timeout=600)
            except Exception:
                pass

            # Seamless fallback to local CPU-aware runner
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
            # Celery is actively running with recent heartbeat
            from system.account.schema_inspector import get_tenant_migration_status
            status = get_tenant_migration_status(schema_name, use_cache=False)
            return {
                "schema_name": schema_name,
                "is_ready": status["is_ready"],
                "failed": False,
                "locked": False,
                "cooldown": False,
                "error": "",
                "engine": "celery_active",
                "watchdog": watchdog,
            }

    # No active Celery task — attempt to dispatch
    try:
        from system.account.tasks import run_chunked_tenant_migrations_celery_task
        async_result = run_chunked_tenant_migrations_celery_task.delay(
            schema_name,
            chunk_size=chunk_size,
            max_chunks=max_chunks,
            time_budget=time_budget,
            session_id=session_id,
        )
        logger.info("[Watchdog] Dispatched Celery migration task for '%s' (task_id=%s)", schema_name, async_result.id)
        return {
            "schema_name": schema_name,
            "is_ready": False,
            "engine": "celery_dispatched",
            "task_id": async_result.id,
        }
    except Exception as dispatch_err:
        # Broker down or Celery error — fall back to local runner immediately
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
