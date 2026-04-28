from __future__ import annotations

from django.urls import reverse

from dashboard.sidebar_utiles import main_sidebar
from dashboard.payments_tenant.models import (
    PaymentGatewayDefinition,
    PaymentMode,
    PlatformGatewayCredential,
    SupportedCurrency,
    TenantGatewayMode,
    TenantPaymentProfile,
)


def get_payment_profile(request) -> TenantPaymentProfile:
    profile = TenantPaymentProfile.objects.order_by("created_at").first()
    if profile is None:
        tenant = getattr(request, "tenant", None)
        email = getattr(getattr(request, "user", None), "email", "") or ""
        profile = TenantPaymentProfile.objects.create(
            account_status=TenantPaymentProfile.AccountStatus.ACTIVE,
            business_name=getattr(tenant, "name", "") or "Store",
            support_email=email,
            payment_notification_email=email,
        )

    bootstrap_payment_profile(profile, actor=getattr(request, "user", None))
    return profile


def bootstrap_payment_profile(profile: TenantPaymentProfile, actor=None) -> TenantPaymentProfile:
    SupportedCurrency.objects.get_or_create(
        payment_profile=profile,
        currency_code=profile.default_currency,
        defaults={"is_default": True, "is_enabled": True},
    )

    enabled_gateways = PaymentGatewayDefinition.objects.filter(is_enabled=True).order_by(
        "display_order", "name"
    )
    has_default = TenantGatewayMode.objects.filter(
        payment_profile=profile,
        is_default=True,
    ).exists()

    for index, gateway in enumerate(enabled_gateways):
        platform_credential = (
            PlatformGatewayCredential.objects.filter(gateway=gateway, is_active=True)
            .order_by("-priority", "-created_at")
            .first()
        )
        accepted_currencies = gateway.supported_currencies or [profile.default_currency]
        gateway_mode, created = TenantGatewayMode.objects.get_or_create(
            payment_profile=profile,
            gateway=gateway,
            defaults={
                "mode": PaymentMode.PLATFORM,
                "status": (
                    TenantGatewayMode.ActivationStatus.ACTIVE
                    if platform_credential
                    else TenantGatewayMode.ActivationStatus.INACTIVE
                ),
                "is_default": not has_default and index == 0,
                "platform_credential": platform_credential,
                "accepted_currencies": accepted_currencies,
                "enabled_payment_methods": ["card"],
                "checkout_label": gateway.name,
                "checkout_display_order": index,
                "mode_switched_by": actor,
            },
        )
        if created:
            continue

        changed_fields = []
        if not gateway_mode.checkout_label:
            gateway_mode.checkout_label = gateway.name
            changed_fields.append("checkout_label")
        if not gateway_mode.accepted_currencies:
            gateway_mode.accepted_currencies = accepted_currencies
            changed_fields.append("accepted_currencies")
        if not gateway_mode.enabled_payment_methods:
            gateway_mode.enabled_payment_methods = ["card"]
            changed_fields.append("enabled_payment_methods")
        if gateway_mode.platform_credential_id is None and platform_credential:
            gateway_mode.platform_credential = platform_credential
            changed_fields.append("platform_credential")
        if (
            gateway_mode.status == TenantGatewayMode.ActivationStatus.INACTIVE
            and platform_credential
        ):
            gateway_mode.status = TenantGatewayMode.ActivationStatus.ACTIVE
            changed_fields.append("status")
        if changed_fields:
            gateway_mode.save(update_fields=changed_fields + ["updated_at"])

    if not has_default:
        default_mode = (
            TenantGatewayMode.objects.filter(payment_profile=profile)
            .order_by("-status", "checkout_display_order", "gateway__display_order")
            .first()
        )
        if default_mode:
            default_mode.is_default = True
            default_mode.save(update_fields=["is_default", "updated_at"])

    return profile


def build_page_context(prefix: str, page_title: str, active_menu: str, **extra):
    context = {
        "prefix": prefix,
        "page_title": page_title,
        "active_menu": active_menu,
        "sidebar": main_sidebar(prefix, active_menu),
    }
    context.update(extra)
    return context


def menu_url(prefix: str, name: str, **kwargs) -> str:
    payload = {"prefix": prefix}
    payload.update(kwargs)
    return reverse(name, kwargs=payload)
