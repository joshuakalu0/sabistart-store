"""Platform dashboard views."""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views import View

from sabistart_store.navigation import build_platform_navigation
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
