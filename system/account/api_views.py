"""
system/account/api_views.py
============================
Non-blocking REST API endpoints for tenant provisioning status polling.

Endpoints:
  GET  /api/v1/tenants/status/?schema=<schema_name>
  GET  /api/v1/tenants/<tenant_id>/status/

Response contract:
  {
    "status": "PROVISIONING" | "RUNNING" | "COMPLETED" | "FAILED" | "READY",
    "progress_percentage": 0-100,
    "current_step": "Migration 14/34: cart.0001_initial...",
    "is_completed": false,
    "redirect_url": null | "https://<subdomain>.sabistart.store/auth/sso/?ticket=...",
    "applied_count": 14,
    "total_migrations": 34,
    "schema_name": "onboard_abc123"
  }

Design principles:
  - ZERO heavy DDL or migration execution in this view.
  - Reads the Shop row + schema_inspector (django_migrations table).
  - Returns redirect_url only when status == "READY" (cron sweep done).
  - All migration work is performed by the OS-cron-scheduled
    process_pending_tenants management command.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger("sabistart.provisioning.api")


@require_GET
def tenant_status_api(request, tenant_id=None):
    """
    GET /api/v1/tenants/status/?schema=<schema>
    GET /api/v1/tenants/<tenant_id>/status/

    Lightweight polling endpoint.  Reads the Shop row plus the tenant
    schema's django_migrations table -- both cheap, indexed reads.
    This endpoint does NOT dispatch to any worker; provisioning is now
    cron-driven via the process_pending_tenants management command.
    """
    from django.conf import settings
    from system.core.models import Shop

    # ── Resolve schema_name ────────────────────────────────────────────────
    schema_name = request.GET.get("schema", "").strip().lower()

    if not schema_name and tenant_id:
        try:
            shop = Shop.objects.get(pk=tenant_id)
            schema_name = shop.schema_name
        except (Shop.DoesNotExist, Exception):
            return JsonResponse({"error": "tenant not found"}, status=404)

    if not schema_name:
        # Try to resolve from the authenticated user's shop
        if getattr(request.user, "is_authenticated", False):
            shop = Shop.objects.filter(owner=request.user).order_by("-created_on").first()
            if shop:
                schema_name = shop.schema_name

    if not schema_name:
        return JsonResponse({
            "status": "UNKNOWN",
            "progress_percentage": 0,
            "current_step": "No schema specified",
            "is_completed": False,
            "redirect_url": None,
        })

    # ── Fetch shop record ──────────────────────────────────────────────────
    shop = Shop.objects.filter(schema_name=schema_name).first()
    if not shop:
        return JsonResponse({
            "status": "PROVISIONING",
            "progress_percentage": 5,
            "current_step": "Setting up your store...",
            "is_completed": False,
            "redirect_url": None,
            "schema_name": schema_name,
        })

    # ── Already READY (fast path) ──────────────────────────────────────────
    if shop.provisioning_status == Shop.ProvisioningStatus.READY:
        redirect_url = _build_redirect_url(shop, request)
        return JsonResponse({
            "status": "READY",
            "progress_percentage": 100,
            "current_step": "Store is live! Redirecting...",
            "is_completed": True,
            "redirect_url": redirect_url,
            "schema_name": schema_name,
            "engine": "cron_sweep",
        })

    # ── Failed: surface a clear error to the user ────────────────────────
    if shop.provisioning_status == Shop.ProvisioningStatus.FAILED:
        err = (shop.provisioning_error or "Provisioning failed. Please retry.").strip()
        return JsonResponse({
            "status": "FAILED",
            "progress_percentage": 100,
            "current_step": err[:500] or "Provisioning failed.",
            "is_completed": False,
            "is_failed": True,
            "error": err[:2000],
            "redirect_url": None,
            "schema_name": schema_name,
            "engine": "cron_sweep",
        })

    # ── Pending: report real DB progress (what the cron sweep is doing) ──
    # The endpoint is a pure read -- it does NOT dispatch to any worker
    # and does NOT call ensure_tenant_admin_user.  All work is done by
    # the OS-cron-scheduled `process_pending_tenants` management command.
    try:
        from system.account.schema_inspector import get_tenant_migration_status
        mig = get_tenant_migration_status(schema_name, use_cache=True)
        applied = mig.get("applied_count", 0)
        total = mig.get("total_migrations", 0)
        pct = int(mig.get("progress_percent", 5))
        current_stage = mig.get("current_stage") or {}
        if current_stage:
            step = f"Stage {current_stage.get('stage', '')}:  {current_stage.get('name', 'Setting up database...')}"
        else:
            step = "Setting up database..."
    except Exception:
        applied, total, pct, step = 0, 0, 5, "Starting up..."

    # Reflect the Shop row's current state in the user-facing step.
    if shop.provisioning_status == Shop.ProvisioningStatus.PENDING:
        step = "Waiting for the migration sweep to pick up your store..."
    elif shop.provisioning_status == Shop.ProvisioningStatus.PROVISIONING:
        step = "Preparing your store..."
    elif shop.provisioning_status == Shop.ProvisioningStatus.IN_PROGRESS and applied == 0:
        step = "Migration sweep is starting..."

    return JsonResponse({
        "status": "PROVISIONING",
        "progress_percentage": max(5, pct),
        "current_step": step,
        "is_completed": False,
        "redirect_url": None,
        "applied_count": applied,
        "total_migrations": total,
        "schema_name": schema_name,
        "engine": "cron_sweep",
    })


def _build_redirect_url(shop, request) -> str:
    """Generates the cross-subdomain SSO redirect URL for a READY shop."""
    try:
        user = request.user if getattr(request.user, "is_authenticated", False) else shop.owner
        from system.account.sso import get_tenant_subdomain_redirect_url
        return get_tenant_subdomain_redirect_url(shop, request=request, user=user)
    except Exception as exc:
        logger.warning("[API] Could not build redirect URL: %s", exc)
        return "/platform/"
