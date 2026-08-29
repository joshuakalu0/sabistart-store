"""
system/account/middleware.py
============================
Self-healing Tenant Provisioning & Migration Guard Middleware.

Intercepts requests to unready/partially-migrated tenant workspaces.
Instead of throwing 500 errors (relation does not exist) when a user logs in
before Celery completes or after an interruption, this middleware:
1. Dynamically detects unapplied migrations using the schema inspector (0ms cache lookup).
2. Automatically self-heals by triggering the chunked migration task in the background.
3. Renders a sleek setup interstitial UI that live-polls and reloads once ready.
"""

from __future__ import annotations

import logging
import re
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse

from system.account.schema_inspector import (
    get_tenant_migration_status,
    is_tenant_ready,
)

logger = logging.getLogger("sabistart.account.middleware")

# Regex to detect dashboard tenant prefix: /dashboard/<prefix>/...
DASHBOARD_PREFIX_RE = re.compile(r"^/dashboard/([^/]+)(?:/.*)?$")


class TenantProvisioningGuardMiddleware:
    """
    Guards tenant requests against incomplete database migrations.
    Provides automatic background healing and clean user-facing interstitial.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path_info

        # Skip platform administrative, static, health, and onboarding paths
        if (
            path.startswith("/platform/")
            or path.startswith("/admin/")
            or path.startswith("/static/")
            or path.startswith("/media/")
            or path.startswith("/healthz")
            or path.startswith("/readyz")
            or path.startswith("/deployz")
            or path.startswith("/favicon.ico")
            or path.startswith("/.well-known/")
            or path == "/"
        ):
            return self.get_response(request)

        # Identify target tenant schema
        schema_name = None

        # 1. From request.tenant if resolved by domain middleware
        if hasattr(request, "tenant") and request.tenant:
            tenant_schema = getattr(request.tenant, "schema_name", None)
            if tenant_schema and tenant_schema != "public":
                schema_name = tenant_schema

        # 2. From /dashboard/<prefix>/ URL routing
        if not schema_name:
            match = DASHBOARD_PREFIX_RE.match(path)
            if match:
                prefix = match.group(1).lower().strip()
                # Ignore system keywords
                if prefix not in {"login", "logout", "auth", "static", "media", "platform"}:
                    from system.core.models import Shop
                    # Check if prefix matches a shop schema_name or domain
                    shop = Shop.objects.filter(schema_name=prefix).first()
                    if not shop:
                        # Try finding by domain or name
                        shop = Shop.objects.filter(domains__domain__istartswith=prefix).first()
                    if shop:
                        schema_name = shop.schema_name

        if not schema_name:
            return self.get_response(request)

        # Fast cache check: if already verified ready, pass through immediately
        if is_tenant_ready(schema_name):
            return self.get_response(request)

        # Schema is not cached as ready — inspect actual database state
        status = get_tenant_migration_status(schema_name, use_cache=False)
        if status.get("is_ready") is True:
            return self.get_response(request)

        # ── Self-healing trigger ──────────────────────────────────────────────
        # Schema has pending migrations. Check if task is already running or trigger it.
        from system.core.models import Shop
        shop = Shop.objects.filter(schema_name=schema_name).first()
        if shop:
            # If status is PENDING, FAILED, or stuck, automatically launch background chunk task
            if shop.provisioning_status in {
                Shop.ProvisioningStatus.PENDING,
                Shop.ProvisioningStatus.FAILED,
            }:
                logger.info(
                    "[ProvisioningGuard] Auto-triggering background self-healing for schema '%s'...",
                    schema_name,
                )
                try:
                    from system.account.tasks import provision_tenant_schema_task
                    shop.provisioning_status = Shop.ProvisioningStatus.IN_PROGRESS
                    shop.provisioning_error = "Self-healing: applying missing schema migrations..."
                    shop.save(update_fields=["provisioning_status", "provisioning_error"])
                    provision_tenant_schema_task.delay(schema_name=schema_name)
                except Exception as task_err:
                    logger.warning("[ProvisioningGuard] Could not launch async task: %s", task_err)

        # ── Return Interstitial or JSON ───────────────────────────────────────
        is_ajax = (
            request.headers.get("x-requested-with") == "XMLHttpRequest"
            or "application/json" in request.headers.get("Accept", "")
        )

        if is_ajax:
            return JsonResponse({
                "status": "provisioning",
                "schema_name": schema_name,
                "progress": status.get("progress_percent", 35),
                "stage": status.get("current_stage"),
                "applied_count": status.get("applied_count", 0),
                "total_migrations": status.get("total_migrations", 54),
                "message": "Store workspace database setup is finishing in the background.",
            }, status=503)

        context = {
            "schema_name": schema_name,
            "shop_name": shop.name if shop else schema_name,
            "status": status,
            "progress_percent": status.get("progress_percent", 35),
            "current_stage": status.get("current_stage"),
            "poll_url": reverse("platform:onboarding_provisioning_status"),
            "target_url": path,
        }
        return render(request, "account/tenant_provisioning_interstitial.html", context, status=200)
