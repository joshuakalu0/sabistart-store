"""
system/account/worker_views.py
===============================
Two paired Django views for the Migration Worker Microservice Architecture:

1. worker_migrate_endpoint  (POST /api/v1/worker/migrate/)
   - Validates the shared HMAC secret from the main server.
   - Immediately returns HTTP 202 Accepted.
   - Spawns a background thread that runs all tenant migrations in 1-by-1
     micro-chunks, writing Redis progress heartbeats after every migration.
   - On completion, POSTs an authenticated webhook to the main server callback URL.

2. tenant_migration_webhook_callback  (POST /api/v1/tenants/migration-callback/)
   - Validates the shared HMAC secret from the worker.
   - Flips Shop.provisioning_status to READY.
   - Provisions the tenant owner as Superuser inside the isolated schema.
   - Returns JSON {"ok": true}.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
import urllib.request
from typing import Any, Dict

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger("sabistart.provisioning.worker_views")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _get_worker_secret() -> str:
    return getattr(settings, "MIGRATION_WORKER_SECRET", settings.SECRET_KEY)


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _verify(body: bytes, sig: str, secret: str) -> bool:
    return hmac.compare_digest(_sign(body, secret), sig or "")


def _auth_error() -> JsonResponse:
    return JsonResponse({"error": "Unauthorized"}, status=401)


# ---------------------------------------------------------------------------
# 1. Worker Migration Endpoint
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def worker_migrate_endpoint(request):
    """
    POST /api/v1/worker/migrate/

    Called by the main server to start migrations on this worker node.
    Validates Authorization header, immediately returns 202, and runs
    migrations in a background daemon thread.
    """
    secret = _get_worker_secret()

    # Validate Bearer token
    auth_header = request.headers.get("Authorization", "")
    bearer_token = auth_header.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(bearer_token, secret):
        logger.warning("[WorkerEndpoint] Rejected request: invalid bearer token.")
        return _auth_error()

    # Also verify HMAC body signature
    body = request.body
    sig = request.headers.get("X-Worker-Signature", "")
    if not _verify(body, sig, secret):
        logger.warning("[WorkerEndpoint] Rejected request: invalid HMAC signature.")
        return _auth_error()

    try:
        payload = json.loads(body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    schema_name = (payload.get("schema_name") or "").strip().lower()
    if not schema_name:
        return JsonResponse({"error": "schema_name is required"}, status=400)

    chunk_size = int(payload.get("chunk_size", 1))
    callback_url = payload.get("callback_url", "")
    owner_id = payload.get("owner_id", "")
    owner_email = payload.get("owner_email", "")

    # Write DISPATCHED progress immediately
    from system.account.worker_client import set_worker_progress
    set_worker_progress(schema_name, {
        "status": "RUNNING",
        "schema_name": schema_name,
        "applied_count": 0,
        "total_migrations": 0,
        "current_step": "Worker received, starting migrations...",
        "progress_percentage": 3,
        "engine": "remote_worker",
    })

    # Spawn background thread
    thread = threading.Thread(
        target=_run_all_migrations_and_callback,
        args=(schema_name, chunk_size, callback_url, owner_id, owner_email, secret),
        daemon=True,
        name=f"worker-mig-{schema_name}",
    )
    thread.start()

    logger.info(
        "[WorkerEndpoint] Accepted migration job for '%s' (owner=%s) — thread started.",
        schema_name, owner_email,
    )
    return JsonResponse({"accepted": True, "schema_name": schema_name}, status=202)


def _run_all_migrations_and_callback(
    schema_name: str,
    chunk_size: int,
    callback_url: str,
    owner_id: str,
    owner_email: str,
    secret: str,
) -> None:
    """Background thread: runs every pending migration one-by-one, then calls back."""
    from system.account.migration_runner import advance_tenant_provisioning
    from system.account.worker_client import set_worker_progress

    def _cb(stage_info, applied, total, detail=""):
        pct = int((applied / total) * 100) if total else 5
        set_worker_progress(schema_name, {
            "status": "RUNNING",
            "schema_name": schema_name,
            "applied_count": applied,
            "total_migrations": total,
            "current_step": detail or f"Migration {applied}/{total}",
            "progress_percentage": max(5, min(98, pct)),
            "engine": "remote_worker",
        })

    logger.info("[WorkerThread] Running migrations for '%s'.", schema_name)

    final_status = "FAILED"
    error_msg = ""
    applied_count = 0
    total_migrations = 0

    while True:
        try:
            result = advance_tenant_provisioning(
                schema_name,
                chunk_size=chunk_size,
                max_chunks=1,
                time_budget=None,
                source="remote_worker",
                progress_callback=_cb,
            )
        except Exception as exc:
            logger.exception("[WorkerThread] Error for '%s': %s", schema_name, exc)
            error_msg = str(exc)
            break

        applied_count = result.get("applied_count", applied_count)
        total_migrations = result.get("total_migrations", total_migrations)

        if result.get("is_ready"):
            final_status = "COMPLETED"
            break
        if result.get("stopped_reason") == "failed":
            error_msg = result.get("error") or "Migration failed"
            break

        time.sleep(0.1)

    # Update final progress in Redis
    set_worker_progress(schema_name, {
        "status": final_status,
        "schema_name": schema_name,
        "applied_count": applied_count,
        "total_migrations": total_migrations,
        "current_step": "All migrations complete" if final_status == "COMPLETED" else f"Failed: {error_msg}",
        "progress_percentage": 100 if final_status == "COMPLETED" else 0,
        "engine": "remote_worker",
        "error": error_msg,
    })
    logger.info("[WorkerThread] Finished migrations for '%s': %s.", schema_name, final_status)

    # POST callback to main server
    if callback_url:
        _post_callback(callback_url, schema_name, final_status, error_msg, owner_id, owner_email, secret)


def _post_callback(
    callback_url: str,
    schema_name: str,
    status: str,
    error: str,
    owner_id: str,
    owner_email: str,
    secret: str,
) -> None:
    """POSTs webhook to main server's /api/v1/tenants/migration-callback/."""
    payload = {
        "schema_name": schema_name,
        "status": status,
        "error": error,
        "owner_id": owner_id,
        "owner_email": owner_email,
    }
    body = json.dumps(payload).encode()
    sig = _sign(body, secret)

    req = urllib.request.Request(
        callback_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {secret}",
            "X-Worker-Signature": sig,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            logger.info(
                "[WorkerThread] Callback to '%s' succeeded (HTTP %s) for schema '%s'.",
                callback_url, resp.status, schema_name,
            )
    except Exception as exc:
        logger.warning(
            "[WorkerThread] Callback to '%s' failed for schema '%s': %s",
            callback_url, schema_name, exc,
        )


# ---------------------------------------------------------------------------
# 2. Webhook Callback (on main server — receives completion from worker)
# ---------------------------------------------------------------------------

@csrf_exempt
@require_POST
def tenant_migration_webhook_callback(request):
    """
    POST /api/v1/tenants/migration-callback/

    Receives authenticated webhook from the Migration Worker when migrations finish.
    Updates Shop.provisioning_status to READY and provisions tenant admin user.
    """
    secret = _get_worker_secret()

    # Validate Bearer token
    auth_header = request.headers.get("Authorization", "")
    bearer_token = auth_header.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(bearer_token, secret):
        logger.warning("[WebhookCallback] Rejected callback: invalid bearer token.")
        return _auth_error()

    body = request.body
    sig = request.headers.get("X-Worker-Signature", "")
    if not _verify(body, sig, secret):
        logger.warning("[WebhookCallback] Rejected callback: invalid HMAC signature.")
        return _auth_error()

    try:
        payload = json.loads(body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    schema_name = (payload.get("schema_name") or "").strip().lower()
    status = (payload.get("status") or "").strip().upper()
    error_msg = payload.get("error", "")
    owner_id = payload.get("owner_id", "")
    owner_email = payload.get("owner_email", "")

    if not schema_name:
        return JsonResponse({"error": "schema_name required"}, status=400)

    logger.info(
        "[WebhookCallback] Received callback for schema '%s': status=%s",
        schema_name, status,
    )

    from system.core.models import Shop
    from system.account.worker_client import set_worker_progress, clear_worker_progress

    shop = Shop.objects.filter(schema_name=schema_name).first()
    if not shop:
        logger.warning("[WebhookCallback] Shop not found for schema '%s'.", schema_name)
        return JsonResponse({"error": "shop not found"}, status=404)

    if status == "COMPLETED":
        admin_ok = _provision_tenant_admin(shop, owner_id, owner_email)
        if not admin_ok:
            from system.account.worker_client import clear_worker_progress
            clear_worker_progress(schema_name)
            shop.provisioning_status = Shop.ProvisioningStatus.IN_PROGRESS
            shop.provisioning_error = "Tenant admin provisioning failed; retrying migrations."
            shop.save(update_fields=["provisioning_status", "provisioning_error"])
            return JsonResponse({
                "ok": False,
                "schema_name": schema_name,
                "status": "RETRY",
                "error": "Tenant admin provisioning failed; schema not fully ready.",
            })

        shop.provisioning_status = Shop.ProvisioningStatus.READY
        shop.provisioned_at = timezone.now()
        shop.provisioning_error = ""
        shop.save(update_fields=["provisioning_status", "provisioned_at", "provisioning_error"])

        set_worker_progress(schema_name, {
            "status": "COMPLETED",
            "schema_name": schema_name,
            "progress_percentage": 100,
            "current_step": "Store is ready!",
            "engine": "remote_worker",
        })

        logger.info("[WebhookCallback] Shop '%s' marked READY.", schema_name)

    elif status == "FAILED":
        shop.provisioning_status = Shop.ProvisioningStatus.FAILED
        shop.provisioning_error = error_msg[:5000]
        shop.save(update_fields=["provisioning_status", "provisioning_error"])

        set_worker_progress(schema_name, {
            "status": "FAILED",
            "schema_name": schema_name,
            "progress_percentage": 0,
            "current_step": f"Failed: {error_msg}",
            "error": error_msg,
            "engine": "remote_worker",
        })

        logger.error("[WebhookCallback] Shop '%s' provisioning FAILED: %s", schema_name, error_msg)

    return JsonResponse({"ok": True, "schema_name": schema_name, "status": status})


def _provision_tenant_admin(shop, owner_id: str, owner_email: str) -> bool:
    """Provisions the store owner as superuser in the tenant schema. Returns True on success."""
    from system.account.models import PlatformUser
    from system.account.sso import ensure_tenant_admin_user, TenantSchemaNotReady

    user = None
    if owner_id:
        try:
            user = PlatformUser.objects.get(pk=owner_id)
        except PlatformUser.DoesNotExist:
            pass
    if not user and owner_email:
        user = PlatformUser.objects.filter(email__iexact=owner_email).first()
    if not user:
        user = shop.owner if hasattr(shop, "owner") else None

    if user:
        try:
            ensure_tenant_admin_user(shop, user)
            logger.info("[WebhookCallback] Provisioned tenant admin for '%s'.", shop.schema_name)
            return True
        except TenantSchemaNotReady as exc:
            logger.warning("[WebhookCallback] Tenant schema not ready for admin user '%s': %s", shop.schema_name, exc)
            return False
        except Exception as exc:
            logger.warning("[WebhookCallback] Could not provision tenant admin: %s", exc)
    return True
