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
  - Only reads Redis cache (written by worker_client.py or tasks.py).
  - Falls back to DB-level schema_inspector for progress if no Redis data yet.
  - Returns redirect_url only when is_completed=True (status READY).
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

    Lightweight polling endpoint — reads Redis only, never touches the DB
    migration tables in the hot path.
    """
    from django.conf import settings
    from system.core.models import Shop
    from system.account.worker_client import get_worker_progress

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
        })

    # ── Read live progress from Redis (written by worker thread) ──────────
    progress = get_worker_progress(schema_name)

    if progress:
        worker_status = progress.get("status", "RUNNING")
        pct = int(progress.get("progress_percentage", 5))
        applied = int(progress.get("applied_count", 0))
        total = int(progress.get("total_migrations", 0))
        current_step = progress.get("current_step", "Running migrations...")
        engine = progress.get("engine", "background_thread")

        if worker_status == "COMPLETED" or pct >= 100:
            # Double-check DB status and update if needed
            shop.refresh_from_db()
            if shop.provisioning_status != Shop.ProvisioningStatus.READY:
                from django.utils import timezone
                from system.account.sso import ensure_tenant_admin_user
                shop.provisioning_status = Shop.ProvisioningStatus.READY
                shop.provisioned_at = timezone.now()
                shop.provisioning_error = ""
                shop.save(update_fields=["provisioning_status", "provisioned_at", "provisioning_error"])
                try:
                    ensure_tenant_admin_user(shop, shop.owner)
                except Exception as exc:
                    logger.warning("[API] Could not provision tenant admin: %s", exc)

            redirect_url = _build_redirect_url(shop, request)
            return JsonResponse({
                "status": "READY",
                "progress_percentage": 100,
                "current_step": "Store is live! Redirecting...",
                "is_completed": True,
                "redirect_url": redirect_url,
                "applied_count": applied,
                "total_migrations": total,
                "schema_name": schema_name,
                "engine": engine,
            })

        if worker_status == "FAILED":
            return JsonResponse({
                "status": "FAILED",
                "progress_percentage": pct,
                "current_step": progress.get("error") or "Provisioning failed. Contact support.",
                "is_completed": False,
                "is_failed": True,
                "redirect_url": None,
                "schema_name": schema_name,
                "engine": engine,
            })

        # Still RUNNING / DISPATCHED
        return JsonResponse({
            "status": "PROVISIONING",
            "progress_percentage": max(5, pct),
            "current_step": current_step,
            "is_completed": False,
            "redirect_url": None,
            "applied_count": applied,
            "total_migrations": total,
            "schema_name": schema_name,
            "engine": engine,
        })

    # ── No Redis data yet — fall back to DB schema_inspector ──────────────
    # This is a lightweight DB read (only django_migrations table count).
    try:
        from system.account.schema_inspector import get_tenant_migration_status
        mig = get_tenant_migration_status(schema_name, use_cache=True)
        applied = mig.get("applied_count", 0)
        total = mig.get("total_migrations", 0)
        pct = int(mig.get("progress_percent", 5))
        current_stage = mig.get("current_stage") or {}
        step = f"Stage {current_stage.get('stage', '')}:  {current_stage.get('name', 'Setting up database...')}"
    except Exception:
        applied, total, pct, step = 0, 0, 5, "Starting up..."

    return JsonResponse({
        "status": "PROVISIONING",
        "progress_percentage": max(5, pct),
        "current_step": step,
        "is_completed": False,
        "redirect_url": None,
        "applied_count": applied,
        "total_migrations": total,
        "schema_name": schema_name,
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
