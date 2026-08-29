"""
system/account/tasks.py
====================
Celery Tasks for Tenant Migrations & Provisioning (Dual-Engine).

Executes tenant migrations using the EXACT SAME micro-chunking logic,
database connection recycling, memory cleanup, and CPU-aware throttling
as our working local runner.
Updates a vigtilant watchdog heartbeat after every chunk to prevent silent hangs.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from celery import shared_task
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("sabistart.provisioning.celery")

WATCHDOG_KEY_PREFIX = "celery_migration_watchdog"
WATCHDOG_TTL = 600  # 10 minutes max for state key


def record_watchdog_heartbeat(
    schema_name: str,
    task_id: str,
    *,
    status: str = "RUNNING",
    applied_count: int = 0,
    total_migrations: int = 54,
    current_chunk: str = "",
    system_health: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> None:
    data = {
        "task_id": task_id,
        "schema_name": schema_name,
        "status": status,  # "RUNNING", "COMPLETED", "FAILED", "STALLED"
        "last_heartbeat_at": time.time(),
        "applied_count": applied_count,
        "total_migrations": total_migrations,
        "current_chunk": current_chunk,
        "system_health": system_health,
        "error": error,
    }
    try:
        cache.set(f"{WATCHDOG_KEY_PREFIX}:{schema_name}", data, timeout=WATCHDOG_TTL)
    except Exception as err:
        logger.debug("Could not set watchdog heartbeat: %s", err)



@shared_task(bind=True, name="system.account.tasks.run_chunked_tenant_migrations_celery_task")
def run_chunked_tenant_migrations_celery_task(
    self,
    schema_name: str,

    *,
    chunk_size: Optional[int] = None,
    max_chunks: Optional[int] = None,
    time_budget: Optional[float] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Celery worker task that executes tenant migrations in micro-chunks.
    Updates the watchdog heartbeat after every chunk.
    """
    schema_name = (schema_name or "").strip().lower()
    task_id = str(self.request.id or "sync-task")

    logger.info(
        "[CeleryRunner] Starting Celery chunked migrations for '%s' (task_id=%s)",
        schema_name, task_id,
    )

    record_watchdog_heartbeat(
        schema_name=
        schema_name,
        task_id=task_id,
        status="RUNNING",
        current_chunk="Initializing",
    )

    from system.account.migration_runner import advance_tenant_provisioning
    from system.account.throttler import default_throttler

    try:
        result = advance_tenant_provisioning(
            schema_name,
            chunk_size=chunk_size,
            max_chunks=max_chunks,
            time_budget=time_budget,
            session_id=session_id,
            source="celery_worker",
            throttler=default_throttler,
        )


        final_status = "COMPLETED" if result.get("is_ready") else ("FAILED" if result.get("failed") else "RUNNING")
        record_watchdog_heartbeat(
            schema_name,
            task_id,
            status=final_status,
            error=result.get("error", ""),
        )
        logger.info("[CeleryRunner] Finished Celery pass for '%s' (status=%s)", schema_name, final_status)
        return result


    except Exception as exc:
        logger.exception("[CeleryRunner] Unhandled exception in Celery migration task for '%s': %s", schema_name, exc)
        record_watchdog_heartbeat(
            schema_name,
            task_id,
            status="FAILED",
            error=f"{type(exc).__name__}: {exc}",
        )
        raise

