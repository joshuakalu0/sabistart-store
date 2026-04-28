import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction as db_transaction
from django.shortcuts import get_object_or_404, redirect, render

from dashboard.decorators import dashboard_prefix_required
from dashboard.analytics.services import build_export_urls, build_payments_bundle, bundle_to_json, export_bundle, parse_analytics_window
from dashboard.feature_marketplace.services import require_feature
from dashboard.payments_tenant.forms import (
    SupportedCurrencyForm,
    TenantGatewayCredentialForm,
    TenantPaymentProfileForm,
)
from dashboard.payments_tenant.models import (
    SupportedCurrency,
    TenantBalance,
    TenantGatewayCredential,
    TenantGatewayMode,
    Transaction,
)
from dashboard.payments_tenant.services import (
    get_payments_attention_queue,
    get_payments_dashboard_kpis,
    get_payments_health_checks,
    switch_tenant_to_direct_mode,
    switch_tenant_to_platform_mode,
)
from dashboard.payments_tenant.view_utils import (
    build_page_context,
    get_payment_profile,
    menu_url,
)

logger = logging.getLogger("dashboard.payments_tenant.views.profile")


def _normalize_health_checks(prefix, raw_checks):
    action_map = {
        "active_gateway": ("dashboard:payments_tenant:gateway_mode_list", {}),
        "default_gateway": ("dashboard:payments_tenant:gateway_mode_list", {}),
        "payout_enabled": ("dashboard:payments_tenant:bank_account_list", {}),
        "kyb_status": ("dashboard:payments_tenant:profile_edit", {}),
        "bank_account": ("dashboard:payments_tenant:bank_account_list", {}),
    }
    checks = []
    for check in raw_checks:
        action = action_map.get(check["check"])
        checks.append(
            {
                "ok": check["status"] == "ok",
                "label": check["check"].replace("_", " ").title(),
                "message": check["message"],
                "action_url": menu_url(prefix, action[0], **action[1]) if action and check["status"] != "ok" else "",
            }
        )
    return checks


def _attention_items(prefix, summary):
    items = []
    if summary.get("flagged_transactions"):
        items.append(
            {
                "message": f"{summary['flagged_transactions']} transactions need manual review.",
                "url": menu_url(prefix, "dashboard:payments_tenant:transaction_list") + "?flagged=1",
            }
        )
    if summary.get("overdue_disputes"):
        items.append(
            {
                "message": f"{summary['overdue_disputes']} disputes have passed their evidence deadline.",
                "url": menu_url(prefix, "dashboard:payments_tenant:dispute_list") + "?overdue=1",
            }
        )
    if summary.get("open_disputes"):
        items.append(
            {
                "message": f"{summary['open_disputes']} customer disputes are still open.",
                "url": menu_url(prefix, "dashboard:payments_tenant:dispute_list"),
            }
        )
    if summary.get("pending_payout_reviews"):
        items.append(
            {
                "message": f"{summary['pending_payout_reviews']} payout requests are waiting.",
                "url": menu_url(prefix, "dashboard:payments_tenant:payout_request_list"),
            }
        )
    if summary.get("inactive_gateways"):
        items.append(
            {
                "message": f"{summary['inactive_gateways']} gateways are inactive.",
                "url": menu_url(prefix, "dashboard:payments_tenant:gateway_mode_list"),
            }
        )
    return items


@login_required
@dashboard_prefix_required
def tenant_home(request, prefix):
    profile = get_payment_profile(request)
    try:
        period_days = max(1, int(request.GET.get("period", 30)))
    except (TypeError, ValueError):
        period_days = 30

    kpi_source = get_payments_dashboard_kpis(profile, period_days=period_days)
    health = _normalize_health_checks(prefix, get_payments_health_checks(profile))
    attention_summary = get_payments_attention_queue(profile)
    attention = _attention_items(prefix, attention_summary)
    recent_txns = (
        Transaction.objects.filter(payment_profile=profile)
        .select_related("gateway_mode__gateway")
        .order_by("-created_at")[:10]
    )
    balances = TenantBalance.objects.filter(payment_profile=profile).order_by("currency")
    modes = profile.gateway_modes.select_related("gateway", "direct_credential", "platform_credential").order_by(
        "-is_default", "gateway__display_order", "gateway__name"
    )

    kpis = {
        "transaction_count": kpi_source["transactions"]["value"],
        "total_volume": kpi_source["gross_revenue"]["value"],
        "success_rate": kpi_source["success_rate"]["value"],
        "open_disputes": attention_summary.get("open_disputes", 0),
    }
    gw_status = [
        {
            "gateway_name": mode.gateway.name,
            "mode": mode.get_mode_display(),
            "is_default": mode.is_default,
            "is_healthy": mode.is_active and (not mode.direct_credential or mode.direct_credential.status != TenantGatewayCredential.CredentialStatus.INVALID),
        }
        for mode in modes
    ]

    context = build_page_context(
        prefix,
        "Payments Dashboard",
        "payments_overview",
        profile=profile,
        kpis=kpis,
        health=health,
        balances=balances,
        attention=attention,
        recent_txns=recent_txns,
        gw_status=gw_status,
        period_days=period_days,
    )
    return render(request, "dashboard/payments_tenant/index.html", context)


@login_required
@dashboard_prefix_required
@require_feature("advanced_analytics")
def analytics_view(request, prefix):
    profile = get_payment_profile(request)
    window = parse_analytics_window(request.GET)
    bundle = build_payments_bundle(profile, window)
    export_format = (request.GET.get("export") or "").strip().lower()
    if export_format:
        return export_bundle(bundle, export_format=export_format, filename_root="payments-analytics", request=request)
    query_params = {
        "period": bundle["filters"]["period"],
        "start": bundle["filters"]["start"],
        "end": bundle["filters"]["end"],
    }
    if bundle["filters"]["compare"]:
        query_params["compare"] = "1"

    context = build_page_context(
        prefix,
        "Payments Analytics",
        "payments_analytics",
        profile=profile,
        analytics_bundle=bundle,
        analytics_bundle_json=bundle_to_json(bundle),
        payment_export_urls=build_export_urls(request.path, query_params),
    )
    return render(request, "dashboard/payments_tenant/analytics.html", context)


@login_required
@dashboard_prefix_required
def profile_edit(request, prefix):
    profile = get_payment_profile(request)
    if request.method == "POST":
        form = TenantPaymentProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Payment settings saved successfully.")
            return redirect("dashboard:payments_tenant:profile_edit", prefix=prefix)
    else:
        form = TenantPaymentProfileForm(instance=profile)

    return render(
        request,
        "dashboard/payments_tenant/profile/form.html",
        build_page_context(
            prefix,
            "Payment Settings",
            "payments_settings",
            form_title="Payment Profile Settings",
            form=form,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def gateway_mode_list(request, prefix):
    profile = get_payment_profile(request)
    modes = profile.gateway_modes.select_related("gateway", "direct_credential", "platform_credential").order_by(
        "-is_default", "gateway__display_order", "gateway__name"
    )
    return render(
        request,
        "dashboard/payments_tenant/gateway_mode/list.html",
        build_page_context(
            prefix,
            "Payment Gateways",
            "payments_gateways",
            modes=modes,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def gateway_mode_detail(request, prefix, pk):
    profile = get_payment_profile(request)
    mode = get_object_or_404(
        TenantGatewayMode.objects.select_related("gateway", "direct_credential", "platform_credential"),
        pk=pk,
        payment_profile=profile,
    )
    credentials = TenantGatewayCredential.objects.filter(
        payment_profile=profile,
        gateway=mode.gateway,
    ).order_by("-created_at")
    return render(
        request,
        "dashboard/payments_tenant/gateway_mode/detail.html",
        build_page_context(
            prefix,
            f"Gateway - {mode.gateway.name}",
            "payments_gateways",
            mode=mode,
            credentials=credentials,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def gateway_mode_switch(request, prefix, pk):
    if request.method != "POST":
        return redirect("dashboard:payments_tenant:gateway_mode_detail", prefix=prefix, pk=pk)

    profile = get_payment_profile(request)
    mode = get_object_or_404(TenantGatewayMode, pk=pk, payment_profile=profile)
    target_mode = request.POST.get("target_mode", "").strip().lower()

    if target_mode == "direct":
        credential = mode.direct_credential or (
            TenantGatewayCredential.objects.filter(
                payment_profile=profile,
                gateway=mode.gateway,
                status=TenantGatewayCredential.CredentialStatus.ACTIVE,
            )
            .order_by("-validated_at", "-created_at")
            .first()
        )
        if credential is None:
            messages.error(request, "Add and validate your gateway credentials before switching to direct mode.")
            return redirect("dashboard:payments_tenant:credential_create", prefix=prefix, gateway_pk=mode.pk)

        result = switch_tenant_to_direct_mode(
            payment_profile=profile,
            gateway_provider=mode.gateway.provider,
            credential_id=str(credential.id),
            actor=request.user,
        )
    elif target_mode == "platform":
        result = switch_tenant_to_platform_mode(
            payment_profile=profile,
            gateway_provider=mode.gateway.provider,
            actor=request.user,
        )
    else:
        result = {"success": False, "message": "Invalid gateway mode target."}

    if result.get("success"):
        messages.success(request, result["message"])
    else:
        messages.error(request, result["message"])
    return redirect("dashboard:payments_tenant:gateway_mode_detail", prefix=prefix, pk=pk)


@login_required
@dashboard_prefix_required
def gateway_mode_set_default(request, prefix, pk):
    if request.method != "POST":
        return redirect("dashboard:payments_tenant:gateway_mode_list", prefix=prefix)

    profile = get_payment_profile(request)
    mode = get_object_or_404(TenantGatewayMode, pk=pk, payment_profile=profile)
    with db_transaction.atomic():
        TenantGatewayMode.objects.filter(payment_profile=profile, is_default=True).update(is_default=False)
        mode.is_default = True
        mode.save(update_fields=["is_default", "updated_at"])
    messages.success(request, f"{mode.gateway.name} is now the default payment gateway.")
    return redirect("dashboard:payments_tenant:gateway_mode_list", prefix=prefix)


@login_required
@dashboard_prefix_required
def credential_list(request, prefix, gateway_pk):
    profile = get_payment_profile(request)
    gateway_mode = get_object_or_404(TenantGatewayMode, pk=gateway_pk, payment_profile=profile)
    credentials = TenantGatewayCredential.objects.filter(
        payment_profile=profile,
        gateway=gateway_mode.gateway,
    ).order_by("-created_at")
    return render(
        request,
        "dashboard/payments_tenant/gateway_credential/list.html",
        build_page_context(
            prefix,
            f"API Credentials - {gateway_mode.gateway.name}",
            "payments_gateways",
            gateway_mode=gateway_mode,
            credentials=credentials,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def credential_create(request, prefix, gateway_pk):
    profile = get_payment_profile(request)
    gateway_mode = get_object_or_404(TenantGatewayMode, pk=gateway_pk, payment_profile=profile)

    if request.method == "POST":
        form = TenantGatewayCredentialForm(request.POST)
        if form.is_valid():
            credential = form.save(commit=False)
            credential.payment_profile = profile
            credential.gateway = gateway_mode.gateway
            credential.submitted_by = request.user
            credential.status = TenantGatewayCredential.CredentialStatus.PENDING
            credential.save()
            gateway_mode.direct_credential = credential
            gateway_mode.save(update_fields=["direct_credential", "updated_at"])
            messages.success(request, "Gateway credentials submitted successfully.")
            return redirect("dashboard:payments_tenant:credential_list", prefix=prefix, gateway_pk=gateway_pk)
    else:
        form = TenantGatewayCredentialForm(initial={"gateway": gateway_mode.gateway})
        form.fields["gateway"].disabled = True

    return render(
        request,
        "dashboard/payments_tenant/gateway_credential/form.html",
        build_page_context(
            prefix,
            f"Submit API Keys - {gateway_mode.gateway.name}",
            "payments_gateways",
            form_title=f"Submit API Credentials - {gateway_mode.gateway.name}",
            form=form,
            gateway_mode=gateway_mode,
            is_edit=False,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def credential_edit(request, prefix, gateway_pk, pk):
    profile = get_payment_profile(request)
    gateway_mode = get_object_or_404(TenantGatewayMode, pk=gateway_pk, payment_profile=profile)
    credential = get_object_or_404(
        TenantGatewayCredential,
        pk=pk,
        payment_profile=profile,
        gateway=gateway_mode.gateway,
    )

    if credential.status == TenantGatewayCredential.CredentialStatus.ACTIVE and gateway_mode.is_direct_mode:
        messages.warning(request, "Submit a new credential set before changing the credential currently used in direct mode.")
        return redirect("dashboard:payments_tenant:credential_list", prefix=prefix, gateway_pk=gateway_pk)

    if request.method == "POST":
        form = TenantGatewayCredentialForm(request.POST, instance=credential)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.payment_profile = profile
            updated.gateway = gateway_mode.gateway
            updated.status = TenantGatewayCredential.CredentialStatus.PENDING
            updated.validated_at = None
            updated.invalid_reason = ""
            updated.validation_note = ""
            updated.save()
            messages.success(request, "Gateway credentials updated and queued for validation.")
            return redirect("dashboard:payments_tenant:credential_list", prefix=prefix, gateway_pk=gateway_pk)
    else:
        form = TenantGatewayCredentialForm(instance=credential)
        form.fields["gateway"].disabled = True

    return render(
        request,
        "dashboard/payments_tenant/gateway_credential/form.html",
        build_page_context(
            prefix,
            f"Edit Credentials - {credential.label or gateway_mode.gateway.name}",
            "payments_gateways",
            form_title="Update API Credentials",
            form=form,
            gateway_mode=gateway_mode,
            object=credential,
            is_edit=True,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def supported_currency_list(request, prefix):
    profile = get_payment_profile(request)
    currencies = SupportedCurrency.objects.filter(payment_profile=profile).select_related("preferred_gateway").order_by(
        "-is_default", "currency_code"
    )
    return render(
        request,
        "dashboard/payments_tenant/supported_currency/list.html",
        build_page_context(
            prefix,
            "Supported Currencies",
            "payments_settings",
            currencies=currencies,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def supported_currency_create(request, prefix):
    profile = get_payment_profile(request)
    if request.method == "POST":
        form = SupportedCurrencyForm(request.POST)
        if form.is_valid():
            currency = form.save(commit=False)
            currency.payment_profile = profile
            currency.save()
            messages.success(request, f"{currency.currency_code} added to supported currencies.")
            return redirect("dashboard:payments_tenant:supported_currency_list", prefix=prefix)
    else:
        form = SupportedCurrencyForm()

    return render(
        request,
        "dashboard/payments_tenant/supported_currency/form.html",
        build_page_context(
            prefix,
            "Add Currency",
            "payments_settings",
            form=form,
            is_edit=False,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def supported_currency_edit(request, prefix, pk):
    profile = get_payment_profile(request)
    currency = get_object_or_404(SupportedCurrency, pk=pk, payment_profile=profile)
    if request.method == "POST":
        form = SupportedCurrencyForm(request.POST, instance=currency)
        if form.is_valid():
            form.save()
            messages.success(request, f"{currency.currency_code} updated successfully.")
            return redirect("dashboard:payments_tenant:supported_currency_list", prefix=prefix)
    else:
        form = SupportedCurrencyForm(instance=currency)

    return render(
        request,
        "dashboard/payments_tenant/supported_currency/form.html",
        build_page_context(
            prefix,
            f"Edit Currency - {currency.currency_code}",
            "payments_settings",
            form=form,
            object=currency,
            is_edit=True,
            profile=profile,
        ),
    )


@login_required
@dashboard_prefix_required
def supported_currency_delete(request, prefix, pk):
    if request.method != "POST":
        return redirect("dashboard:payments_tenant:supported_currency_list", prefix=prefix)

    profile = get_payment_profile(request)
    currency = get_object_or_404(SupportedCurrency, pk=pk, payment_profile=profile)
    if currency.is_default:
        messages.error(request, "Set another default currency before removing this one.")
        return redirect("dashboard:payments_tenant:supported_currency_list", prefix=prefix)

    code = currency.currency_code
    currency.delete()
    messages.success(request, f"{code} removed from supported currencies.")
    return redirect("dashboard:payments_tenant:supported_currency_list", prefix=prefix)
