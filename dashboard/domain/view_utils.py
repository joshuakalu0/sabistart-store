from dashboard.feature_marketplace.services import FeatureEntitlementEngine
from dashboard.sidebar_utiles import main_sidebar
from dashboard.domain.models import CustomDomain, DomainQuota


def get_domain_quota(tenant):
    quota, _ = DomainQuota.objects.get_or_create(tenant=tenant)
    engine = FeatureEntitlementEngine(getattr(tenant, "schema_name", None))
    total_quota = engine.get_feature_limit("max_custom_domains")
    if quota.max_custom_domains != total_quota:
        quota.max_custom_domains = total_quota
        quota.save(update_fields=["max_custom_domains", "updated_at"])
    return quota


def get_tenant_domains(tenant):
    return (
        CustomDomain.objects.filter(tenant=tenant)
        .exclude(status=CustomDomain.Status.REMOVED)
        .order_by("-is_primary", "-created_at")
    )


def build_page_context(prefix, page_title, active_menu, **extra):
    context = {
        "prefix": prefix,
        "page_title": page_title,
        "active_menu": active_menu,
        "sidebar": main_sidebar(prefix, active_menu),
    }
    context.update(extra)
    return context
