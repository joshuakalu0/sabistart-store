from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods

from dashboard.decorators import dashboard_prefix_required
from dashboard.feature_marketplace.forms import MarketplaceCheckoutForm
from dashboard.feature_marketplace.integration_registry import USAGE_SNAPSHOT_FEATURE_CODES
from dashboard.feature_marketplace.models import FeaturePurchase
from dashboard.feature_marketplace.services import (
    FeatureEntitlementEngine,
    create_purchase,
    initialize_purchase_payment,
    list_active_entitlements,
    list_expiring_entitlements,
    list_recent_purchases,
    preview_purchase,
)
from dashboard.feature_marketplace.view_utils import build_page_context
from system.feature_marketplace.services import (
    get_active_bundles,
    get_active_feature_catalog,
    get_bundle_by_slug,
    get_feature_by_code,
)


def _bind_gateway_choices(form, preview):
    gateway_field = form.fields["gateway_provider"]
    choices = [("", "Select a payment gateway")]
    if preview and preview.success:
        choices.extend(
            (gateway["provider"], gateway["name"])
            for gateway in preview.gateways
        )
    gateway_field.choices = choices
    if len(choices) == 2 and not form.initial.get("gateway_provider"):
        form.initial["gateway_provider"] = choices[1][0]
        if "gateway_provider" not in form.data:
            form.fields["gateway_provider"].initial = choices[1][0]


def _preview_from_form_payload(form) -> object | None:
    source = form.data if form.is_bound else form.initial
    if not source:
        return None
    feature_code = source.get("feature_code", "")
    bundle_slug = source.get("bundle_slug", "")
    currency = source.get("currency", "NGN")
    billing_cycle = source.get("billing_cycle", "monthly")
    quantity = source.get("quantity", 1)
    coupon_code = source.get("coupon_code", "")
    try:
        quantity = int(quantity or 1)
    except (TypeError, ValueError):
        quantity = 1
    if not feature_code and not bundle_slug:
        return None
    return preview_purchase(
        feature_code=feature_code,
        bundle_slug=bundle_slug,
        currency=currency,
        billing_cycle=billing_cycle,
        quantity=quantity,
        coupon_code=coupon_code,
    )


@login_required
@dashboard_prefix_required
def home(request, prefix):
    engine = FeatureEntitlementEngine()
    purchases = list_recent_purchases(limit=8)
    expiring = list_expiring_entitlements(within_days=14)[:6]
    has_analytics_offer = get_active_feature_catalog(purchasable_only=True).filter(code="advanced_analytics").exists()
    context = build_page_context(
        prefix,
        "Feature Marketplace",
        "marketplace_overview",
        purchases=purchases,
        expiring_entitlements=expiring,
        available_gateways_count=len(preview_purchase(feature_code="advanced_analytics").gateways if has_analytics_offer else []),
        active_feature_count=sum(1 for snapshot in engine.get_all_entitlements().values() if snapshot.active),
        quota_snapshots=[engine.get_usage_snapshot(code) for code in USAGE_SNAPSHOT_FEATURE_CODES],
    )
    return render(request, "dashboard/feature_marketplace/index.html", context)


@login_required
@dashboard_prefix_required
def catalog(request, prefix):
    currency = request.GET.get("currency", "NGN")
    features = get_active_feature_catalog(currency=currency, purchasable_only=True)
    bundles = get_active_bundles(currency=currency, current_only=True)
    context = build_page_context(
        prefix,
        "Marketplace Catalog",
        "marketplace_catalog",
        currency=currency,
        features=features,
        bundles=bundles,
    )
    return render(request, "dashboard/feature_marketplace/catalog.html", context)


@login_required
@dashboard_prefix_required
def feature_detail(request, prefix, code):
    feature = get_feature_by_code(code, purchasable_only=True)
    default_price = feature.prices.filter(is_active=True).order_by("currency", "amount").first()
    form = MarketplaceCheckoutForm(
        initial={
            "feature_code": feature.code,
            "currency": default_price.currency if default_price else "NGN",
            "billing_cycle": default_price.billing_cycle if default_price else "monthly",
            "quantity": 1,
        }
    )
    preview = preview_purchase(
        feature_code=feature.code,
        currency=form.initial["currency"],
        billing_cycle=form.initial["billing_cycle"],
        quantity=1,
    )
    _bind_gateway_choices(form, preview)
    context = build_page_context(
        prefix,
        feature.name,
        "marketplace_catalog",
        feature=feature,
        form=form,
        preview=preview,
    )
    return render(request, "dashboard/feature_marketplace/feature_detail.html", context)


@login_required
@dashboard_prefix_required
def bundle_detail(request, prefix, slug):
    bundle = get_bundle_by_slug(slug)
    form = MarketplaceCheckoutForm(
        initial={
            "bundle_slug": bundle.slug,
            "currency": bundle.currency,
            "billing_cycle": bundle.billing_cycle,
            "quantity": 1,
        }
    )
    preview = preview_purchase(
        bundle_slug=bundle.slug,
        currency=bundle.currency,
        billing_cycle=bundle.billing_cycle,
        quantity=1,
    )
    _bind_gateway_choices(form, preview)
    context = build_page_context(
        prefix,
        bundle.name,
        "marketplace_catalog",
        bundle=bundle,
        form=form,
        preview=preview,
    )
    return render(request, "dashboard/feature_marketplace/bundle_detail.html", context)


@login_required
@dashboard_prefix_required
def checkout(request, prefix):
    form = MarketplaceCheckoutForm(request.POST or request.GET or None)
    preview = None
    initial_preview = _preview_from_form_payload(form)
    _bind_gateway_choices(form, initial_preview)
    if form.is_valid():
        preview = preview_purchase(
            feature_code=form.cleaned_data.get("feature_code", ""),
            bundle_slug=form.cleaned_data.get("bundle_slug", ""),
            currency=form.cleaned_data["currency"],
            billing_cycle=form.cleaned_data["billing_cycle"],
            quantity=form.cleaned_data["quantity"],
            coupon_code=form.cleaned_data.get("coupon_code", ""),
        )
        _bind_gateway_choices(form, preview)
        if request.method == "POST" and preview.success:
            success_redirect_url = request.build_absolute_uri(
                reverse("dashboard:feature_marketplace:purchase_success", kwargs={"prefix": prefix, "purchase_reference": "PURCHASE_REFERENCE"})
            )
            cancel_redirect_url = request.build_absolute_uri(
                reverse("dashboard:feature_marketplace:purchase_cancel", kwargs={"prefix": prefix, "purchase_reference": "PURCHASE_REFERENCE"})
            )
            purchase = create_purchase(
                schema_name=request.tenant.schema_name,
                feature_code=form.cleaned_data.get("feature_code", ""),
                bundle_slug=form.cleaned_data.get("bundle_slug", ""),
                currency=form.cleaned_data["currency"],
                billing_cycle=form.cleaned_data["billing_cycle"],
                quantity=form.cleaned_data["quantity"],
                coupon_code=form.cleaned_data.get("coupon_code", ""),
                gateway_provider=form.cleaned_data.get("gateway_provider", ""),
                initiated_by=request.user,
                success_redirect_url="",
                cancel_redirect_url="",
            )
            purchase.success_redirect_url = success_redirect_url.replace("PURCHASE_REFERENCE", purchase.purchase_reference)
            purchase.cancel_redirect_url = cancel_redirect_url.replace("PURCHASE_REFERENCE", purchase.purchase_reference)
            purchase.save(update_fields=["success_redirect_url", "cancel_redirect_url", "updated_at"])
            callback_url = ""
            host = request.get_host().split(":")[0].lower()
            _local_hosts = ("localhost", "127.0.0.1", "0.0.0.0")
            if host not in _local_hosts and not host.endswith(".local"):
                callback_url = request.build_absolute_uri(
                    reverse("system_pay:marketplace_payment_callback", kwargs={"purchase_reference": purchase.purchase_reference})
                )
            try:
                intent_result = initialize_purchase_payment(
                    purchase=purchase,
                    initiated_by=request.user,
                    customer_ip=request.META.get("REMOTE_ADDR", ""),
                    callback_url=callback_url,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect(reverse("dashboard:feature_marketplace:checkout", kwargs={"prefix": prefix}))
            hosted_checkout_url = intent_result.authorization_url or purchase.payment_metadata.get("provider_checkout_url", "")
            if hosted_checkout_url:
                messages.success(request, "Purchase created. Redirecting to payment gateway.")
                return redirect(hosted_checkout_url)
            if purchase.gateway_provider not in {"manual", "cod"}:
                messages.error(
                    request,
                    f'{purchase.gateway_name or purchase.gateway_provider.title()} did not return a hosted checkout URL. '
                    "Check the gateway keys and configuration before trying again."
                )
                return redirect(reverse("dashboard:feature_marketplace:checkout", kwargs={"prefix": prefix}) + f"?purchase={purchase.purchase_reference}")
            messages.success(request, "Purchase created. Continue to payment.")
            return redirect(
                purchase.payment_metadata.get("checkout_url")
                or reverse("system_pay:marketplace_checkout", kwargs={"purchase_reference": purchase.purchase_reference})
            )
        if request.method == "POST" and not preview.success:
            messages.error(request, "; ".join(preview.errors) or preview.message or "Unable to prepare checkout.")
    else:
        preview = initial_preview

    context = build_page_context(
        prefix,
        "Marketplace Checkout",
        "marketplace_catalog",
        form=form,
        preview=preview,
    )
    return render(request, "dashboard/feature_marketplace/checkout.html", context)


@login_required
@dashboard_prefix_required
def purchases(request, prefix):
    qs = FeaturePurchase.objects.order_by("-created_at")
    context = build_page_context(
        prefix,
        "Marketplace Purchases",
        "marketplace_purchases",
        purchases=qs,
    )
    return render(request, "dashboard/feature_marketplace/purchases.html", context)


@login_required
@dashboard_prefix_required
def entitlements(request, prefix):
    context = build_page_context(
        prefix,
        "Active Entitlements",
        "marketplace_entitlements",
        entitlements=list_active_entitlements(),
    )
    return render(request, "dashboard/feature_marketplace/entitlements.html", context)


@login_required
@dashboard_prefix_required
def usage(request, prefix):
    engine = FeatureEntitlementEngine()
    snapshots = [engine.get_usage_snapshot(code) for code in USAGE_SNAPSHOT_FEATURE_CODES]
    context = build_page_context(
        prefix,
        "Usage & Quotas",
        "marketplace_usage",
        snapshots=snapshots,
    )
    return render(request, "dashboard/feature_marketplace/usage.html", context)


@login_required
@dashboard_prefix_required
def purchase_success(request, prefix, purchase_reference):
    purchase = get_object_or_404(FeaturePurchase, purchase_reference=purchase_reference)
    context = build_page_context(
        prefix,
        "Purchase Complete",
        "marketplace_purchases",
        purchase=purchase,
    )
    return render(request, "dashboard/feature_marketplace/purchase_status.html", context)


@login_required
@dashboard_prefix_required
def purchase_cancel(request, prefix, purchase_reference):
    purchase = get_object_or_404(FeaturePurchase, purchase_reference=purchase_reference)
    context = build_page_context(
        prefix,
        "Purchase Cancelled",
        "marketplace_purchases",
        purchase=purchase,
        cancelled=True,
    )
    return render(request, "dashboard/feature_marketplace/purchase_status.html", context)


# ─────────────────────────────────────────────────────────────────────────────
# ONE-CLICK CHECKOUT  – creates a purchase and immediately redirects to gateway
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def checkout_direct(request, prefix):
    """
    POST with the checkout form fields → create purchase → redirect to gateway.

    The bundle/feature detail page POSTs here instead of going to the generic
    /checkout/ page, so the user lands directly at the payment gateway without
    any intermediate review step.

    On success → HTTP 302 to gateway hosted-checkout URL.
    On failure → JSON {success:false, error} (AJAX) or messages + redirect (plain).
    """
    from django.views.decorators.http import require_http_methods  # local guard

    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or \
              request.content_type == "application/json"

    form = MarketplaceCheckoutForm(request.POST)
    preview = _preview_from_form_payload(form)
    _bind_gateway_choices(form, preview)

    if not form.is_valid():
        error_msg = "; ".join(
            f"{k}: {v[0]}" for k, v in form.errors.items()
        )
        if is_ajax:
            return JsonResponse({"success": False, "error": error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect(request.META.get("HTTP_REFERER", reverse(
            "dashboard:feature_marketplace:catalog", kwargs={"prefix": prefix}
        )))

    if not preview or not preview.success:
        error_msg = "; ".join(preview.errors) if preview else "Could not compute price."
        if is_ajax:
            return JsonResponse({"success": False, "error": error_msg}, status=400)
        messages.error(request, error_msg)
        return redirect(request.META.get("HTTP_REFERER", reverse(
            "dashboard:feature_marketplace:catalog", kwargs={"prefix": prefix}
        )))

    # Build redirect URLs
    success_redirect_url = request.build_absolute_uri(
        reverse("dashboard:feature_marketplace:purchase_success",
                kwargs={"prefix": prefix, "purchase_reference": "PURCHASE_REFERENCE"})
    )
    cancel_redirect_url = request.build_absolute_uri(
        reverse("dashboard:feature_marketplace:purchase_cancel",
                kwargs={"prefix": prefix, "purchase_reference": "PURCHASE_REFERENCE"})
    )

    purchase = create_purchase(
        schema_name=request.tenant.schema_name,
        feature_code=form.cleaned_data.get("feature_code", ""),
        bundle_slug=form.cleaned_data.get("bundle_slug", ""),
        currency=form.cleaned_data["currency"],
        billing_cycle=form.cleaned_data["billing_cycle"],
        quantity=form.cleaned_data["quantity"],
        coupon_code=form.cleaned_data.get("coupon_code", ""),
        gateway_provider=form.cleaned_data.get("gateway_provider", ""),
        initiated_by=request.user,
        success_redirect_url="",
        cancel_redirect_url="",
    )
    purchase.success_redirect_url = success_redirect_url.replace("PURCHASE_REFERENCE", purchase.purchase_reference)
    purchase.cancel_redirect_url  = cancel_redirect_url.replace("PURCHASE_REFERENCE", purchase.purchase_reference)
    purchase.save(update_fields=["success_redirect_url", "cancel_redirect_url", "updated_at"])

    callback_url = ""
    host = request.get_host().split(":")[0].lower()
    _local_hosts = ("localhost", "127.0.0.1", "0.0.0.0")
    if host not in _local_hosts and not host.endswith(".local"):
        callback_url = request.build_absolute_uri(
            reverse("system_pay:marketplace_payment_callback",
                    kwargs={"purchase_reference": purchase.purchase_reference})
        )

    try:
        intent_result = initialize_purchase_payment(
            purchase=purchase,
            initiated_by=request.user,
            customer_ip=request.META.get("REMOTE_ADDR", ""),
            callback_url=callback_url,
        )
    except ValueError as exc:
        if is_ajax:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)
        messages.error(request, str(exc))
        return redirect(request.META.get("HTTP_REFERER", reverse(
            "dashboard:feature_marketplace:catalog", kwargs={"prefix": prefix}
        )))

    hosted_url = (
        intent_result.authorization_url
        or purchase.payment_metadata.get("provider_checkout_url", "")
    )

    if hosted_url:
        if is_ajax:
            return JsonResponse({"success": True, "redirect_url": hosted_url})
        return redirect(hosted_url)

    # Fallback for manual / COD gateways
    fallback_url = (
        purchase.payment_metadata.get("checkout_url")
        or reverse("system_pay:marketplace_checkout",
                   kwargs={"purchase_reference": purchase.purchase_reference})
    )
    if is_ajax:
        return JsonResponse({"success": True, "redirect_url": fallback_url})
    return redirect(fallback_url)


# ─────────────────────────────────────────────────────────────────────────────
# LIVE PRICE PREVIEW  – JSON endpoint for AJAX field-change updates
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@dashboard_prefix_required
@require_GET
def preview_api(request, prefix):
    """
    GET ?feature_code=&bundle_slug=&currency=&billing_cycle=&quantity=&coupon_code=
    Returns a JSON price preview so the checkout card can update totals live.
    """
    feature_code  = request.GET.get("feature_code", "")
    bundle_slug   = request.GET.get("bundle_slug", "")
    currency      = request.GET.get("currency", "NGN")
    billing_cycle = request.GET.get("billing_cycle", "monthly")
    coupon_code   = request.GET.get("coupon_code", "")
    try:
        quantity = int(request.GET.get("quantity", 1) or 1)
    except (ValueError, TypeError):
        quantity = 1

    if not feature_code and not bundle_slug:
        return JsonResponse({"success": False, "error": "feature_code or bundle_slug required."}, status=400)

    result = preview_purchase(
        feature_code=feature_code,
        bundle_slug=bundle_slug,
        currency=currency,
        billing_cycle=billing_cycle,
        quantity=quantity,
        coupon_code=coupon_code,
    )

    gateways = [
        {"provider": g["provider"], "name": g["name"]}
        for g in (result.gateways or [])
    ]

    # unit_price is not a field on PurchasePreviewResult – compute it safely
    try:
        unit_price = str((result.subtotal / quantity).quantize(__import__("decimal").Decimal("0.01")))
    except Exception:
        unit_price = str(result.subtotal)

    return JsonResponse({
        "success":        result.success,
        "currency":       result.currency,
        "unit_price":     unit_price,
        "subtotal":       str(result.subtotal),
        "discount":       str(result.discount_amount),
        "total_amount":   str(result.total_amount),
        "billing_cycle":  billing_cycle,
        "quantity":       quantity,
        "gateways":       gateways,
        "errors":         result.errors,
        "message":        result.message,
    })

