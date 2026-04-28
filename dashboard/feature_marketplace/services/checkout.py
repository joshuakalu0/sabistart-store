from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from datetime import timedelta

from django.db import connection, transaction
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone

from dashboard.feature_marketplace.models import (
    CouponRedemption,
    FeaturePurchase,
    FeaturePurchaseItem,
    TenantEntitlement,
)
from dashboard.feature_marketplace.integration_registry import RESOURCE_COUNTERS
from dashboard.feature_marketplace.services.engine import FeatureEntitlementEngine
from dashboard.store_settings.models import StoreSettings
from system.feature_marketplace.models import BillingCycle, Coupon, DiscountCampaign, FeatureBundle, FeatureDefinition, FeaturePrice, FeaturePurchaseIndex, FeatureType
from system.feature_marketplace.services import (
    LEGACY_FEATURE_MAP,
    calculate_discounted_total,
    get_active_tenant_override,
    get_best_campaign,
    get_bundle_by_slug,
    get_feature_by_code,
    get_marketplace_gateways,
    register_purchase_index,
    resolve_coupon,
    resolve_feature_price,
    validate_coupon_for_item,
)


@dataclass
class PurchasePreviewResult:
    success: bool = False
    message: str = ""
    errors: list[str] = field(default_factory=list)
    feature: FeatureDefinition | None = None
    bundle: FeatureBundle | None = None
    price: FeaturePrice | None = None
    quantity: int = 1
    subtotal: Decimal = Decimal("0.00")
    discount_amount: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")
    currency: str = "NGN"
    coupon: Coupon | None = None
    campaign: DiscountCampaign | None = None
    gateways: list[dict] = field(default_factory=list)


def build_purchase_reference() -> str:
    return f"FM-{uuid.uuid4().hex[:12].upper()}"


def _calculate_expiry(billing_cycle: str):
    now = timezone.now()
    if billing_cycle == BillingCycle.MONTHLY:
        return now + timedelta(days=30)
    if billing_cycle == BillingCycle.ANNUAL:
        return now + timedelta(days=365)
    return None


def preview_purchase(*, feature_code: str = "", bundle_slug: str = "", currency: str = "NGN", billing_cycle: str = BillingCycle.MONTHLY, quantity: int = 1, coupon_code: str = "") -> PurchasePreviewResult:
    if not feature_code and not bundle_slug:
        return PurchasePreviewResult(success=False, errors=["Select a feature or bundle to continue."])

    coupon = resolve_coupon(coupon_code)
    tenant_coupon_uses = CouponRedemption.objects.filter(coupon_id=coupon.id).count() if coupon else 0
    if feature_code:
        try:
            feature = get_feature_by_code(feature_code, purchasable_only=True)
        except FeatureDefinition.DoesNotExist:
            return PurchasePreviewResult(success=False, errors=["This feature is not available for purchase."])
        price = resolve_feature_price(feature, currency, billing_cycle)
        if price is None:
            return PurchasePreviewResult(success=False, errors=["No active pricing found for this feature in the selected currency and cycle."])
        tenant_override = get_active_tenant_override(
            schema_name=getattr(connection, "schema_name", None),
            feature=feature,
            currency=currency,
            billing_cycle=billing_cycle,
        )
        coupon_result = validate_coupon_for_item(coupon=coupon, feature=feature, tenant_coupon_uses=tenant_coupon_uses)
        if not coupon_result.success:
            return PurchasePreviewResult(success=False, errors=coupon_result.errors, message=coupon_result.message)
        subtotal = (price.amount * quantity).quantize(Decimal("0.01"))
        if tenant_override:
            if tenant_override.mode == tenant_override.OverrideMode.FREE:
                subtotal = Decimal("0.00")
            elif tenant_override.mode == tenant_override.OverrideMode.CUSTOM_PRICE and tenant_override.custom_price is not None:
                subtotal = (tenant_override.custom_price * quantity).quantize(Decimal("0.01"))
        campaign = None if coupon else get_best_campaign(feature=feature)
        discounted = calculate_discounted_total(amount=subtotal, coupon=coupon, campaign=campaign)
        if tenant_override:
            if tenant_override.mode == tenant_override.OverrideMode.CUSTOM_DISCOUNT_PERCENT and tenant_override.custom_discount_percent is not None:
                discounted = calculate_discounted_total(
                    amount=subtotal,
                    campaign=DiscountCampaign(
                        discount_type="percentage",
                        discount_value=tenant_override.custom_discount_percent,
                    ),
                )
            elif tenant_override.mode == tenant_override.OverrideMode.CUSTOM_DISCOUNT_AMOUNT and tenant_override.custom_discount_amount is not None:
                discounted = calculate_discounted_total(
                    amount=subtotal,
                    campaign=DiscountCampaign(
                        discount_type="fixed",
                        discount_value=tenant_override.custom_discount_amount,
                    ),
                )
        return PurchasePreviewResult(
            success=True,
            feature=feature,
            price=price,
            quantity=quantity,
            subtotal=subtotal,
            discount_amount=discounted["discount_amount"],
            total_amount=discounted["final_amount"],
            currency=currency,
            coupon=coupon,
            campaign=campaign,
            gateways=get_marketplace_gateways(currency),
        )

    try:
        bundle = get_bundle_by_slug(bundle_slug)
    except FeatureDefinition.DoesNotExist:
        return PurchasePreviewResult(success=False, errors=["This bundle is not available for purchase."])
    except Exception:
        return PurchasePreviewResult(success=False, errors=["This bundle is not available for purchase."])
    coupon_result = validate_coupon_for_item(coupon=coupon, bundle=bundle, tenant_coupon_uses=tenant_coupon_uses)
    if not coupon_result.success:
        return PurchasePreviewResult(success=False, errors=coupon_result.errors, message=coupon_result.message)
    subtotal = (bundle.price * quantity).quantize(Decimal("0.01"))
    campaign = None if coupon else get_best_campaign(bundle=bundle)
    discounted = calculate_discounted_total(amount=subtotal, coupon=coupon, campaign=campaign)
    return PurchasePreviewResult(
        success=True,
        bundle=bundle,
        quantity=quantity,
        subtotal=subtotal,
        discount_amount=discounted["discount_amount"],
        total_amount=discounted["final_amount"],
        currency=currency,
        coupon=coupon,
        campaign=campaign,
        gateways=get_marketplace_gateways(currency),
    )


@transaction.atomic
def create_purchase(*, schema_name: str, feature_code: str = "", bundle_slug: str = "", currency: str = "NGN", billing_cycle: str = BillingCycle.MONTHLY, quantity: int = 1, coupon_code: str = "", gateway_provider: str = "", initiated_by=None, success_redirect_url: str = "", cancel_redirect_url: str = ""):
    preview = preview_purchase(
        feature_code=feature_code,
        bundle_slug=bundle_slug,
        currency=currency,
        billing_cycle=billing_cycle,
        quantity=quantity,
        coupon_code=coupon_code,
    )
    if not preview.success:
        raise ValueError("; ".join(preview.errors) or "Unable to prepare marketplace purchase.")

    chosen_gateway = next((gateway for gateway in preview.gateways if gateway["provider"] == gateway_provider), None)
    if chosen_gateway is None:
        chosen_gateway = preview.gateways[0] if preview.gateways else None
    if chosen_gateway is None:
        raise ValueError("No platform payment gateway is available for marketplace billing.")

    purchase = FeaturePurchase.objects.create(
        purchase_reference=build_purchase_reference(),
        purchase_type=FeaturePurchase.PurchaseType.FEATURE if preview.feature else FeaturePurchase.PurchaseType.BUNDLE,
        feature_id=preview.feature.id if preview.feature else None,
        feature_code=preview.feature.code if preview.feature else "",
        feature_name=preview.feature.name if preview.feature else "",
        bundle_id=preview.bundle.id if preview.bundle else None,
        bundle_slug=preview.bundle.slug if preview.bundle else "",
        bundle_name=preview.bundle.name if preview.bundle else "",
        price_id=preview.price.id if preview.price else None,
        quantity=quantity,
        billing_cycle=preview.price.billing_cycle if preview.price else preview.bundle.billing_cycle,
        subtotal=preview.subtotal,
        discount_amount=preview.discount_amount,
        total_amount=preview.total_amount,
        currency=preview.currency,
        coupon_code=preview.coupon.code if preview.coupon else "",
        campaign_id=preview.campaign.id if preview.campaign else None,
        status=FeaturePurchase.Status.PENDING,
        gateway_definition_id=uuid.UUID(chosen_gateway["id"]),
        gateway_provider=chosen_gateway["provider"],
        gateway_name=chosen_gateway["name"],
        initiated_by_email=getattr(initiated_by, "email", "") or "",
        initiated_by_name=getattr(initiated_by, "get_full_name", lambda: "")() if initiated_by else "",
        success_redirect_url=success_redirect_url,
        cancel_redirect_url=cancel_redirect_url,
    )
    register_purchase_index(
        purchase_id=purchase.id,
        purchase_reference=purchase.purchase_reference,
        schema_name=schema_name,
        gateway_provider=purchase.gateway_provider,
    )
    purchase.payment_metadata = {
        "checkout_url": reverse("system_pay:marketplace_checkout", kwargs={"purchase_reference": purchase.purchase_reference}),
        "gateway_environment": chosen_gateway["environment"],
    }
    purchase.save(update_fields=["payment_metadata", "updated_at"])
    return purchase


def initialize_purchase_payment(
    *,
    purchase: FeaturePurchase,
    initiated_by=None,
    customer_ip: str = "",
    callback_url: str = "",
):
    from dashboard.payments_tenant.models import TenantPaymentProfile
    from dashboard.payments_tenant.services.intent_transactions import create_payment_intent
    from dashboard.payments_tenant.view_utils import bootstrap_payment_profile

    profile = TenantPaymentProfile.objects.order_by("created_at").first()
    if profile is None:
        profile = TenantPaymentProfile.objects.create(
            account_status=TenantPaymentProfile.AccountStatus.ACTIVE,
            business_name=getattr(connection, "schema_name", "Store").replace("_", " ").title(),
            support_email=purchase.initiated_by_email,
            payment_notification_email=purchase.initiated_by_email,
            default_currency=purchase.currency,
        )

    bootstrap_payment_profile(profile, actor=initiated_by)

    intent_result = create_payment_intent(
        payment_profile=profile,
        order_id=purchase.id,
        order_number=purchase.purchase_reference,
        amount=purchase.total_amount,
        currency=purchase.currency,
        customer_email=purchase.initiated_by_email,
        customer_name=purchase.initiated_by_name,
        customer_ip=customer_ip,
        gateway_provider=purchase.gateway_provider or None,
        payment_method_type="marketplace_feature",
        metadata={
            "source": "feature_marketplace",
            "purchase_reference": purchase.purchase_reference,
            "purchase_type": purchase.purchase_type,
            "feature_code": purchase.feature_code,
            "bundle_slug": purchase.bundle_slug,
        },
        success_url=purchase.success_redirect_url,
        failure_url=purchase.cancel_redirect_url,
        cancel_url=purchase.cancel_redirect_url,
        callback_url=callback_url,
    )
    if not intent_result.success:
        raise ValueError("; ".join(intent_result.errors) or "Unable to initialize marketplace payment.")

    purchase.gateway_reference = intent_result.gateway_reference or purchase.gateway_reference
    purchase.payment_metadata = {
        **(purchase.payment_metadata or {}),
        "payment_intent_id": intent_result.intent_id,
        "authorization_url": intent_result.authorization_url,
        "provider_checkout_url": intent_result.authorization_url,
        "access_code": intent_result.access_code,
        "client_secret": intent_result.client_secret,
        "public_key": intent_result.public_key,
        "is_test": intent_result.is_test,
        "checkout_url": (
            intent_result.authorization_url
            or reverse("system_pay:marketplace_checkout", kwargs={"purchase_reference": purchase.purchase_reference})
        ),
    }
    purchase.save(update_fields=["gateway_reference", "payment_metadata", "updated_at"])
    FeaturePurchaseIndex.objects.filter(purchase_id=purchase.id).update(
        gateway_reference=intent_result.gateway_reference or "",
        status=FeaturePurchaseIndex.PurchaseStatus.PROCESSING,
        metadata={
            **(purchase.payment_metadata or {}),
            "payment_intent_id": intent_result.intent_id,
        },
    )
    return intent_result


def _resolve_entitlement_values(
    *,
    feature: FeatureDefinition,
    billing_cycle: str,
    quantity: int = 1,
    price: FeaturePrice | None = None,
    quantity_override: int | None = None,
    boolean_override: bool | None = None,
):
    quantity_granted = 0
    limit_value = 0
    boolean_value = True
    if feature.feature_type == FeatureType.USAGE:
        quantity_granted = quantity_override if quantity_override is not None else ((price.credits_included if price else feature.default_usage_value) * quantity)
    elif feature.feature_type == FeatureType.LIMIT:
        limit_value = quantity_override if quantity_override is not None else ((price.limit_increment if price else feature.default_limit_value) * quantity)
        quantity_granted = limit_value
    else:
        boolean_value = boolean_override if boolean_override is not None else True
    return {
        "quantity_granted": quantity_granted,
        "limit_value": limit_value,
        "boolean_value": boolean_value,
        "expires_at": _calculate_expiry(billing_cycle),
        "auto_renew": billing_cycle in (BillingCycle.MONTHLY, BillingCycle.ANNUAL),
    }


def _create_entitlement(
    *,
    purchase: FeaturePurchase,
    feature: FeatureDefinition,
    price: FeaturePrice | None = None,
    quantity_override: int | None = None,
    boolean_override: bool | None = None,
    unit_amount: Decimal | None = None,
    line_total: Decimal | None = None,
):
    values = _resolve_entitlement_values(
        feature=feature,
        billing_cycle=purchase.billing_cycle,
        quantity=purchase.quantity,
        price=price,
        quantity_override=quantity_override,
        boolean_override=boolean_override,
    )
    entitlement = TenantEntitlement.objects.create(
        feature_id=feature.id,
        feature_code=feature.code,
        feature_name=feature.name,
        feature_type=feature.feature_type,
        purchase_id=purchase.id,
        purchase_reference=purchase.purchase_reference,
        source=TenantEntitlement.Source.PURCHASE,
        quantity_granted=values["quantity_granted"],
        boolean_value=values["boolean_value"],
        limit_value=values["limit_value"],
        status=TenantEntitlement.Status.ACTIVE,
        activated_at=timezone.now(),
        expires_at=values["expires_at"],
        auto_renew=values["auto_renew"],
        renewal_price_id=price.id if price else None,
        billing_cycle=purchase.billing_cycle,
        currency=purchase.currency,
        price_paid=line_total if line_total is not None else purchase.total_amount,
    )
    FeaturePurchaseItem.objects.create(
        purchase=purchase,
        feature_id=feature.id,
        feature_code=feature.code,
        feature_name=feature.name,
        feature_type=feature.feature_type,
        quantity_granted=values["quantity_granted"],
        limit_value=values["limit_value"],
        boolean_value=values["boolean_value"],
        unit_amount=unit_amount if unit_amount is not None else purchase.total_amount,
        line_total=line_total if line_total is not None else purchase.total_amount,
    )
    return entitlement


@transaction.atomic
def activate_purchase(purchase: FeaturePurchase, gateway_reference: str = "", gateway_transaction_id: str = "", metadata: dict | None = None):
    if purchase.status == FeaturePurchase.Status.COMPLETED:
        return purchase
    purchase.status = FeaturePurchase.Status.COMPLETED
    purchase.gateway_reference = gateway_reference or purchase.gateway_reference or purchase.purchase_reference
    purchase.gateway_transaction_id = gateway_transaction_id or purchase.gateway_transaction_id or purchase.purchase_reference
    purchase.paid_at = timezone.now()
    purchase.completed_at = timezone.now()
    purchase.payment_metadata = {**(purchase.payment_metadata or {}), **(metadata or {})}
    purchase.save(update_fields=["status", "gateway_reference", "gateway_transaction_id", "paid_at", "completed_at", "payment_metadata", "updated_at"])

    affected_limits = set()
    if purchase.purchase_type == FeaturePurchase.PurchaseType.FEATURE:
        feature = get_feature_by_code(purchase.feature_code)
        price = FeaturePrice.objects.filter(pk=purchase.price_id).first() if purchase.price_id else None
        entitlement = _create_entitlement(purchase=purchase, feature=feature, price=price)
        if entitlement.feature_type == FeatureType.LIMIT:
            affected_limits.add(entitlement.feature_code)
    else:
        bundle = get_bundle_by_slug(purchase.bundle_slug)
        bundle_item_count = bundle.items.count() or 1
        per_item_total = (purchase.total_amount / Decimal(bundle_item_count)).quantize(Decimal("0.01"))
        for item in bundle.items.select_related("feature").order_by("sort_order", "feature__display_order"):
            entitlement = _create_entitlement(
                purchase=purchase,
                feature=item.feature,
                quantity_override=item.quantity_override,
                boolean_override=item.boolean_override,
                unit_amount=Decimal("0.00"),
                line_total=per_item_total,
            )
            if entitlement.feature_type == FeatureType.LIMIT:
                affected_limits.add(entitlement.feature_code)

    if purchase.coupon_code:
        coupon = resolve_coupon(purchase.coupon_code)
        if coupon:
            Coupon.objects.filter(pk=coupon.pk).update(current_uses=F("current_uses") + 1)
            CouponRedemption.objects.create(
                coupon_code=coupon.code,
                coupon_id=coupon.id,
                purchase=purchase,
                discount_applied=purchase.discount_amount,
            )

    engine = FeatureEntitlementEngine()
    for feature_code in affected_limits:
        engine.rebuild_quota(feature_code)
    engine.invalidate_cache()
    return purchase


@transaction.atomic
def cancel_purchase(purchase: FeaturePurchase):
    purchase.status = FeaturePurchase.Status.CANCELLED
    purchase.cancelled_at = timezone.now()
    purchase.save(update_fields=["status", "cancelled_at", "updated_at"])
    return purchase


@transaction.atomic
def fail_purchase(
    purchase: FeaturePurchase,
    *,
    reason: str = "",
    gateway_reference: str = "",
    gateway_transaction_id: str = "",
    metadata: dict | None = None,
):
    purchase.status = FeaturePurchase.Status.FAILED
    purchase.gateway_reference = gateway_reference or purchase.gateway_reference
    purchase.gateway_transaction_id = gateway_transaction_id or purchase.gateway_transaction_id
    purchase.payment_metadata = {
        **(purchase.payment_metadata or {}),
        **(metadata or {}),
        **({"failure_reason": reason} if reason else {}),
    }
    purchase.save(
        update_fields=[
            "status",
            "gateway_reference",
            "gateway_transaction_id",
            "payment_metadata",
            "updated_at",
        ]
    )
    return purchase


@transaction.atomic
def grant_manual_entitlement(
    *,
    feature: FeatureDefinition,
    quantity: int | None = None,
    note: str = "",
    billing_cycle: str = BillingCycle.PERPETUAL,
    currency: str = "NGN",
):
    values = _resolve_entitlement_values(
        feature=feature,
        billing_cycle=billing_cycle or BillingCycle.PERPETUAL,
        quantity=1,
        quantity_override=quantity if feature.feature_type in (FeatureType.LIMIT, FeatureType.USAGE) else None,
        boolean_override=True,
    )
    entitlement = TenantEntitlement.objects.create(
        feature_id=feature.id,
        feature_code=feature.code,
        feature_name=feature.name,
        feature_type=feature.feature_type,
        source=TenantEntitlement.Source.MANUAL,
        source_note=note,
        quantity_granted=values["quantity_granted"],
        boolean_value=values["boolean_value"],
        limit_value=values["limit_value"],
        status=TenantEntitlement.Status.ACTIVE,
        activated_at=timezone.now(),
        expires_at=values["expires_at"],
        auto_renew=False,
        billing_cycle=billing_cycle or BillingCycle.PERPETUAL,
        currency=currency,
    )
    engine = FeatureEntitlementEngine()
    if feature.feature_type == FeatureType.LIMIT:
        engine.rebuild_quota(feature.code)
    engine.invalidate_cache(feature.code)
    return entitlement


def list_recent_purchases(limit: int = 20):
    return FeaturePurchase.objects.order_by("-created_at")[:limit]


def list_active_entitlements():
    now = timezone.now()
    return TenantEntitlement.objects.filter(status=TenantEntitlement.Status.ACTIVE).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    ).order_by("feature_code", "-activated_at")


def list_expiring_entitlements(within_days: int = 14):
    start = timezone.now()
    end = start + timedelta(days=within_days)
    return TenantEntitlement.objects.filter(
        status=TenantEntitlement.Status.ACTIVE,
        expires_at__gte=start,
        expires_at__lte=end,
    ).order_by("expires_at")


def expire_due_entitlements():
    now = timezone.now()
    expired = TenantEntitlement.objects.filter(
        status=TenantEntitlement.Status.ACTIVE,
        expires_at__lt=now,
    )
    count = 0
    engine = FeatureEntitlementEngine()
    for entitlement in expired:
        entitlement.status = TenantEntitlement.Status.EXPIRED
        entitlement.save(update_fields=["status", "updated_at"])
        if entitlement.feature_type == "limit":
            engine.rebuild_quota(entitlement.feature_code)
        count += 1
    engine.invalidate_cache()
    return count


def grandfather_legacy_entitlements():
    settings_obj = StoreSettings.objects.get_settings()
    created = 0
    for feature_code, setting_key in LEGACY_FEATURE_MAP.items():
        if not getattr(settings_obj, setting_key, False):
            continue
        feature = FeatureDefinition.objects.filter(code=feature_code, is_active=True).first()
        if feature is None:
            continue
        exists = TenantEntitlement.objects.filter(
            feature_code=feature_code,
            status__in=[TenantEntitlement.Status.ACTIVE, TenantEntitlement.Status.PENDING],
        ).exists()
        if exists:
            continue
        TenantEntitlement.objects.create(
            feature_id=feature.id,
            feature_code=feature.code,
            feature_name=feature.name,
            feature_type=feature.feature_type,
            source=TenantEntitlement.Source.GRANDFATHER,
            source_note="Migrated from legacy store feature toggle.",
            boolean_value=True,
            status=TenantEntitlement.Status.ACTIVE,
            activated_at=timezone.now(),
            billing_cycle=BillingCycle.PERPETUAL,
            compatibility_setting_key=setting_key,
        )
        created += 1

    engine = FeatureEntitlementEngine()
    for feature_code, counter in RESOURCE_COUNTERS.items():
        current_usage = counter()
        if current_usage <= 0:
            continue
        feature = FeatureDefinition.objects.filter(code=feature_code, is_active=True).first()
        if feature is None:
            continue
        target_limit = max(feature.default_limit_value, current_usage)
        additional_limit = max(0, target_limit - feature.default_limit_value)
        if additional_limit <= 0:
            continue
        active_limit = engine.get_feature_limit(feature_code)
        if active_limit >= target_limit:
            continue
        TenantEntitlement.objects.create(
            feature_id=feature.id,
            feature_code=feature.code,
            feature_name=feature.name,
            feature_type=feature.feature_type,
            source=TenantEntitlement.Source.GRANDFATHER,
            source_note="Migrated from current live tenant usage.",
            quantity_granted=additional_limit,
            limit_value=additional_limit,
            status=TenantEntitlement.Status.ACTIVE,
            activated_at=timezone.now(),
            billing_cycle=BillingCycle.PERPETUAL,
        )
        created += 1
        engine.rebuild_quota(feature_code)
    engine.invalidate_cache()
    return created
