from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import connection
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone
from django_tenants.utils import schema_context

from system.feature_marketplace.models import (
    Coupon,
    DiscountCampaign,
    DiscountType,
    FeatureEntitlementIndex,
    FeatureBundle,
    FeatureDefinition,
    FeaturePrice,
    FeaturePurchaseIndex,
    TenantFeatureOverride,
)
from system.system_pay.services import get_enabled_gateways


LEGACY_FEATURE_MAP = {
    "reviews": "enable_reviews",
    "wishlist": "enable_wishlist",
    "compare": "enable_compare",
    "gift_cards": "enable_gift_cards",
    "subscriptions": "enable_subscriptions",
    "live_chat": "enable_live_chat",
    "discount_codes": "enable_discount_codes",
    "api_access": "enable_api_access",
    "webhooks": "enable_webhooks",
    "social_login": "enable_social_login",
}


@dataclass
class MarketplaceServiceResult:
    success: bool = False
    message: str = ""
    errors: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)


@dataclass
class MarketplacePaymentResolutionResult:
    success: bool = False
    message: str = ""
    errors: list[str] = field(default_factory=list)
    purchase_reference: str = ""
    schema_name: str = ""
    redirect_url: str = ""
    status: str = ""


def get_active_feature_catalog(currency: str = "NGN", *, purchasable_only: bool = False):
    now = timezone.now()
    price_qs = FeaturePrice.objects.filter(is_active=True, currency=currency).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=now)
    ).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=now)
    )
    filters = {"is_active": True}
    if purchasable_only:
        filters["is_purchasable"] = True
    return FeatureDefinition.objects.filter(**filters).select_related("category").prefetch_related(
        Prefetch("prices", queryset=price_qs.order_by("billing_cycle", "amount"))
    ).order_by("display_order", "name")


def get_active_bundles(currency: str = "NGN", *, current_only: bool = False):
    qs = FeatureBundle.objects.filter(
        is_active=True,
        currency=currency,
    )
    if current_only:
        now = timezone.now()
        qs = qs.filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=now)
        ).filter(
            Q(valid_until__isnull=True) | Q(valid_until__gte=now)
        )
    return qs.prefetch_related("items__feature").order_by("display_order", "name")


def get_feature_by_code(code: str, *, purchasable_only: bool = False) -> FeatureDefinition:
    filters = {"code": code, "is_active": True}
    if purchasable_only:
        filters["is_purchasable"] = True
    return FeatureDefinition.objects.select_related("category").get(**filters)


def get_bundle_by_slug(slug: str) -> FeatureBundle:
    now = timezone.now()
    return FeatureBundle.objects.prefetch_related("items__feature").filter(
        slug=slug,
        is_active=True,
    ).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=now)
    ).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=now)
    ).get()


def resolve_feature_price(feature: FeatureDefinition, currency: str, billing_cycle: str):
    now = timezone.now()
    return feature.prices.filter(
        currency=currency,
        billing_cycle=billing_cycle,
        is_active=True,
    ).filter(Q(valid_from__isnull=True) | Q(valid_from__lte=now)).filter(
        Q(valid_until__isnull=True) | Q(valid_until__gte=now)
    ).order_by("amount").first()


def get_active_tenant_override(
    *,
    schema_name: str | None = None,
    feature: FeatureDefinition | None = None,
    feature_code: str = "",
    currency: str = "",
    billing_cycle: str = "",
):
    schema_name = schema_name or getattr(connection, "schema_name", "")
    if not schema_name or schema_name == "public":
        return None
    now = timezone.now()
    qs = TenantFeatureOverride.objects.filter(schema_name=schema_name, is_active=True).filter(
        Q(effective_from__isnull=True) | Q(effective_from__lte=now)
    ).filter(
        Q(effective_until__isnull=True) | Q(effective_until__gte=now)
    )
    if feature is not None:
        qs = qs.filter(feature=feature)
    elif feature_code:
        qs = qs.filter(feature__code=feature_code)
    if currency:
        qs = qs.filter(Q(currency="") | Q(currency=currency))
    if billing_cycle:
        qs = qs.filter(Q(billing_cycle="") | Q(billing_cycle=billing_cycle))
    return qs.order_by("-created_at").first()


def _apply_discount(base_amount: Decimal, discount_type: str, discount_value: Decimal) -> Decimal:
    if discount_type == DiscountType.PERCENTAGE:
        discounted = base_amount - (base_amount * discount_value / Decimal("100"))
    else:
        discounted = base_amount - discount_value
    return max(Decimal("0.00"), discounted.quantize(Decimal("0.01")))


def resolve_coupon(code: str):
    if not code:
        return None
    return Coupon.objects.filter(code__iexact=code.strip(), is_active=True).first()


def validate_coupon_for_item(*, coupon: Coupon | None, feature: FeatureDefinition | None = None, bundle: FeatureBundle | None = None, tenant_coupon_uses: int = 0) -> MarketplaceServiceResult:
    if coupon is None:
        return MarketplaceServiceResult(success=True)
    if not coupon.is_valid:
        return MarketplaceServiceResult(success=False, errors=["Coupon is not active or has expired."], message="Invalid coupon.")
    if coupon.max_uses_per_tenant and tenant_coupon_uses >= coupon.max_uses_per_tenant:
        return MarketplaceServiceResult(success=False, errors=["Coupon usage limit reached for this store."], message="Coupon already used.")
    if feature and coupon.applicable_features.exists() and not coupon.applicable_features.filter(pk=feature.pk).exists():
        return MarketplaceServiceResult(success=False, errors=["Coupon does not apply to this feature."], message="Coupon not applicable.")
    if bundle and coupon.applicable_bundles.exists() and not coupon.applicable_bundles.filter(pk=bundle.pk).exists():
        return MarketplaceServiceResult(success=False, errors=["Coupon does not apply to this bundle."], message="Coupon not applicable.")
    return MarketplaceServiceResult(success=True)


def get_best_campaign(*, feature: FeatureDefinition | None = None, bundle: FeatureBundle | None = None):
    now = timezone.now()
    qs = DiscountCampaign.objects.filter(is_active=True).filter(
        Q(valid_from__isnull=True) | Q(valid_from__lte=now),
        Q(valid_until__isnull=True) | Q(valid_until__gte=now),
    )
    if feature:
        qs = qs.filter(Q(applicable_features__isnull=True) | Q(applicable_features=feature)).distinct()
    if bundle:
        qs = qs.filter(Q(applicable_bundles__isnull=True) | Q(applicable_bundles=bundle)).distinct()
    return qs.order_by("-discount_value").first()


def calculate_discounted_total(*, amount: Decimal, coupon: Coupon | None = None, campaign: DiscountCampaign | None = None) -> dict:
    original = amount.quantize(Decimal("0.01"))
    discounted = original
    description = ""
    if coupon:
        discounted = _apply_discount(original, coupon.discount_type, coupon.discount_value)
        description = f"Coupon {coupon.code}"
    elif campaign and campaign.is_valid:
        discounted = _apply_discount(original, campaign.discount_type, campaign.discount_value)
        description = campaign.name
    return {
        "original_amount": original,
        "discount_amount": (original - discounted).quantize(Decimal("0.01")),
        "final_amount": discounted,
        "discount_description": description,
    }


def get_marketplace_gateways(currency: str = "NGN"):
    gateways = []
    for gateway in get_enabled_gateways().order_by("display_order", "name"):
        supported_currencies = gateway.supported_currencies or []
        if supported_currencies and currency not in supported_currencies:
            continue
        credential = gateway.platform_credentials.filter(is_active=True).order_by("-priority", "-created_at").first()
        if credential is None or not credential.is_healthy:
            continue
        gateways.append(
            {
                "id": str(gateway.id),
                "provider": gateway.provider,
                "name": gateway.name,
                "badge_label": gateway.badge_label,
                "supported_currencies": supported_currencies,
                "supports_recurring": gateway.supports_recurring,
                "public_key": credential.public_key,
                "environment": credential.environment,
            }
        )
    return gateways


def sync_feature_entitlement_index(shop) -> int:
    count = 0
    with schema_context(shop.schema_name):
        from dashboard.feature_marketplace.models import TenantEntitlement

        active_ids = set()
        for entitlement in TenantEntitlement.objects.all().iterator():
            active_ids.add(entitlement.id)
            FeatureEntitlementIndex.objects.update_or_create(
                entitlement_id=entitlement.id,
                defaults={
                    "shop": shop,
                    "schema_name": shop.schema_name,
                    "feature_id": entitlement.feature_id,
                    "feature_code": entitlement.feature_code,
                    "feature_name": entitlement.feature_name,
                    "feature_type": entitlement.feature_type,
                    "status": entitlement.status,
                    "source": entitlement.source,
                    "purchase_reference": entitlement.purchase_reference,
                    "quantity_granted": entitlement.quantity_granted,
                    "quantity_used": entitlement.quantity_used,
                    "boolean_value": entitlement.boolean_value,
                    "limit_value": entitlement.limit_value,
                    "billing_cycle": entitlement.billing_cycle,
                    "currency": entitlement.currency,
                    "activated_at": entitlement.activated_at,
                    "expires_at": entitlement.expires_at,
                    "usage_summary": _usage_summary_for_entitlement(entitlement),
                    "last_synced_at": timezone.now(),
                },
            )
            count += 1
        FeatureEntitlementIndex.objects.filter(schema_name=shop.schema_name).exclude(entitlement_id__in=active_ids).delete()
    return count


def _usage_summary_for_entitlement(entitlement) -> str:
    if entitlement.feature_type == "usage":
        return f"{entitlement.quantity_remaining} remaining of {entitlement.quantity_granted}"
    if entitlement.feature_type == "limit":
        return f"Limit {entitlement.limit_value}"
    return "Enabled" if entitlement.boolean_value else "Disabled"


@transaction.atomic
def register_purchase_index(*, purchase_id, purchase_reference: str, schema_name: str, gateway_provider: str = "", gateway_reference: str = "", metadata: dict | None = None):
    return FeaturePurchaseIndex.objects.update_or_create(
        purchase_id=purchase_id,
        defaults={
            "purchase_reference": purchase_reference,
            "schema_name": schema_name,
            "gateway_provider": gateway_provider,
            "gateway_reference": gateway_reference,
            "metadata": metadata or {},
        },
    )[0]


def resolve_purchase_index(*, purchase_reference: str = "", gateway_reference: str = ""):
    qs = FeaturePurchaseIndex.objects.all()
    if purchase_reference:
        qs = qs.filter(purchase_reference=purchase_reference)
    elif gateway_reference:
        qs = qs.filter(gateway_reference=gateway_reference)
    else:
        return None
    return qs.first()


@transaction.atomic
def process_marketplace_payment_event(
    *,
    payment_status: str,
    purchase_reference: str = "",
    gateway_reference: str = "",
    gateway_transaction_id: str = "",
    metadata: dict | None = None,
) -> MarketplacePaymentResolutionResult:
    index = resolve_purchase_index(
        purchase_reference=purchase_reference,
        gateway_reference=gateway_reference,
    )
    if index is None:
        return MarketplacePaymentResolutionResult(
            success=False,
            message="Marketplace purchase could not be resolved.",
            errors=["Purchase index not found."],
            purchase_reference=purchase_reference,
        )

    normalized_status = (payment_status or "").strip().lower()
    if normalized_status in {"success", "successful", "completed", "paid"}:
        target_status = FeaturePurchaseIndex.PurchaseStatus.COMPLETED
    elif normalized_status in {"processing", "pending"}:
        target_status = FeaturePurchaseIndex.PurchaseStatus.PROCESSING
    elif normalized_status in {"cancel", "cancelled", "canceled", "abandoned"}:
        target_status = FeaturePurchaseIndex.PurchaseStatus.CANCELLED
    elif normalized_status in {"failed", "failure", "error"}:
        target_status = FeaturePurchaseIndex.PurchaseStatus.FAILED
    else:
        return MarketplacePaymentResolutionResult(
            success=False,
            message="Unsupported marketplace payment status.",
            errors=[f"Unsupported status: {payment_status}"],
            purchase_reference=index.purchase_reference,
            schema_name=index.schema_name,
        )

    with schema_context(index.schema_name):
        from dashboard.feature_marketplace.models import FeaturePurchase
        from dashboard.feature_marketplace.services.checkout import (
            activate_purchase,
            cancel_purchase,
            fail_purchase,
        )

        purchase = FeaturePurchase.objects.filter(
            purchase_reference=index.purchase_reference
        ).first()
        if purchase is None:
            return MarketplacePaymentResolutionResult(
                success=False,
                message="Marketplace purchase record is missing.",
                errors=["Tenant purchase not found."],
                purchase_reference=index.purchase_reference,
                schema_name=index.schema_name,
            )

        merged_metadata = {**(index.metadata or {}), **(metadata or {})}
        purchase_already_completed = (
            purchase.status == FeaturePurchase.Status.COMPLETED
            and target_status != FeaturePurchaseIndex.PurchaseStatus.COMPLETED
        )
        if purchase_already_completed:
            target_status = FeaturePurchaseIndex.PurchaseStatus.COMPLETED
        if target_status == FeaturePurchaseIndex.PurchaseStatus.COMPLETED:
            activate_purchase(
                purchase,
                gateway_reference=gateway_reference or purchase.gateway_reference or index.gateway_reference,
                gateway_transaction_id=gateway_transaction_id or purchase.gateway_transaction_id or index.purchase_reference,
                metadata=merged_metadata,
            )
            redirect_url = purchase.success_redirect_url
        elif target_status == FeaturePurchaseIndex.PurchaseStatus.CANCELLED:
            cancel_purchase(purchase)
            redirect_url = purchase.cancel_redirect_url
        elif target_status == FeaturePurchaseIndex.PurchaseStatus.FAILED:
            fail_purchase(
                purchase,
                reason=merged_metadata.get("reason", ""),
                gateway_reference=gateway_reference or purchase.gateway_reference or index.gateway_reference,
                gateway_transaction_id=gateway_transaction_id or purchase.gateway_transaction_id or index.purchase_reference,
                metadata=merged_metadata,
            )
            redirect_url = purchase.cancel_redirect_url
        else:
            purchase.status = FeaturePurchase.Status.PROCESSING
            purchase.gateway_reference = gateway_reference or purchase.gateway_reference
            purchase.gateway_transaction_id = gateway_transaction_id or purchase.gateway_transaction_id
            purchase.payment_metadata = {**(purchase.payment_metadata or {}), **merged_metadata}
            purchase.save(
                update_fields=[
                    "status",
                    "gateway_reference",
                    "gateway_transaction_id",
                    "payment_metadata",
                    "updated_at",
                ]
            )
            redirect_url = ""

    index.status = target_status
    if gateway_reference:
        index.gateway_reference = gateway_reference
    index.metadata = {**(index.metadata or {}), **(metadata or {})}
    index.save(update_fields=["status", "gateway_reference", "metadata", "updated_at"])
    return MarketplacePaymentResolutionResult(
        success=True,
        message="Marketplace payment processed successfully.",
        purchase_reference=index.purchase_reference,
        schema_name=index.schema_name,
        redirect_url=redirect_url,
        status=target_status,
    )
