from __future__ import annotations

from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.forms import HiddenInput
from django.shortcuts import get_object_or_404, redirect, render
from django_tenants.utils import get_tenant_model, schema_context

from dashboard.feature_marketplace.models import FeaturePurchase, TenantEntitlement
from dashboard.feature_marketplace.services import grant_manual_entitlement
from sabistart_store.navigation import build_platform_navigation
from system.account.platform_support import safe_platform_call, setup_warning_for
from system.core.models import Shop
from system.feature_marketplace.forms import (
    BundleItemForm,
    CouponForm,
    DiscountCampaignForm,
    FeatureBundleForm,
    FeatureCategoryForm,
    FeatureDefinitionForm,
    FeaturePriceForm,
    ManualGrantForm,
    TenantFeatureOverrideForm,
)
from system.feature_marketplace.models import (
    BundleItem,
    Coupon,
    DiscountCampaign,
    FeatureBundle,
    FeatureCategory,
    FeatureDefinition,
    FeatureEntitlementIndex,
    FeaturePrice,
    FeaturePurchaseIndex,
    TenantFeatureOverride,
)
from system.feature_marketplace.services import (
    get_active_bundles,
    get_active_feature_catalog,
    get_marketplace_gateways,
    process_marketplace_payment_event,
    sync_feature_entitlement_index,
)


def _is_platform_staff(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff or getattr(user, "is_platform_admin", False))


def platform_staff_required(view_func):
    return login_required(user_passes_test(_is_platform_staff)(view_func), login_url="platform:login")


FEATURE_NAVIGATION = (
    {"key": "platform_features", "label": "Overview", "route": "platform_features:home"},
    {"key": "platform_features_list", "label": "Features", "route": "platform_features:catalog"},
    {"key": "platform_features_categories", "label": "Categories", "route": "platform_features:categories"},
    {"key": "platform_features_pricing", "label": "Pricing", "route": "platform_features:pricing"},
    {"key": "platform_features_bundles", "label": "Bundles", "route": "platform_features:bundles"},
    {"key": "platform_features_campaigns", "label": "Campaigns", "route": "platform_features:campaigns"},
    {"key": "platform_features_coupons", "label": "Coupons", "route": "platform_features:coupons"},
    {"key": "platform_features_purchases", "label": "Purchases", "route": "platform_features:purchases"},
    {"key": "platform_features_tenants", "label": "Tenant Usage", "route": "platform_features:tenants"},
    {"key": "platform_features_guide", "label": "Developer Guide", "route": "platform_features:guide"},
)

FEATURE_SHARED_MODELS = (
    FeatureCategory,
    FeatureDefinition,
    FeaturePrice,
    FeatureBundle,
    BundleItem,
    DiscountCampaign,
    Coupon,
    FeaturePurchaseIndex,
    TenantFeatureOverride,
    FeatureEntitlementIndex,
)


def _feature_nav(active_key: str):
    from django.urls import reverse

    return [{**item, "url": reverse(item["route"]), "active": item["key"] == active_key} for item in FEATURE_NAVIGATION]


def _platform_context(*, active_platform_nav="platform_features", active_feature_nav="platform_features", page_title="Feature Marketplace", request=None, **extra):
    context = {
        "page_title": page_title,
        "active_platform_nav": active_platform_nav,
        "platform_navigation": build_platform_navigation(active_platform_nav) if request and request.user.is_authenticated else [],
        "feature_navigation": _feature_nav(active_feature_nav),
        "gateway_options": safe_platform_call(get_marketplace_gateways, []),
        "feature_count": safe_platform_call(lambda: FeatureDefinition.objects.count(), 0),
        "bundle_count": safe_platform_call(lambda: FeatureBundle.objects.count(), 0),
        "coupon_count": safe_platform_call(lambda: Coupon.objects.count(), 0),
        "setup_warning": setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS),
    }
    context.update(extra)
    return context


def _sync_entitlement_indices(schema_name: str | None = None) -> int:
    queryset = Shop.objects.all()
    if schema_name:
        queryset = queryset.filter(schema_name=schema_name)
    total = 0
    for shop in queryset:
        total += sync_feature_entitlement_index(shop)
    return total


@platform_staff_required
def home(request):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if request.GET.get("sync") == "1":
        if setup_warning:
            messages.warning(request, setup_warning)
            return redirect("platform_features:home")
        total = _sync_entitlement_indices()
        messages.success(request, f"Rebuilt feature entitlement index rows: {total}.")
        return redirect("platform_features:home")
    context = _platform_context(
        request=request,
        page_title="Feature Marketplace",
        setup_warning=setup_warning,
        recent_purchases=safe_platform_call(lambda: list(FeaturePurchaseIndex.objects.order_by("-created_at")[:10]), []),
        tenants=safe_platform_call(lambda: list(Shop.objects.order_by("name")[:10]), []),
        featured_features=safe_platform_call(
            lambda: list(FeatureDefinition.objects.select_related("category").order_by("display_order", "name")[:8]),
            [],
        ),
    )
    return render(request, "account/features/index.html", context)


@platform_staff_required
def catalog(request):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_features:home")
    q = request.GET.get("q", "").strip()
    category_slug = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()
    features = FeatureDefinition.objects.select_related("category").order_by("display_order", "name")
    if q:
        features = features.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q))
    if category_slug:
        features = features.filter(category__slug=category_slug)
    if status == "free":
        features = features.filter(is_globally_enabled=True)
    elif status == "inactive":
        features = features.filter(is_active=False)
    usage_map = {
        row["feature_code"]: row["tenant_count"]
        for row in FeatureEntitlementIndex.objects.values("feature_code").annotate(tenant_count=Count("schema_name", distinct=True))
    }
    feature_rows = [{"feature": feature, "tenant_usage_count": usage_map.get(feature.code, 0)} for feature in features]
    context = _platform_context(
        request=request,
        page_title="Features",
        active_feature_nav="platform_features_list",
        feature_rows=feature_rows,
        categories=FeatureCategory.objects.order_by("display_order", "name"),
        q=q,
        selected_category=category_slug,
        selected_status=status,
    )
    return render(request, "account/features/features_list.html", context)


@platform_staff_required
def feature_create(request):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_features:home")
    form = FeatureDefinitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        feature = form.save()
        messages.success(request, "Feature created.")
        return redirect("platform_features:feature_detail", code=feature.code)
    context = _platform_context(
        request=request,
        page_title="Add Feature",
        active_feature_nav="platform_features_list",
        form=form,
    )
    return render(request, "account/features/feature_create.html", context)


@platform_staff_required
def feature_detail(request, code):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_features:home")
    feature = get_object_or_404(FeatureDefinition, code=code)
    feature_form = FeatureDefinitionForm(request.POST or None, instance=feature, prefix="feature")
    price_form = FeaturePriceForm(request.POST or None, prefix="price")
    override_form = TenantFeatureOverrideForm(request.POST or None, prefix="override", initial={"feature": feature, "schema_name": request.POST.get("override-schema_name", "")})
    price_form.fields["feature"].initial = feature
    price_form.fields["feature"].widget = HiddenInput()
    override_form.fields["feature"].initial = feature
    override_form.fields["feature"].widget = HiddenInput()
    override_form.fields["shop"].queryset = Shop.objects.order_by("name")
    if request.method == "POST":
        if "save_feature" in request.POST and feature_form.is_valid():
            feature_form.save()
            messages.success(request, "Feature updated.")
            return redirect("platform_features:feature_detail", code=feature.code)
        if "save_price" in request.POST and price_form.is_valid():
            price = price_form.save(commit=False)
            price.feature = feature
            price.save()
            messages.success(request, "Feature pricing saved.")
            return redirect("platform_features:feature_detail", code=feature.code)
        if "save_override" in request.POST and override_form.is_valid():
            override = override_form.save(commit=False)
            override.feature = feature
            if not override.schema_name and override.shop_id:
                override.schema_name = override.shop.schema_name
            override.save()
            messages.success(request, "Tenant override saved.")
            return redirect("platform_features:feature_detail", code=feature.code)
    tenant_usage = FeatureEntitlementIndex.objects.select_related("shop").filter(feature_code=code).order_by("schema_name", "-created_at")
    context = _platform_context(
        request=request,
        page_title=feature.name,
        active_feature_nav="platform_features_list",
        feature=feature,
        feature_form=feature_form,
        price_form=price_form,
        override_form=override_form,
        prices=FeaturePrice.objects.filter(feature=feature).order_by("currency", "billing_cycle"),
        bundle_items=BundleItem.objects.select_related("bundle").filter(feature=feature).order_by("bundle__name"),
        campaigns=DiscountCampaign.objects.filter(applicable_features=feature).order_by("-created_at"),
        coupons=Coupon.objects.filter(applicable_features=feature).order_by("code"),
        tenant_usage=tenant_usage,
        tenant_overrides=TenantFeatureOverride.objects.select_related("shop").filter(feature=feature).order_by("-created_at"),
    )
    return render(request, "account/features/feature_detail.html", context)


@platform_staff_required
def categories(request):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_features:home")
    editing_category = None
    edit_id = request.GET.get("edit")
    if edit_id:
        editing_category = get_object_or_404(FeatureCategory, pk=edit_id)
    form = FeatureCategoryForm(request.POST or None, instance=editing_category)
    if request.method == "POST":
        if "delete_category" in request.POST:
            category = get_object_or_404(FeatureCategory, pk=request.POST.get("category_id"))
            if category.features.exists():
                messages.error(request, "Move or delete the features in this category before deleting it.")
            else:
                category.delete()
                messages.success(request, "Feature category deleted.")
            return redirect("platform_features:categories")
        if form.is_valid():
            form.save()
            messages.success(request, "Feature category saved.")
            return redirect("platform_features:categories")
    context = _platform_context(
        request=request,
        page_title="Feature Categories",
        active_feature_nav="platform_features_categories",
        form=form,
        categories=FeatureCategory.objects.order_by("display_order", "name"),
        editing_category=editing_category,
    )
    return render(request, "account/features/categories.html", context)


@platform_staff_required
def pricing(request):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_features:home")
    form = FeaturePriceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Feature price saved.")
        return redirect("platform_features:pricing")
    context = _platform_context(
        request=request,
        page_title="Pricing",
        active_feature_nav="platform_features_pricing",
        form=form,
        prices=FeaturePrice.objects.select_related("feature").order_by("feature__name", "currency", "billing_cycle"),
    )
    return render(request, "account/features/pricing.html", context)


@platform_staff_required
def bundles(request):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_features:home")
    bundle_form = FeatureBundleForm(request.POST or None, prefix="bundle")
    item_form = BundleItemForm(request.POST or None, prefix="item")
    if request.method == "POST":
        if "save_bundle" in request.POST and bundle_form.is_valid():
            bundle_form.save()
            messages.success(request, "Feature bundle saved.")
            return redirect("platform_features:bundles")
        if "save_item" in request.POST and item_form.is_valid():
            item_form.save()
            messages.success(request, "Bundle item saved.")
            return redirect("platform_features:bundles")
    context = _platform_context(
        request=request,
        page_title="Bundles",
        active_feature_nav="platform_features_bundles",
        bundle_form=bundle_form,
        item_form=item_form,
        bundles=get_active_bundles(),
        all_bundles=FeatureBundle.objects.order_by("name"),
    )
    return render(request, "account/features/bundles.html", context)


@platform_staff_required
def campaigns(request):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_features:home")
    form = DiscountCampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Campaign saved.")
        return redirect("platform_features:campaigns")
    context = _platform_context(
        request=request,
        page_title="Campaigns",
        active_feature_nav="platform_features_campaigns",
        form=form,
        campaigns=DiscountCampaign.objects.order_by("-created_at"),
    )
    return render(request, "account/features/campaigns.html", context)


@platform_staff_required
def coupons(request):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_features:home")
    form = CouponForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Coupon saved.")
        return redirect("platform_features:coupons")
    context = _platform_context(
        request=request,
        page_title="Coupons",
        active_feature_nav="platform_features_coupons",
        form=form,
        coupons=Coupon.objects.order_by("code"),
    )
    return render(request, "account/features/coupons.html", context)


@platform_staff_required
def purchases(request):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_features:home")
    context = _platform_context(
        request=request,
        page_title="Marketplace Purchases",
        active_feature_nav="platform_features_purchases",
        purchases=FeaturePurchaseIndex.objects.order_by("-created_at"),
    )
    return render(request, "account/features/purchases.html", context)


@platform_staff_required
def tenants(request):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_features:home")
    usage_counts = {
        row["schema_name"]: row["feature_count"]
        for row in FeatureEntitlementIndex.objects.values("schema_name").annotate(feature_count=Count("feature_code", distinct=True))
    }
    shops = [
        {"shop": shop, "feature_count": usage_counts.get(shop.schema_name, 0)}
        for shop in Shop.objects.order_by("name")
    ]
    context = _platform_context(
        request=request,
        page_title="Tenant Feature Usage",
        active_feature_nav="platform_features_tenants",
        shops=shops,
    )
    return render(request, "account/features/tenants.html", context)


@platform_staff_required
def tenant_detail(request, schema_name):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_features:home")
    shop = get_object_or_404(Shop, schema_name=schema_name)
    grant_form = ManualGrantForm(request.POST or None)
    entitlements = []
    purchases = []
    with schema_context(schema_name):
        if request.method == "POST" and grant_form.is_valid():
            feature = get_object_or_404(FeatureDefinition, code=grant_form.cleaned_data["feature_code"])
            grant_manual_entitlement(
                feature=feature,
                quantity=grant_form.cleaned_data.get("quantity") or None,
                note=grant_form.cleaned_data.get("note", ""),
                billing_cycle=grant_form.cleaned_data.get("billing_cycle") or "perpetual",
            )
            messages.success(request, f"Granted {feature.name} to {shop.name}.")
            _sync_entitlement_indices(schema_name)
            return redirect("platform_features:tenant_detail", schema_name=schema_name)
        entitlements = list(TenantEntitlement.objects.order_by("-created_at")[:20])
        purchases = list(FeaturePurchase.objects.order_by("-created_at")[:20])
    context = _platform_context(
        request=request,
        page_title=f"{shop.name} Marketplace",
        active_feature_nav="platform_features_tenants",
        shop=shop,
        grant_form=grant_form,
        entitlements=entitlements,
        purchases=purchases,
        overrides=TenantFeatureOverride.objects.filter(schema_name=schema_name).select_related("feature").order_by("-created_at"),
    )
    return render(request, "account/features/tenant_detail.html", context)


@platform_staff_required
def guide(request):
    guide_path = Path("system/feature_marketplace/FEATURE_ADDITION_GUIDE.md")
    guide_markdown = guide_path.read_text(encoding="utf-8") if guide_path.exists() else "Guide file not found."
    context = _platform_context(
        request=request,
        page_title="Feature Developer Guide",
        active_feature_nav="platform_features_guide",
        guide_markdown=guide_markdown,
        guide_path=str(guide_path),
    )
    return render(request, "account/features/guide.html", context)


def checkout_session(request, purchase_reference):
    setup_warning = setup_warning_for("Feature marketplace", *FEATURE_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("system_pay:marketplace_checkout", purchase_reference=purchase_reference)
    if not _is_platform_staff(request.user):
        return redirect("system_pay:marketplace_checkout", purchase_reference=purchase_reference)
    index = get_object_or_404(FeaturePurchaseIndex, purchase_reference=purchase_reference)
    with schema_context(index.schema_name):
        purchase = get_object_or_404(FeaturePurchase, purchase_reference=purchase_reference)
        if request.method == "POST":
            if request.POST.get("action") == "confirm":
                result = process_marketplace_payment_event(
                    payment_status="success",
                    purchase_reference=purchase.purchase_reference,
                    gateway_reference=f"marketplace_{purchase.purchase_reference}",
                    gateway_transaction_id=f"marketplace_tx_{purchase.purchase_reference}",
                    metadata={"confirmed_by_platform_user": getattr(request.user, "email", "")},
                )
                if result.success:
                    messages.success(request, "Marketplace purchase completed.")
                    return redirect(result.redirect_url or purchase.success_redirect_url or "platform_features:purchases")
                messages.error(request, "; ".join(result.errors) or result.message or "Unable to complete marketplace purchase.")
            if request.POST.get("action") == "cancel":
                result = process_marketplace_payment_event(
                    payment_status="cancelled",
                    purchase_reference=purchase.purchase_reference,
                    metadata={"cancelled_by_platform_user": getattr(request.user, "email", "")},
                )
                if result.success:
                    messages.info(request, "Marketplace purchase cancelled.")
                    return redirect(result.redirect_url or purchase.cancel_redirect_url or "platform_features:purchases")
                messages.error(request, "; ".join(result.errors) or result.message or "Unable to cancel marketplace purchase.")
    context = _platform_context(
        request=request,
        active_platform_nav="platform_features" if request.user.is_authenticated else "",
        active_feature_nav="platform_features_purchases",
        page_title="Marketplace Checkout",
        index=index,
        purchase=purchase,
    )
    return render(request, "account/features/checkout_session.html", context)
