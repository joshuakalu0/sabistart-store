try:
    from celery import shared_task
except ImportError:  # pragma: no cover
    def shared_task(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

from django_tenants.utils import get_tenant_model, schema_context

from dashboard.feature_marketplace.models import TenantEntitlement
from dashboard.feature_marketplace.services import FeatureEntitlementEngine, expire_due_entitlements, list_expiring_entitlements


@shared_task
def expire_feature_entitlements_task(schema_name: str | None = None):
    if schema_name:
        with schema_context(schema_name):
            return expire_due_entitlements()
    total = 0
    TenantModel = get_tenant_model()
    for tenant in TenantModel.objects.all():
        with schema_context(tenant.schema_name):
            total += expire_due_entitlements()
    return total


@shared_task
def rebuild_feature_quotas_task(schema_name: str | None = None):
    if schema_name:
        with schema_context(schema_name):
            FeatureEntitlementEngine(schema_name).rebuild_all_quotas()
            return True
    TenantModel = get_tenant_model()
    for tenant in TenantModel.objects.all():
        with schema_context(tenant.schema_name):
            FeatureEntitlementEngine(tenant.schema_name).rebuild_all_quotas()
    return True


@shared_task
def send_feature_renewal_reminders_task(schema_name: str | None = None, within_days: int = 14):
    processed = 0
    schemas = [schema_name] if schema_name else [tenant.schema_name for tenant in get_tenant_model().objects.all()]
    for current_schema in schemas:
        with schema_context(current_schema):
            for entitlement in list_expiring_entitlements(within_days=within_days):
                if entitlement.reminder_sent_at:
                    continue
                entitlement.reminder_sent_at = entitlement.reminder_sent_at or entitlement.updated_at
                entitlement.save(update_fields=["reminder_sent_at", "updated_at"])
                processed += 1
    return processed
