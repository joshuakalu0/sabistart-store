from __future__ import annotations

import logging
from django.db import connection

logger = logging.getLogger(__name__)


def dashboard_feature_context(request):
    """
    Injected into all templates via settings.TEMPLATES context_processors.
    Provides feature_access_map on tenant schemas so Django templates can
    cleanly omit or include feature surfaces on the server side.
    Also injects `catalog_settings` (PlatformCatalogFeatureSetting) for
    gating advanced product/category/brand form sections.
    """
    schema_name = getattr(connection, "schema_name", None)
    if not schema_name or schema_name == "public":
        return {}

    ctx = {}

    try:
        from dashboard.feature_marketplace.services import FeatureEntitlementEngine
        ctx["feature_access_map"] = FeatureEntitlementEngine(schema_name).get_all_entitlements()
    except Exception as exc:
        logger.debug("[dashboard_feature_context] Error loading entitlements: %s", exc)
        ctx["feature_access_map"] = {}

    try:
        from system.core.platform_settings import PlatformCatalogFeatureSetting
        # PlatformCatalogFeatureSetting lives in the PUBLIC schema.
        # When called from a tenant request, the DB connection is scoped to
        # the tenant schema, so we must temporarily switch to public, read,
        # then restore the tenant schema.
        current_schema = connection.schema_name
        connection.set_schema_to_public()
        try:
            catalog = PlatformCatalogFeatureSetting.get_settings()
        finally:
            connection.set_schema(current_schema)
        ctx["catalog_settings"] = catalog
    except Exception as exc:
        logger.debug("[dashboard_feature_context] Error loading catalog settings: %s", exc)
        from system.core.platform_settings import PlatformCatalogFeatureSetting
        ctx["catalog_settings"] = PlatformCatalogFeatureSetting()

    return ctx
