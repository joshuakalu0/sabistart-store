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
)
def provision_tenant_schema_task(
    self,
    schema_name: str,
    session_id: str | None = None,
) -> dict:
    """
    Celery task to asynchronously provision a tenant schema:
    1. Runs database schema creation and all tenant app migrations
    2. Provisions initial store settings & plan entitlements (within tenant schema context)
    3. Updates Shop & OnboardingSession provisioning statuses and records metrics
    """
    from system.account.models import OnboardingSession
    from system.account.services import TenantService
    from system.core.models import Shop

    task_id = self.request.id or "sync"
    logger.info(
        "[Celery Task %s] Starting async provisioning for tenant schema '%s' (session_id=%s)",
        task_id,
        schema_name,
        session_id,
    )

    shop = Shop.objects.filter(schema_name=schema_name).first()
    if not shop:
        err_msg = f"Shop record for schema '{schema_name}' was not found."
        logger.error("[Celery Task %s] %s", task_id, err_msg)
        return {"success": False, "error": err_msg}

    # Mark as In-Progress
    shop.provisioning_status = Shop.ProvisioningStatus.IN_PROGRESS
    shop.provisioning_error = ""
    shop.save(update_fields=["provisioning_status", "provisioning_error"])

    session = None
    if session_id:
        session = OnboardingSession.objects.filter(id=session_id).first()

    try:
        # Step 1: Run tenant migrations & schema creation
        logger.info("[Celery Task %s] Running migrations for schema '%s'...", task_id, schema_name)
        TenantService.run_tenant_migrations(schema_name)
        logger.info("[Celery Task %s] Migrations completed for schema '%s'.", task_id, schema_name)

        # Step 2: Provision entitlements & onboarding settings if session provided
        if session:
            logger.info("[Celery Task %s] Provisioning entitlements for schema '%s'...", task_id, schema_name)
            TenantService.provision_tenant_entitlements(session, shop)
            logger.info("[Celery Task %s] Entitlements provisioned for schema '%s'.", task_id, schema_name)

        # Step 3: Update Shop to Ready
        shop.provisioning_status = Shop.ProvisioningStatus.READY
        shop.provisioning_error = ""
        shop.provisioned_at = timezone.now()
        shop.save(update_fields=["provisioning_status", "provisioning_error", "provisioned_at"])

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

        logger.info("[Celery Task %s] Provisioning finished successfully for schema '%s'.", task_id, schema_name)
        return {"success": True, "schema_name": schema_name, "status": "ready"}

    except Exception as exc:
        err_msg = f"{type(exc).__name__}: {str(exc)}"
        stack_trace = traceback.format_exc()
        logger.exception("[Celery Task %s] Provisioning FAILED for schema '%s': %s", task_id, schema_name, err_msg)

        # Mark Shop as Failed with detailed trace for debugging
        shop.provisioning_status = Shop.ProvisioningStatus.FAILED
        shop.provisioning_error = f"{err_msg}\n\nTraceback:\n{stack_trace}"[:3000]
        shop.save(update_fields=["provisioning_status", "provisioning_error"])

        if session:
            metadata = dict(session.metadata or {})
            metadata["provisioning_error"] = err_msg
            metadata["provisioning_task_id"] = task_id
            session.metadata = metadata
            session.save(update_fields=["metadata", "updated_at"])

        # Re-raise so Celery logs and tracks task failure state
        raise exc
