from __future__ import annotations

import logging
from django.db import connection

logger = logging.getLogger(__name__)


def dashboard_feature_context(request):
    """
    Injected into all templates via settings.TEMPLATES context_processors.
    Provides feature_access_map on tenant schemas so Django templates can
    cleanly omit or include feature surfaces on the server side.
    """
    schema_name = getattr(connection, "schema_name", None)
    if not schema_name or schema_name == "public":
        return {}

    try:
        from dashboard.feature_marketplace.services import FeatureEntitlementEngine

        return {
            "feature_access_map": FeatureEntitlementEngine(schema_name).get_all_entitlements()
        }
    except Exception as exc:
        logger.debug("[dashboard_feature_context] Error loading entitlements: %s", exc)
        return {"feature_access_map": {}}
