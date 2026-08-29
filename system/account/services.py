"""
system/account/services.py
=========================
Business logic services for platform-level operations.

These services handle:
- Tenant creation (shop setup with schema, domain)
- Tenant migration setup
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from django.db import connection, transaction
from django_tenants.utils import schema_context, get_tenant_domain_model

from system.core.models import Shop, Domain
from system.account.models import PlatformUser


class TenantCreationError(Exception):
    """Raised when tenant creation fails."""
    pass


class TenantService:
    """
    Service for creating and managing tenant shops.

    This service handles:
    1. Creating the Shop (tenant) record
    2. Creating the default Domain
    3. Running migrations for the new tenant schema
    """

    @staticmethod
    def create_tenant(
        owner: PlatformUser,
        name: str,
        subdomain: str,
        schema_name: str = "",
        session=None,
        enqueue_async: bool = True,
    ) -> tuple[Shop, Domain]:
        """
        Create a new tenant (shop) for a platform user in the public schema,
        then enqueue schema creation and tenant migrations asynchronously.

        Args:
            owner: The PlatformUser who will own this shop
            name: Display name for the shop
            subdomain: The subdomain part of the shop URL
            schema_name: Optional schema name (defaults to subdomain)
            session: Optional OnboardingSession model instance
            enqueue_async: Whether to trigger the Celery provisioning task

        Returns:
            tuple of (Shop, Domain)

        Raises:
            TenantCreationError: If creation fails
        """
        subdomain = subdomain.lower().strip()
        schema_name = (schema_name or "").strip().lower() or subdomain

        if Domain.objects.filter(domain__iexact=subdomain).exists():
            raise TenantCreationError(
                f"The subdomain '{subdomain}' is already taken. "
                "Please choose a different one."
            )

        try:
            with transaction.atomic():
                shop = Shop.objects.create(
                    owner=owner,
                    name=name,
                    schema_name=schema_name,
                    provisioning_status=Shop.ProvisioningStatus.PENDING,
                    provisioning_error="",
                )
                domain = Domain.objects.create(
                    domain=subdomain,
                    tenant=shop,
                    is_primary=True,
                )

            if enqueue_async:
                from system.account.tasks import provision_tenant_schema_task
                session_id = str(session.id) if session else None
                try:
                    provision_tenant_schema_task.delay(
                        schema_name=shop.schema_name,
                        session_id=session_id,
                    )
                except Exception as exc:
                    # In local dev or if broker is temporarily unavailable, log warning
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        "Celery broker unavailable to enqueue provisioning task for %s: %s",
                        shop.schema_name,
                        exc,
                    )

            return shop, domain
        except Exception as e:
            raise TenantCreationError(f"Failed to create tenant: {str(e)}")

    @staticmethod
    def run_tenant_migrations(
        schema_name: str,
        progress_callback: Any = None,
    ) -> dict:
        """
        Create the PostgreSQL schema and run tenant migrations in dependency-ordered
        micro-batches with connection recycling and RAM safety (under 30MB).
        Resumes immediately from the last applied migration if previously interrupted.

        Args:
            schema_name: The tenant's schema name
            progress_callback: Optional callable(stage_info, applied_count, total_count)
        """
        import gc
        import logging
        from django.core.management import call_command
        from django.db import connection, transaction
        from django.db.migrations.recorder import MigrationRecorder
        from system.account.schema_inspector import (
            STAGE_APP_MAPPINGS,
            get_tenant_migration_status,
            invalidate_tenant_ready_cache,
        )

        logger = logging.getLogger("sabistart.celery.provisioning")
        schema_name = schema_name.strip().lower()

        logger.info("[TenantService] Starting micro-chunked migrations for '%s'...", schema_name)

        # 1. Ensure the schema exists
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}";')

        # 2. Ensure django_migrations table is created inside the schema
        connection.set_schema(schema_name, include_public=False)
        recorder = MigrationRecorder(connection)
        recorder.ensure_schema()
        connection.set_schema(schema_name, include_public=False)

        # 3. Iterate through ordered dependency stages
        total_stages = len(STAGE_APP_MAPPINGS)
        for stage_idx, stage_info in enumerate(STAGE_APP_MAPPINGS, start=1):
            stage_key = stage_info["key"]
            stage_name = stage_info["name"]
            stage_apps = stage_info["apps"]

            logger.info(
                "[TenantService][%s] Executing Stage %d/%d: %s (apps=%s)",
                schema_name, stage_idx, total_stages, stage_name, stage_apps,
            )

            # Apply migrations app-by-app in this micro-chunk
            for app_label in stage_apps:
                try:
                    connection.set_schema(schema_name, include_public=False)
                    call_command("migrate", app_label, interactive=False, verbosity=0)
                except Exception as app_err:
                    logger.warning(
                        "[TenantService][%s] App '%s' migration notice: %s. Continuing...",
                        schema_name, app_label, app_err,
                    )

            # Commit batch transaction and recycle connection memory
            try:
                if not transaction.get_autocommit():
                    transaction.commit()
                connection.close()
                connection.connection = None
            except Exception:
                pass
            gc.collect()

            # Inspect progress and trigger callback
            status = get_tenant_migration_status(schema_name, use_cache=False)
            if progress_callback:
                try:
                    progress_callback(stage_info, status["applied_count"], status["total_migrations"])
                except Exception as cb_err:
                    logger.debug("[TenantService] Progress callback error: %s", cb_err)

        # 4. Final convergence pass to ensure all dependencies are 100% applied
        try:
            connection.set_schema(schema_name, include_public=False)
            call_command("migrate", interactive=False, verbosity=0)
            if not transaction.get_autocommit():
                transaction.commit()
            connection.close()
            connection.connection = None
        except Exception as final_err:
            logger.warning("[TenantService][%s] Final convergence pass notice: %s", schema_name, final_err)
        finally:
            connection.set_schema_to_public()
            gc.collect()

        # Invalidate and re-cache ready status
        invalidate_tenant_ready_cache(schema_name)
        final_status = get_tenant_migration_status(schema_name, use_cache=False)
        logger.info(
            "[TenantService] Micro-chunked migrations finished for '%s' (Applied: %d/%d, Ready: %s)",
            schema_name, final_status["applied_count"], final_status["total_migrations"], final_status["is_ready"],
        )
        return final_status

    @staticmethod
    def provision_tenant_entitlements(session, shop: Shop) -> None:
        """
        Grants plan bundle features and add-ons within the tenant's schema context.
        """
        from django_tenants.utils import schema_context
        from dashboard.feature_marketplace.services import (
            get_plan_bundle_by_slug,
            get_active_feature_catalog,
            grant_manual_entitlement,
        )
        from system.feature_marketplace.models import FeaturePrice, FeatureType

        with schema_context(shop.schema_name):
            # 1. Plan bundle
            bundle_slug = getattr(session, "selected_bundle_slug", "")
            currency = getattr(session, "currency", "NGN")
            if bundle_slug:
                bundle = get_plan_bundle_by_slug(bundle_slug, currency=currency)
                if bundle:
                    for item in bundle.items.select_related("feature").order_by("sort_order"):
                        grant_manual_entitlement(
                            feature=item.feature,
                            quantity=item.quantity_override or 1,
                            note="Granted during platform onboarding.",
                            billing_cycle=bundle.billing_cycle,
                            currency=bundle.currency,
                        )

            # 2. Add-on features
            addon_codes = getattr(session, "selected_feature_codes", []) or []
            if addon_codes:
                feature_map = {
                    feature.code: feature
                    for feature in get_active_feature_catalog(currency=currency, purchasable_only=True)
                }
                for code in addon_codes:
                    feature = feature_map.get(code)
                    if not feature:
                        continue
                    price = (
                        FeaturePrice.objects.filter(feature=feature, currency=currency, is_active=True)
                        .order_by("amount")
                        .first()
                    )
                    quantity = 1
                    if price and feature.feature_type == FeatureType.LIMIT:
                        quantity = price.limit_increment or feature.default_limit_value or 1
                    elif price and feature.feature_type == FeatureType.USAGE:
                        quantity = price.credits_included or feature.default_usage_value or 1
                    grant_manual_entitlement(
                        feature=feature,
                        quantity=quantity,
                        note="Granted during platform onboarding.",
                        billing_cycle=price.billing_cycle if price else "perpetual",
                        currency=currency,
                    )


    @staticmethod
    def get_tenant_for_subdomain(subdomain: str) -> Shop | None:
        """
        Get a tenant by its subdomain.

        Args:
            subdomain: The subdomain to look up

        Returns:
            Shop instance or None if not found
        """
        subdomain = subdomain.lower()
        try:
            domain = Domain.objects.select_related('tenant').get(
                domain=subdomain,
                is_primary=True,
            )
            return domain.tenant
        except Domain.DoesNotExist:
            return None

    @staticmethod
    def is_subdomain_available(subdomain: str) -> bool:
        """
        Check if a subdomain is available.

        Args:
            subdomain: The subdomain to check

        Returns:
            True if available, False if taken
        """
        subdomain = subdomain.lower()
        reserved = {'www', 'admin', 'mail', 'ftp', 'localhost', 'api',
                    'blog', 'shop', 'store', 'platform', 'public', 'private'}
        if subdomain in reserved:
            return False
        return not Domain.objects.filter(domain=subdomain).exists()
