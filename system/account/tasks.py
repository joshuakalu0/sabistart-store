from __future__ import annotations

import logging
import traceback
from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("sabistart.celery.provisioning")


@shared_task(
    bind=True,
    name="system.account.tasks.provision_tenant_schema_task",
    max_retries=2,
    default_retry_delay=15,
    soft_time_limit=1800,  # 30 minutes for tenant schema migrations
    time_limit=2400,       # 40 minutes hard limit
)
def provision_tenant_schema_task(
    self,
    schema_name: str,
    session_id: str | None = None,
) -> dict:
    """
    Celery task to asynchronously provision a tenant schema in micro-batches:
    1. Runs micro-chunked schema migrations with memory recycling & live stage tracking
    2. Provisions initial store settings & plan entitlements (within tenant schema context)
    3. Updates Shop & OnboardingSession provisioning statuses and invalidates caches
    """
    import gc
    from system.account.models import OnboardingSession
    from system.account.services import TenantService
    from system.account.schema_inspector import (
        get_tenant_migration_status,
        invalidate_tenant_ready_cache,
    )
    from system.core.models import Shop

    task_id = self.request.id or "sync"
    schema_name = schema_name.strip().lower()
    logger.info(
        "[Celery Task %s] Starting micro-chunked provisioning for tenant '%s' (session_id=%s)",
        task_id, schema_name, session_id,
    )

    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute('SET search_path = "public";')
    except Exception:
        pass
    connection.set_schema_to_public()

    shop = Shop.objects.filter(schema_name=schema_name).first()
    if not shop:
        err_msg = f"Shop record for schema '{schema_name}' was not found."
        logger.error("[Celery Task %s] %s", task_id, err_msg)
        return {"success": False, "error": err_msg}

    # Mark as In-Progress
    shop.provisioning_status = Shop.ProvisioningStatus.IN_PROGRESS
    shop.provisioning_error = "Starting tenant migrations..."
    shop.save(update_fields=["provisioning_status", "provisioning_error"])

    session = None
    if session_id:
        session = OnboardingSession.objects.filter(id=session_id).first()

    # Define progress callback to record live stage in Shop model
    def on_stage_progress(stage_info: dict, applied: int, total: int, current_app: str = ""):
        pct = int((applied / total) * 100) if total > 0 else 0
        stage_name = stage_info.get("name", "Migrating")
        stage_num = stage_info.get("stage", 1)
        mig_detail = f" ▶ {current_app}" if current_app else ""
        progress_msg = f"Stage {stage_num}/7: {stage_name} ({pct}% — {applied}/{total} applied){mig_detail}"
        try:
            connection.set_schema_to_public()
            Shop.objects.filter(schema_name=schema_name).update(provisioning_error=progress_msg)
        except Exception:
            pass

    try:
        # Step 1: Run micro-chunked tenant migrations
        logger.info("[Celery Task %s] Running micro-chunked migrations for '%s'...", task_id, schema_name)
        status = TenantService.run_tenant_migrations(schema_name, progress_callback=on_stage_progress)
        logger.info("[Celery Task %s] Migrations finished for '%s'. Status: %s", task_id, schema_name, status)

        # Step 2: Provision entitlements & onboarding settings if session provided
        if session:
            logger.info("[Celery Task %s] Provisioning entitlements for '%s'...", task_id, schema_name)
            TenantService.provision_tenant_entitlements(session, shop)
            logger.info("[Celery Task %s] Entitlements provisioned for '%s'.", task_id, schema_name)

        # Step 3: Update Shop to Ready
        shop.provisioning_status = Shop.ProvisioningStatus.READY
        shop.provisioning_error = ""
        shop.provisioned_at = timezone.now()
        shop.save(update_fields=["provisioning_status", "provisioning_error", "provisioned_at"])

        # Invalidate cache so middleware immediately recognizes tenant as ready
        invalidate_tenant_ready_cache(schema_name)

        # Step 4: Update OnboardingSession if present
        if session:
            session.status = OnboardingSession.Status.COMPLETED
            session.completed_at = timezone.now()
            metadata = dict(session.metadata or {})
            metadata["tenant_schema_name"] = schema_name
            metadata["provisioning_task_id"] = task_id
            metadata["provisioned_at"] = timezone.now().isoformat()
            session.metadata = metadata
            session.save(update_fields=["status", "completed_at", "metadata", "updated_at"])

        logger.info("[Celery Task %s] Provisioning SUCCESS for '%s'.", task_id, schema_name)
        gc.collect()
        return {"success": True, "schema_name": schema_name, "status": "ready"}

    except Exception as exc:
        err_msg = f"{type(exc).__name__}: {str(exc)}"
        stack_trace = traceback.format_exc()
        logger.exception("[Celery Task %s] Provisioning FAILED for '%s': %s", task_id, schema_name, err_msg)

        # Mark Shop as Failed with trace for debugging
        shop.provisioning_status = Shop.ProvisioningStatus.FAILED
        shop.provisioning_error = f"{err_msg}\n\nTraceback:\n{stack_trace}"[:3000]
        shop.save(update_fields=["provisioning_status", "provisioning_error"])

        if session:
            metadata = dict(session.metadata or {})
            metadata["provisioning_error"] = err_msg
            metadata["provisioning_task_id"] = task_id
            session.metadata = metadata
            session.save(update_fields=["metadata", "updated_at"])

        gc.collect()
        # Re-raise so Celery tracks task state
        raise exc
