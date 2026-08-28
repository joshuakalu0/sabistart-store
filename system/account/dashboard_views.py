"""Platform dashboard views."""

from __future__ import annotations

import json

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator

from sabistart.navigation import build_platform_navigation
from dashboard.analytics.services import build_platform_dashboard_bundle, bundle_to_json
from system.account.platform_support import safe_platform_call, setup_warning_for
from system.core.models import Shop


def _is_platform_staff(user) -> bool:
    return bool(
        user.is_authenticated
        and (user.is_superuser or user.is_staff or getattr(user, "is_platform_admin", False))
    )


class PlatformStaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = "platform:login"

    def test_func(self):
        return _is_platform_staff(self.request.user)


def _base_shop_queryset():
    return Shop.objects.select_related("owner").annotate(domain_count=Count("domains")).order_by("-created_on")


def _shop_context(request, *, active_platform_nav: str, page_title: str, shops=None, **extra):
    shops = shops if shops is not None else _base_shop_queryset()
    context = {
        "page_title": page_title,
        "active_platform_nav": active_platform_nav,
        "platform_navigation": build_platform_navigation(active_platform_nav),
        "shops": shops,
        "shop_count": shops.count() if hasattr(shops, "count") else len(shops),
    }
    context.update(extra)
    return context


def _store_detail_sections(shop: Shop) -> dict:
    from dashboard.domain.models import CustomDomain
    from system.feature_marketplace.models import FeatureEntitlementIndex
    from system.system_pay.models import (
        PlatformDisputeIndex,
        PlatformPayoutIndex,
        PlatformRefundIndex,
        PlatformTransactionIndex,
        TenantGatewaySnapshot,
        TenantPaymentSnapshot,
    )

    warnings: list[str] = []
    payment_warning = setup_warning_for(
        "Platform payment projections",
        TenantPaymentSnapshot,
        TenantGatewaySnapshot,
        PlatformTransactionIndex,
        PlatformPayoutIndex,
        PlatformRefundIndex,
        PlatformDisputeIndex,
    )
    if payment_warning:
        warnings.append(payment_warning)
    feature_warning = setup_warning_for(
        "Platform feature reporting",
        FeatureEntitlementIndex,
    )
    if feature_warning:
        warnings.append(feature_warning)
    domain_warning = setup_warning_for(
        "Platform domain management",
        CustomDomain,
    )
    if domain_warning:
        warnings.append(domain_warning)

    payment_snapshot = safe_platform_call(
        lambda: TenantPaymentSnapshot.objects.filter(schema_name=shop.schema_name).first(),
        None,
    )
    gateway_snapshots = safe_platform_call(
        lambda: list(TenantGatewaySnapshot.objects.filter(schema_name=shop.schema_name).order_by("gateway_name")),
        [],
    )
    feature_usage = safe_platform_call(
        lambda: list(FeatureEntitlementIndex.objects.filter(schema_name=shop.schema_name).order_by("feature_name")[:20]),
        [],
    )
    domains = safe_platform_call(
        lambda: list(
            CustomDomain.objects.filter(tenant=shop)
            .exclude(status=CustomDomain.Status.REMOVED)
            .order_by("-is_primary", "domain")[:20]
        ),
        [],
    )
    transaction_count = safe_platform_call(
        lambda: PlatformTransactionIndex.objects.filter(schema_name=shop.schema_name).count(),
        0,
    )
    payout_count = safe_platform_call(
        lambda: PlatformPayoutIndex.objects.filter(schema_name=shop.schema_name).count(),
        0,
    )
    refund_count = safe_platform_call(
        lambda: PlatformRefundIndex.objects.filter(schema_name=shop.schema_name).count(),
        0,
    )
    dispute_count = safe_platform_call(
        lambda: PlatformDisputeIndex.objects.filter(schema_name=shop.schema_name).count(),
        0,
    )

    return {
        "payment_snapshot": payment_snapshot,
        "gateway_snapshots": gateway_snapshots,
        "feature_usage": feature_usage,
        "domains": domains,
        "warnings": warnings,
        "payment_counts": {
            "transactions": transaction_count,
            "payouts": payout_count,
            "refunds": refund_count,
            "disputes": dispute_count,
        },
    }


class PlatformDashboardView(PlatformStaffRequiredMixin, View):
    """Global platform dashboard - app hub and tenant overview."""

    template_name = "account/dashboard.html"

    def get(self, request):
        shops = _base_shop_queryset()
        app_cards = [
            {
                "title": "Stores",
                "description": "Inspect every tenant, drill into operational detail, and jump into support flows.",
                "icon": "storefront",
                "url": reverse("platform:stores"),
            },
            {
                "title": "Feature Marketplace",
                "description": "Manage catalog items, overrides, pricing, bundles, coupons, and feature usage.",
                "icon": "store",
                "url": reverse("platform_features:home"),
            },
            {
                "title": "Payments",
                "description": "Review platform gateways, tenant payment health, and indexed transaction activity.",
                "icon": "payments",
                "url": reverse("platform_payments:home"),
            },
        ]
        context = _shop_context(
            request,
            active_platform_nav="platform_dashboard",
            page_title="Platform Dashboard",
            shops=shops,
            app_cards=app_cards,
            recent_shops=shops[:8],
            platform_analytics=build_platform_dashboard_bundle(),
        )
        context["platform_analytics_json"] = bundle_to_json(context["platform_analytics"])
        return render(request, self.template_name, context)


class PlatformStoresView(PlatformStaffRequiredMixin, View):
    """Global tenant list for platform staff."""

    template_name = "account/stores.html"

    def get(self, request):
        shops = _base_shop_queryset()
        context = _shop_context(
            request,
            active_platform_nav="platform_stores",
            page_title="Stores",
            shops=shops,
        )
        return render(request, self.template_name, context)


class PlatformStoreDetailView(PlatformStaffRequiredMixin, View):
    """Operational detail page for a tenant shop."""

    template_name = "account/store_detail.html"

    def get(self, request, schema_name: str):
        shop = get_object_or_404(_base_shop_queryset(), schema_name=schema_name)
        sections = _store_detail_sections(shop)
        active_tab = request.GET.get("tab", "overview")
        if active_tab not in {"overview", "payments", "features", "domains"}:
            active_tab = "overview"
        tab_defs = (
            {"key": "overview", "label": "Overview"},
            {"key": "payments", "label": "Payments"},
            {"key": "features", "label": "Features"},
            {"key": "domains", "label": "Domains"},
        )
        tabs = []
        for item in tab_defs:
            tabs.append(
                {
                    **item,
                    "active": item["key"] == active_tab,
                    "url": f"{reverse('platform:store_detail', args=[shop.schema_name])}?tab={item['key']}",
                }
            )
        context = _shop_context(
            request,
            active_platform_nav="platform_stores",
            page_title=shop.name,
            shops=_base_shop_queryset()[:10],
            shop=shop,
            tabs=tabs,
            active_tab=active_tab,
            platform_store_tabs=sections,
            setup_warnings=sections["warnings"],
        )
        return render(request, self.template_name, context)


class PlatformDiagnosticsView(PlatformStaffRequiredMixin, View):
    """Platform service diagnostics page — super admin only."""

    template_name = "account/diagnostics.html"

    def get(self, request):
        from system.diagnostics.services import SECTIONS
        # Build skeleton sections for initial page render (checks run client-side via AJAX)
        skeleton_sections = [
            {
                "key": key,
                "label": meta["label"],
                "icon": meta["icon"],
                "description": meta["description"],
                "overall": "unknown",
                "checks": [],
            }
            for key, meta in SECTIONS.items()
        ]
        context = {
            "page_title": "Service Diagnostics",
            "active_platform_nav": "platform_diagnostics",
            "platform_navigation": build_platform_navigation("platform_diagnostics"),
            "sections": skeleton_sections,
            "diagnostics_run_url": reverse("platform:diagnostics_run"),
        }
        return render(request, self.template_name, context)


@method_decorator(csrf_protect, name="dispatch")
class PlatformDiagnosticsRunView(PlatformStaffRequiredMixin, View):
    """AJAX endpoint — runs diagnostic checks and returns JSON."""

    def post(self, request):
        from system.diagnostics.services import run_section, run_all_diagnostics, SECTIONS
        try:
            body = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, ValueError):
            body = {}

        section_key = body.get("section", "").strip()

        if section_key == "all":
            sections = run_all_diagnostics()
            return JsonResponse({"ok": True, "sections": sections})

        if section_key and section_key in SECTIONS:
            checks = run_section(section_key)
            statuses = [c["status"] for c in checks]
            if "error" in statuses:
                overall = "error"
            elif "warning" in statuses:
                overall = "warning"
            elif all(s == "ok" for s in statuses):
                overall = "ok"
            else:
                overall = "unknown"
            return JsonResponse({
                "ok": True,
                "section": section_key,
                "overall": overall,
                "checks": checks,
            })

        return JsonResponse({"ok": False, "error": f"Unknown section: '{section_key}'"}, status=400)


# =============================================================================
# USER MANAGEMENT VIEWS
# =============================================================================

class PlatformUsersView(PlatformStaffRequiredMixin, View):
    """Platform users directory and account management."""

    template_name = "account/users.html"

    def get(self, request):
        from system.account.models import PlatformUser
        from django.db.models import Q

        q = request.GET.get("q", "").strip()
        status_filter = request.GET.get("status", "").strip().upper()

        users_qs = (
            PlatformUser.objects.prefetch_related("owned_shops", "owned_shops__domains")
            .order_by("-created_at")
        )

        if q:
            users_qs = users_qs.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
            )

        if status_filter and status_filter in dict(PlatformUser.AccountStatus.choices):
            users_qs = users_qs.filter(account_status=status_filter)

        total_users = PlatformUser.objects.count()
        active_users = PlatformUser.objects.filter(account_status=PlatformUser.AccountStatus.ACTIVE).count()
        pending_users = PlatformUser.objects.filter(account_status=PlatformUser.AccountStatus.PENDING).count()
        suspended_users = PlatformUser.objects.filter(account_status=PlatformUser.AccountStatus.SUSPENDED).count()

        context = {
            "page_title": "User Management",
            "active_platform_nav": "platform_users",
            "platform_navigation": build_platform_navigation("platform_users"),
            "users": users_qs,
            "q": q,
            "status_filter": status_filter,
            "stats": {
                "total": total_users,
                "active": active_users,
                "pending": pending_users,
                "suspended": suspended_users,
            },
        }
        return render(request, self.template_name, context)


class PlatformUserDetailView(PlatformStaffRequiredMixin, View):
    """Detailed inspector for a single platform user."""

    template_name = "account/user_detail.html"

    def get(self, request, user_id):
        from system.account.models import PlatformUser, OnboardingSession, PlatformLoginAuditLog
        user = get_object_or_404(PlatformUser, id=user_id)
        shops = user.owned_shops.prefetch_related("domains").order_by("-created_on")
        sessions = OnboardingSession.objects.filter(email__iexact=user.email).order_by("-created_at")[:10]
        audit_logs = PlatformLoginAuditLog.objects.filter(user=user).order_by("-created_at")[:20]

        context = {
            "page_title": f"User: {user.get_full_name() or user.email}",
            "active_platform_nav": "platform_users",
            "platform_navigation": build_platform_navigation("platform_users"),
            "target_user": user,
            "shops": shops,
            "sessions": sessions,
            "audit_logs": audit_logs,
        }
        return render(request, self.template_name, context)


@method_decorator(csrf_protect, name="dispatch")
class PlatformUserDeleteView(PlatformStaffRequiredMixin, View):
    """
    Safely deletes a PlatformUser and completely drops all associated
    PostgreSQL schemas (CASCADE), tenant shops, domains, and onboarding sessions.
    """

    def post(self, request, user_id):
        from system.account.models import PlatformUser, OnboardingSession
        from system.core.models import Shop, Domain
        from django.db import connection
        from django.contrib import messages
        from django.shortcuts import redirect

        user = get_object_or_404(PlatformUser, id=user_id)

        # Safety check: prevent superadmins from deleting their own current session
        if request.user.id == user.id:
            messages.error(request, "You cannot delete your own logged-in account.")
            return redirect("platform:users")

        user_email = user.email
        shops = list(Shop.objects.filter(owner=user))
        dropped_schemas = []

        for shop in shops:
            schema = shop.schema_name
            if schema and schema not in ("public", "shared", "information_schema", "pg_catalog"):
                with connection.cursor() as cursor:
                    cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE;')
                dropped_schemas.append(schema)

            Domain.objects.filter(tenant=shop).delete()
            shop.delete()

        # Clean up related onboarding sessions
        OnboardingSession.objects.filter(email__iexact=user_email).delete()

        # Delete the user
        user.delete()

        msg = f"User '{user_email}' deleted successfully."
        if dropped_schemas:
            msg += f" Dropped {len(dropped_schemas)} schema(s): {', '.join(dropped_schemas)}."
        messages.success(request, msg)

        return redirect("platform:users")


@method_decorator(csrf_protect, name="dispatch")
class PlatformUserStatusToggleView(PlatformStaffRequiredMixin, View):
    """Toggle a platform user's account status (Active <-> Suspended)."""

    def post(self, request, user_id):
        from system.account.models import PlatformUser
        from django.contrib import messages
        from django.shortcuts import redirect

        user = get_object_or_404(PlatformUser, id=user_id)
        if request.user.id == user.id:
            messages.error(request, "You cannot change the status of your own logged-in account.")
            return redirect("platform:users")

        if user.account_status == PlatformUser.AccountStatus.ACTIVE:
            user.account_status = PlatformUser.AccountStatus.SUSPENDED
            messages.warning(request, f"User '{user.email}' has been suspended.")
        else:
            user.account_status = PlatformUser.AccountStatus.ACTIVE
            messages.success(request, f"User '{user.email}' has been activated.")

        user.save(update_fields=["account_status", "updated_at"])
        return redirect(request.META.get("HTTP_REFERER") or "platform:users")


# =============================================================================
# PROVISIONING & CELERY MIGRATION LOG VIEWS
# =============================================================================

class PlatformProvisioningLogsView(PlatformStaffRequiredMixin, View):
    """Live Celery tenant provisioning dashboard & migration logs."""

    template_name = "account/provisioning_logs.html"

    def get(self, request):
        from system.core.models import Shop
        from django.db import connection
        import logging

        logger = logging.getLogger(__name__)
        status_filter = request.GET.get("status", "").strip().lower()

        try:
            shops_qs = Shop.objects.select_related("owner").prefetch_related("domains").order_by("-created_on")
            if status_filter and status_filter in dict(Shop.ProvisioningStatus.choices):
                shops_qs = shops_qs.filter(provisioning_status=status_filter)

            total_shops = Shop.objects.count()
            ready_shops = Shop.objects.filter(provisioning_status=Shop.ProvisioningStatus.READY).count()
            in_progress_shops = Shop.objects.filter(provisioning_status=Shop.ProvisioningStatus.IN_PROGRESS).count()
            failed_shops = Shop.objects.filter(provisioning_status=Shop.ProvisioningStatus.FAILED).count()
            pending_shops = Shop.objects.filter(provisioning_status=Shop.ProvisioningStatus.PENDING).count()
        except Exception as e:
            logger.exception("Error loading shop provisioning list: %s", e)
            shops_qs = []
            total_shops = ready_shops = in_progress_shops = failed_shops = pending_shops = 0

        # Safely find orphaned schemas in Postgres
        orphaned_schemas = []
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'onboard_%';")
                dangling_schemas = [row[0] for row in cursor.fetchall()]

            active_schemas = set(Shop.objects.values_list("schema_name", flat=True))
            orphaned_schemas = [s for s in dangling_schemas if s not in active_schemas]
        except Exception as e:
            logger.warning("Could not inspect information_schema.schemata: %s", e)
            orphaned_schemas = []

        context = {
            "page_title": "Store Provisioning & Migration Logs",
            "active_platform_nav": "platform_provisioning",
            "platform_navigation": build_platform_navigation("platform_provisioning"),
            "shops": shops_qs,
            "status_filter": status_filter,
            "orphaned_schemas": orphaned_schemas,
            "stats": {
                "total": total_shops,
                "ready": ready_shops,
                "in_progress": in_progress_shops,
                "failed": failed_shops,
                "pending": pending_shops,
                "orphaned": len(orphaned_schemas),
            },
        }
        return render(request, self.template_name, context)


@method_decorator(csrf_protect, name="dispatch")
class PlatformProvisioningRetryView(PlatformStaffRequiredMixin, View):
    """Retry Celery async provisioning and tenant migrations for a shop."""

    def post(self, request, schema_name):
        from system.core.models import Shop
        from system.account.tasks import provision_tenant_schema_task
        from django.contrib import messages
        from django.shortcuts import redirect

        shop = get_object_or_404(Shop, schema_name=schema_name)
        shop.provisioning_status = Shop.ProvisioningStatus.PENDING
        shop.provisioning_error = ""
        shop.save(update_fields=["provisioning_status", "provisioning_error"])

        try:
            provision_tenant_schema_task.delay(schema_name=shop.schema_name)
            messages.success(request, f"Provisioning task enqueued for store '{shop.name}' ({shop.schema_name}). Check logs for progress.")
        except Exception as e:
            messages.error(request, f"Failed to enqueue task: {str(e)}")

        return redirect("platform:provisioning_logs")


@method_decorator(csrf_protect, name="dispatch")
class PlatformProvisioningDropSchemaView(PlatformStaffRequiredMixin, View):
    """Drop an orphaned PostgreSQL schema from the database."""

    def post(self, request, schema_name):
        from django.db import connection
        from django.contrib import messages
        from django.shortcuts import redirect

        schema_name = schema_name.strip().lower()
        if schema_name in ("public", "shared", "information_schema", "pg_catalog"):
            messages.error(request, f"Cannot drop protected system schema '{schema_name}'.")
            return redirect("platform:provisioning_logs")

        try:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE;')
            messages.success(request, f"Orphaned schema '{schema_name}' was dropped successfully.")
        except Exception as e:
            messages.error(request, f"Error dropping schema '{schema_name}': {str(e)}")

        return redirect("platform:provisioning_logs")

