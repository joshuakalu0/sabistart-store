"""
system/account/middleware.py
============================
Self-healing Tenant Provisioning & Migration Guard Middleware (Celery-free).

Intercepts requests to unready/partially-migrated tenant workspaces.
Instead of throwing 500 errors (relation does not exist) when a user logs in
before provisioning completes or after an interruption, this middleware:
1. Dynamically detects unapplied migrations using the schema inspector (0ms cache lookup).
2. Automatically self-heals by applying the remaining migration chunks inline,
   in a strictly time-budgeted micro-chunk pass (no Celery, no threads).
3. If the tenant becomes ready within the budget, the request proceeds
   seamlessly; otherwise it renders a sleek setup interstitial UI that
   live-polls (and keeps advancing) until ready.
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
    Provides automatic inline self-healing (time-budgeted chunked migrations)
    and a clean user-facing interstitial while work remains.
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

        # ── On-login self-healing (only when NOT in cron mode) ──────────────────
        # In cron mode the OS cron job owns all DDL work.  Running
        # advance_tenant_provisioning() inside a Gunicorn HTTP worker is what
        # causes OOM / timeout kills, so we skip it entirely and just show
        # the interstitial immediately.
        migration_runner = getattr(settings, "MIGRATION_RUNNER", "redis").lower()
        heal_result: dict = {}

        if migration_runner != "cron":
            from system.account.migration_runner import advance_tenant_provisioning

            heal_budget = getattr(settings, "TENANT_PROVISIONING_HEAL_BUDGET", 8)
            try:
                heal_result = advance_tenant_provisioning(
                    schema_name,
                    time_budget=heal_budget,
                    source="login_guard",
                )
            except Exception as heal_err:
                logger.warning(
                    "[ProvisioningGuard] Inline self-healing error for schema '%s': %s",
                    schema_name,
                    heal_err,
                )

        if heal_result.get("is_ready"):
            # Healing finished within budget — let the request through seamlessly.
            return self.get_response(request)

        # Refresh status for the interstitial payload

        status = get_tenant_migration_status(schema_name, use_cache=False)

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

        # Redirect to the unified provisioning waiting page (same UI as signup flow)
        from django.http import HttpResponseRedirect
        from urllib.parse import urlencode
        provisioning_url = reverse("platform:onboarding_provisioning")
        params = urlencode({"schema": schema_name, "next": path})
        return HttpResponseRedirect(f"{provisioning_url}?{params}")
