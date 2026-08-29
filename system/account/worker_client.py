"""
system/account/worker_client.py
================================
Migration Worker Client — dispatches tenant migrations to an external
Migration Worker Microservice (Railway / VPS) via authenticated HTTP POST.

Flow:
  1. Main server calls dispatch_migration_to_worker(shop).
  2. If MIGRATION_WORKER_URL is set and healthy, POST to remote worker.
  3. If not set / worker unreachable, run migrations in a background daemon thread
     on the local server so Gunicorn HTTP workers are never blocked.

Progress is always stored in Redis cache under the worker_migration_progress:<schema>
key so the polling endpoint can read it without touching the worker.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("sabistart.provisioning.worker_client")

# Redis cache key prefix for worker progress state
WORKER_PROGRESS_KEY = "worker_migration_progress"
WORKER_PROGRESS_TTL = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Progress helpers
# ---------------------------------------------------------------------------

def get_worker_progress(schema_name: str) -> Optional[Dict[str, Any]]:
    """Returns the latest worker progress dict cached in Redis."""
    try:
        return cache.get(f"{WORKER_PROGRESS_KEY}:{schema_name}")
    except Exception:
        return None


def set_worker_progress(schema_name: str, data: Dict[str, Any]) -> None:
    """Upserts progress dict in Redis; never raises."""
    try:
        data["last_heartbeat_at"] = time.time()
        cache.set(f"{WORKER_PROGRESS_KEY}:{schema_name}", data, timeout=WORKER_PROGRESS_TTL)
    except Exception as exc:
        logger.debug("[WorkerClient] Could not set worker progress: %s", exc)


def clear_worker_progress(schema_name: str) -> None:
    try:
        cache.delete(f"{WORKER_PROGRESS_KEY}:{schema_name}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# HMAC signature helpers (shared secret between main server & worker)
# ---------------------------------------------------------------------------

def _build_signature(body: bytes, secret: str) -> str:
    import hmac as _hmac
    return _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _verify_signature(body: bytes, signature: str, secret: str) -> bool:
    expected = _build_signature(body, secret)
    return hmac.compare_digest(expected, signature or "")


# ---------------------------------------------------------------------------
# Background thread runner (local fallback when no external worker URL)
# ---------------------------------------------------------------------------

def _run_migrations_in_background(schema_name: str, chunk_size: int = 1) -> None:
    """
    Runs ALL pending tenant migrations in a daemon background thread so the
    Gunicorn HTTP worker returns immediately.  Progress is written to Redis
    after every single migration so the polling endpoint stays up-to-date.
    """
    from system.account.migration_runner import advance_tenant_provisioning

    def _worker():
        logger.info("[BackgroundRunner] Starting background migration thread for '%s'.", schema_name)
        set_worker_progress(schema_name, {
            "status": "RUNNING",
            "schema_name": schema_name,
            "applied_count": 0,
            "total_migrations": 0,
            "current_step": "Initializing...",
            "progress_percentage": 5,
            "engine": "background_thread",
        })

        def _per_migration_cb(stage_info, applied, total, detail=""):
            pct = int((applied / total) * 100) if total else 5
            set_worker_progress(schema_name, {
                "status": "RUNNING",
                "schema_name": schema_name,
                "applied_count": applied,
                "total_migrations": total,
                "current_step": detail or f"Migration {applied}/{total}",
                "progress_percentage": max(5, min(98, pct)),
                "engine": "background_thread",
            })

        while True:
            try:
                result = advance_tenant_provisioning(
                    schema_name,
                    chunk_size=chunk_size,
                    max_chunks=1,
                    time_budget=None,
                    source="background_thread",
                    progress_callback=_per_migration_cb,
                )
            except Exception as exc:
                logger.exception("[BackgroundRunner] Error during migration for '%s': %s", schema_name, exc)
                set_worker_progress(schema_name, {
                    "status": "FAILED",
                    "schema_name": schema_name,
                    "error": str(exc),
                    "progress_percentage": 0,
                    "engine": "background_thread",
                })
                return

            if result.get("is_ready"):
                set_worker_progress(schema_name, {
                    "status": "COMPLETED",
                    "schema_name": schema_name,
                    "applied_count": result.get("applied_count", 0),
                    "total_migrations": result.get("total_migrations", 0),
                    "current_step": "All migrations complete",
                    "progress_percentage": 100,
                    "engine": "background_thread",
                })
                logger.info("[BackgroundRunner] All migrations complete for '%s'.", schema_name)
                return

            stopped = result.get("stopped_reason", "")
            if stopped == "failed":
                error = result.get("error") or "Migration failed"
                set_worker_progress(schema_name, {
                    "status": "FAILED",
                    "schema_name": schema_name,
                    "error": error,
                    "progress_percentage": 0,
                    "engine": "background_thread",
                })
                return

            # Pause briefly between single-migration ticks to yield CPU
            time.sleep(0.1)

    thread = threading.Thread(target=_worker, daemon=True, name=f"mig-{schema_name}")
    thread.start()
    logger.info("[WorkerClient] Launched background migration thread %s for '%s'.", thread.name, schema_name)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

def dispatch_migration_to_worker(
    shop,
    user=None,
    session=None,
    chunk_size: int = 1,
) -> Dict[str, Any]:
    """
    Dispatches tenant schema migrations to the appropriate engine:
    1. External Migration Worker Microservice (if MIGRATION_WORKER_URL is set).
    2. Background daemon thread on local server (safe fallback).

    Returns a dict summarising what was launched.
    """
    schema_name = getattr(shop, "schema_name", "") or ""

    # Skip if already running or complete
    existing = get_worker_progress(schema_name)
    if existing and existing.get("status") in ("RUNNING", "COMPLETED"):
        logger.info(
            "[WorkerClient] Migration already %s for '%s'; skipping new dispatch.",
            existing["status"], schema_name,
        )
        return {"dispatched": False, "reason": "already_running", "progress": existing}

    worker_url = getattr(settings, "MIGRATION_WORKER_URL", "").rstrip("/")
    worker_secret = getattr(settings, "MIGRATION_WORKER_SECRET", settings.SECRET_KEY)

    if worker_url:
        return _dispatch_to_remote_worker(
            shop, user, session, chunk_size, worker_url, worker_secret,
        )

    # No remote worker configured — use background thread
    logger.info("[WorkerClient] No MIGRATION_WORKER_URL set; using background thread for '%s'.", schema_name)
    _run_migrations_in_background(schema_name, chunk_size=chunk_size)
    return {"dispatched": True, "engine": "background_thread", "schema_name": schema_name}


def _dispatch_to_remote_worker(
    shop, user, session, chunk_size, worker_url, worker_secret
) -> Dict[str, Any]:
    import urllib.request

    schema_name = shop.schema_name

    main_server_base = getattr(settings, "MIGRATION_WEBHOOK_URL", "").rstrip("/")
    if not main_server_base:
        platform_cname = getattr(settings, "PLATFORM_CNAME", "localhost")
        main_server_base = f"https://{platform_cname}"
    callback_url = f"{main_server_base}/api/v1/tenants/migration-callback/"

    owner_obj = user or getattr(shop, "owner", None)
    owner_email = getattr(owner_obj, "email", "") or ""
    owner_id = str(getattr(owner_obj, "id", "")) or ""

    payload = {
        "schema_name": schema_name,
        "shop_id": str(shop.id) if hasattr(shop, "id") else "",
        "owner_email": owner_email,
        "owner_id": owner_id,
        "chunk_size": chunk_size,
        "callback_url": callback_url,
    }

    body = json.dumps(payload).encode()
    sig = _build_signature(body, worker_secret)

    req = urllib.request.Request(
        f"{worker_url}/api/v1/worker/migrate/",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {worker_secret}",
            "X-Worker-Signature": sig,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            response_data = json.loads(resp.read())
        logger.info("[WorkerClient] Dispatched to remote worker for '%s'.", schema_name)
        set_worker_progress(schema_name, {
            "status": "DISPATCHED",
            "schema_name": schema_name,
            "applied_count": 0,
            "total_migrations": 0,
            "current_step": "Dispatched to worker node...",
            "progress_percentage": 3,
            "engine": "remote_worker",
        })
        return {"dispatched": True, "engine": "remote_worker", "schema_name": schema_name, "response": response_data}

    except Exception as exc:
        logger.warning(
            "[WorkerClient] Remote worker unreachable (%s); falling back to background thread for '%s'.",
            exc, schema_name,
        )
        _run_migrations_in_background(schema_name, chunk_size=chunk_size)
        return {"dispatched": True, "engine": "background_thread_fallback", "schema_name": schema_name, "error": str(exc)}
