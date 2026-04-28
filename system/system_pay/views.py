from __future__ import annotations

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import F, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django_tenants.utils import schema_context

from sabistart_store.navigation import build_platform_navigation
from system.account.platform_support import safe_platform_call, setup_warning_for
from system.feature_marketplace.models import FeaturePurchaseIndex
from system.system_pay.forms import (
    GatewayWebhookConfigForm,
    PaymentGatewayDefinitionForm,
    PlatformCommissionRuleForm,
    PlatformGatewayCredentialForm,
    PlatformPaymentSettingForm,
)
from system.system_pay.models import (
    GatewayWebhookConfig,
    PaymentGatewayDefinition,
    PlatformCommissionRule,
    PlatformDisputeIndex,
    PlatformGatewayCredential,
    PlatformPaymentSetting,
    PlatformPayoutIndex,
    PlatformRefundIndex,
    PlatformTransactionIndex,
    TenantGatewaySnapshot,
    TenantPaymentSnapshot,
)
from system.system_pay.services import (
    get_enabled_gateways,
    get_or_create_platform_payment_setting,
    get_platform_payment_overview,
    get_system_payment_stats,
    rebuild_payment_projections,
    review_tenant_direct_mode,
    set_tenant_payout_enabled,
    sync_tenant_payment_snapshot,
    update_tenant_payment_account_status,
)
from system.feature_marketplace.services import process_marketplace_payment_event


def _is_platform_staff(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff or getattr(user, "is_platform_admin", False))


def platform_staff_required(view_func):
    return login_required(user_passes_test(_is_platform_staff)(view_func), login_url="platform:login")


PAYMENT_NAVIGATION = (
    {"key": "platform_payments", "label": "Overview", "route": "platform_payments:home"},
    {"key": "platform_payments_gateways", "label": "Gateways", "route": "platform_payments:gateways"},
    {"key": "platform_payments_tenants", "label": "Tenant Gateways", "route": "platform_payments:tenants"},
    {"key": "platform_payments_transactions", "label": "Transactions", "route": "platform_payments:transactions"},
    {"key": "platform_payments_payouts", "label": "Payouts & Commissions", "route": "platform_payments:payouts"},
    {"key": "platform_payments_refunds", "label": "Refunds", "route": "platform_payments:refunds"},
    {"key": "platform_payments_disputes", "label": "Disputes", "route": "platform_payments:disputes"},
    {"key": "platform_payments_settings", "label": "Settings", "route": "platform_payments:settings"},
)

PAYMENT_SHARED_MODELS = (
    PaymentGatewayDefinition,
    PlatformGatewayCredential,
    GatewayWebhookConfig,
    PlatformPaymentSetting,
    PlatformCommissionRule,
    TenantPaymentSnapshot,
    TenantGatewaySnapshot,
    PlatformTransactionIndex,
    PlatformPayoutIndex,
    PlatformRefundIndex,
    PlatformDisputeIndex,
)


def _payment_nav(active_key: str):
    from django.urls import reverse

    items = []
    for item in PAYMENT_NAVIGATION:
        items.append(
            {
                **item,
                "url": reverse(item["route"]),
                "active": item["key"] == active_key,
            }
        )
    return items


def _payment_context(request, *, page_title: str, active_platform_nav: str = "platform_payments", active_payment_nav: str = "platform_payments", **extra):
    context = {
        "page_title": page_title,
        "active_platform_nav": active_platform_nav,
        "platform_navigation": build_platform_navigation(active_platform_nav),
        "payment_navigation": _payment_nav(active_payment_nav),
        "setup_warning": setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS),
    }
    context.update(extra)
    return context


@platform_staff_required
def system_pay_home(request):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if request.GET.get("sync") == "1":
        if setup_warning:
            messages.warning(request, setup_warning)
            return redirect("platform_payments:home")
        synced = rebuild_payment_projections()
        messages.success(request, f"Rebuilt platform payment projections for {synced} tenant schema(s).")
        return redirect("platform_payments:home")

    payment_stats = safe_platform_call(get_system_payment_stats, {})
    enabled_gateways = safe_platform_call(lambda: list(get_enabled_gateways()), [])
    context = _payment_context(
        request,
        page_title="Payments",
        active_payment_nav="platform_payments",
        overview=safe_platform_call(
            get_platform_payment_overview,
            lambda: {
                "tenant_count": 0,
                "gateway_count": 0,
                "credential_count": 0,
                "transaction_count": 0,
                "payout_count": 0,
                "refund_count": 0,
                "dispute_count": 0,
                "transaction_volume": 0,
            },
        ),
        gateway_count=safe_platform_call(lambda: PaymentGatewayDefinition.objects.filter(is_enabled=True).count(), 0),
        active_credentials=safe_platform_call(lambda: PlatformGatewayCredential.objects.filter(is_active=True).count(), 0),
        enabled_gateways=enabled_gateways,
        payment_stats=payment_stats,
        webhook_count=safe_platform_call(lambda: GatewayWebhookConfig.objects.filter(is_active=True).count(), 0),
        tenant_snapshots=safe_platform_call(
            lambda: list(TenantPaymentSnapshot.objects.order_by("business_name", "schema_name")[:8]),
            [],
        ),
        recent_transactions=safe_platform_call(
            lambda: list(PlatformTransactionIndex.objects.order_by("-paid_at", "-created_at")[:10]),
            [],
        ),
        setup_warning=setup_warning,
    )
    return render(request, "system_pay/overview.html", context)


@platform_staff_required
def gateways(request):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    context = _payment_context(
        request,
        page_title="Payment Gateways",
        active_payment_nav="platform_payments_gateways",
        gateways=PaymentGatewayDefinition.objects.prefetch_related("platform_credentials").order_by("display_order", "name"),
    )
    return render(request, "system_pay/gateways.html", context)


@platform_staff_required
def gateway_detail(request, gateway_id):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    gateway = get_object_or_404(PaymentGatewayDefinition, pk=gateway_id)
    context = _payment_context(
        request,
        page_title=gateway.name,
        active_payment_nav="platform_payments_gateways",
        gateway=gateway,
        webhook_config=getattr(gateway, "webhook_config", None),
        credentials=gateway.platform_credentials.order_by("-priority", "name"),
        tenant_snapshots=TenantGatewaySnapshot.objects.filter(gateway_provider=gateway.provider).order_by("schema_name"),
    )
    return render(request, "system_pay/gateway_detail.html", context)


@platform_staff_required
def gateway_create(request):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    form = PaymentGatewayDefinitionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        gateway = form.save()
        messages.success(request, "Gateway definition created.")
        return redirect("platform_payments:gateway_detail", gateway_id=gateway.id)
    context = _payment_context(
        request,
        page_title="Add gateway",
        active_payment_nav="platform_payments_gateways",
        form=form,
        form_title="Add payment gateway",
        form_intro="Create a reusable platform gateway definition once, then attach platform credentials and webhook settings from the gateway workspace.",
        cancel_href=redirect("platform_payments:gateways").url,
    )
    return render(request, "system_pay/form_page.html", context)


@platform_staff_required
def gateway_edit(request, gateway_id):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    gateway = get_object_or_404(PaymentGatewayDefinition, pk=gateway_id)
    form = PaymentGatewayDefinitionForm(request.POST or None, instance=gateway)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Gateway updated.")
        return redirect("platform_payments:gateway_detail", gateway_id=gateway.id)
    context = _payment_context(
        request,
        page_title=f"Edit {gateway.name}",
        active_payment_nav="platform_payments_gateways",
        gateway=gateway,
        form=form,
        form_title=f"Edit {gateway.name}",
        form_intro="Update the parent gateway definition. Credentials and webhook configuration inherit from this gateway instead of asking you to re-enter the provider identity.",
        cancel_href=redirect("platform_payments:gateway_detail", gateway_id=gateway.id).url,
    )
    return render(request, "system_pay/form_page.html", context)


@platform_staff_required
def credential_create(request, gateway_id):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    gateway = get_object_or_404(PaymentGatewayDefinition, pk=gateway_id)
    form = PlatformGatewayCredentialForm(
        request.POST or None,
        initial={"name": gateway.name, "default_currency": "NGN"},
    )
    if request.method == "POST" and form.is_valid():
        credential = form.save(commit=False)
        credential.gateway = gateway
        credential.save()
        messages.success(request, "Platform credential saved.")
        return redirect("platform_payments:gateway_detail", gateway_id=gateway.id)
    context = _payment_context(
        request,
        page_title=f"{gateway.name} credential",
        active_payment_nav="platform_payments_gateways",
        gateway=gateway,
        form=form,
        form_title=f"Add credential for {gateway.name}",
        form_intro="This credential inherits its provider from the parent gateway. You only fill in the environment, keys, limits, and health information here.",
        cancel_href=redirect("platform_payments:gateway_detail", gateway_id=gateway.id).url,
    )
    return render(request, "system_pay/form_page.html", context)


@platform_staff_required
def credential_edit(request, credential_id):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    credential = get_object_or_404(PlatformGatewayCredential.objects.select_related("gateway"), pk=credential_id)
    form = PlatformGatewayCredentialForm(request.POST or None, instance=credential)
    if request.method == "POST" and form.is_valid():
        updated = form.save(commit=False)
        updated.gateway = credential.gateway
        updated.save()
        messages.success(request, "Platform credential updated.")
        return redirect("platform_payments:gateway_detail", gateway_id=credential.gateway_id)
    context = _payment_context(
        request,
        page_title=f"Edit credential: {credential.name}",
        active_payment_nav="platform_payments_gateways",
        gateway=credential.gateway,
        form=form,
        form_title=f"Edit credential for {credential.gateway.name}",
        form_intro="Update the active keys, limits, and health metadata for this platform credential without touching the parent gateway definition.",
        cancel_href=redirect("platform_payments:gateway_detail", gateway_id=credential.gateway_id).url,
    )
    return render(request, "system_pay/form_page.html", context)


@platform_staff_required
def webhook_edit(request, gateway_id):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    gateway = get_object_or_404(PaymentGatewayDefinition, pk=gateway_id)
    webhook_instance = getattr(gateway, "webhook_config", None)
    form = GatewayWebhookConfigForm(request.POST or None, instance=webhook_instance)
    if request.method == "POST" and form.is_valid():
        webhook = form.save(commit=False)
        webhook.gateway = gateway
        webhook.save()
        messages.success(request, "Webhook configuration saved.")
        return redirect("platform_payments:gateway_detail", gateway_id=gateway.id)
    context = _payment_context(
        request,
        page_title=f"{gateway.name} webhook",
        active_payment_nav="platform_payments_gateways",
        gateway=gateway,
        form=form,
        form_title=f"Webhook settings for {gateway.name}",
        form_intro="Manage the endpoint, signature headers, and verification settings for this gateway. The webhook remains attached to the parent gateway automatically.",
        cancel_href=redirect("platform_payments:gateway_detail", gateway_id=gateway.id).url,
    )
    return render(request, "system_pay/form_page.html", context)


@platform_staff_required
def tenants(request):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    snapshots = TenantPaymentSnapshot.objects.all().order_by("business_name", "schema_name")
    if q:
        snapshots = snapshots.filter(Q(business_name__icontains=q) | Q(schema_name__icontains=q))
    if status:
        snapshots = snapshots.filter(account_status=status)
    context = _payment_context(
        request,
        page_title="Tenant Gateway Management",
        active_payment_nav="platform_payments_tenants",
        snapshots=snapshots,
        q=q,
        selected_status=status,
    )
    return render(request, "system_pay/tenants.html", context)


@platform_staff_required
def tenant_detail(request, schema_name):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    snapshot = get_object_or_404(TenantPaymentSnapshot, schema_name=schema_name)
    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "sync_snapshot":
            sync_tenant_payment_snapshot(snapshot.shop)
            messages.success(request, "Tenant payment snapshot refreshed.")
            return redirect("platform_payments:tenant_detail", schema_name=schema_name)
        if action == "update_status":
            result = update_tenant_payment_account_status(
                schema_name=schema_name,
                account_status=request.POST.get("account_status", snapshot.account_status),
                reason=request.POST.get("restriction_reason", ""),
            )
            if result.success:
                messages.success(request, result.message)
            else:
                messages.error(request, "; ".join(result.errors) or "Could not update tenant status.")
            return redirect("platform_payments:tenant_detail", schema_name=schema_name)
        if action == "toggle_payout":
            result = set_tenant_payout_enabled(
                schema_name=schema_name,
                enabled=request.POST.get("enabled") == "1",
            )
            if result.success:
                messages.success(request, result.message)
            else:
                messages.error(request, "; ".join(result.errors) or "Could not update payout setting.")
            return redirect("platform_payments:tenant_detail", schema_name=schema_name)
        if action == "review_gateway":
            result = review_tenant_direct_mode(
                schema_name=schema_name,
                gateway_provider=request.POST.get("gateway_provider", ""),
                approved=request.POST.get("approved") == "1",
                notes=request.POST.get("review_notes", ""),
            )
            if result.success:
                messages.success(request, result.message)
            else:
                messages.error(request, "; ".join(result.errors) or "Could not review tenant gateway mode.")
            return redirect("platform_payments:tenant_detail", schema_name=schema_name)

    context = _payment_context(
        request,
        page_title=snapshot.business_name or snapshot.schema_name,
        active_payment_nav="platform_payments_tenants",
        snapshot=snapshot,
        gateway_snapshots=TenantGatewaySnapshot.objects.filter(schema_name=schema_name).order_by("gateway_name"),
        transactions=PlatformTransactionIndex.objects.filter(schema_name=schema_name).order_by("-paid_at", "-created_at")[:20],
        payouts=PlatformPayoutIndex.objects.filter(schema_name=schema_name).order_by("-requested_at")[:20],
        refunds=PlatformRefundIndex.objects.filter(schema_name=schema_name).order_by("-requested_at")[:20],
        disputes=PlatformDisputeIndex.objects.filter(schema_name=schema_name).order_by("-opened_at")[:20],
    )
    return render(request, "system_pay/tenant_detail.html", context)


@platform_staff_required
def transactions(request):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    gateway = request.GET.get("gateway", "").strip()
    transactions = PlatformTransactionIndex.objects.all().order_by("-paid_at", "-created_at")
    if q:
        transactions = transactions.filter(
            Q(internal_reference__icontains=q)
            | Q(gateway_reference__icontains=q)
            | Q(customer_email__icontains=q)
            | Q(order_number__icontains=q)
        )
    if status:
        transactions = transactions.filter(status=status)
    if gateway:
        transactions = transactions.filter(gateway_provider=gateway)
    context = _payment_context(
        request,
        page_title="Transaction Logs",
        active_payment_nav="platform_payments_transactions",
        transactions=transactions[:200],
        q=q,
        selected_status=status,
        selected_gateway=gateway,
    )
    return render(request, "system_pay/transactions.html", context)


@platform_staff_required
def payouts(request):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    status = request.GET.get("status", "").strip()
    payouts_qs = PlatformPayoutIndex.objects.all().order_by("-requested_at")
    if status:
        payouts_qs = payouts_qs.filter(status=status)
    context = _payment_context(
        request,
        page_title="Payouts & Commissions",
        active_payment_nav="platform_payments_payouts",
        payouts=payouts_qs[:200],
        commission_rules=PlatformCommissionRule.objects.order_by("-priority", "name"),
        selected_status=status,
    )
    return render(request, "system_pay/payouts.html", context)


@platform_staff_required
def refunds(request):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    status = request.GET.get("status", "").strip()
    refunds_qs = PlatformRefundIndex.objects.all().order_by("-requested_at")
    if status:
        refunds_qs = refunds_qs.filter(status=status)
    context = _payment_context(
        request,
        page_title="Refunds",
        active_payment_nav="platform_payments_refunds",
        refunds=refunds_qs[:200],
        selected_status=status,
    )
    return render(request, "system_pay/refunds.html", context)


@platform_staff_required
def disputes(request):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    status = request.GET.get("status", "").strip()
    disputes_qs = PlatformDisputeIndex.objects.all().order_by("-opened_at")
    if status:
        disputes_qs = disputes_qs.filter(status=status)
    context = _payment_context(
        request,
        page_title="Disputes",
        active_payment_nav="platform_payments_disputes",
        disputes=disputes_qs[:200],
        selected_status=status,
    )
    return render(request, "system_pay/disputes.html", context)


@platform_staff_required
def settings_view(request):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    setting = get_or_create_platform_payment_setting()
    context = _payment_context(
        request,
        page_title="Payment Settings",
        active_payment_nav="platform_payments_settings",
        setting=setting,
        commission_rules=PlatformCommissionRule.objects.order_by("-priority", "name"),
    )
    return render(request, "system_pay/settings.html", context)


@platform_staff_required
def payment_settings_edit(request):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    setting = get_or_create_platform_payment_setting()
    form = PlatformPaymentSettingForm(request.POST or None, instance=setting)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Platform payment settings updated.")
        return redirect("platform_payments:settings")
    context = _payment_context(
        request,
        page_title="Edit payment settings",
        active_payment_nav="platform_payments_settings",
        form=form,
        form_title="Platform payment settings",
        form_intro="Manage global currency defaults, payout review behavior, and platform-wide payment tooling from one dedicated page.",
        cancel_href=redirect("platform_payments:settings").url,
    )
    return render(request, "system_pay/form_page.html", context)


@platform_staff_required
def commission_rule_create(request):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    form = PlatformCommissionRuleForm(request.POST or None)
    preview_fee = None
    if request.method == "POST" and form.is_valid():
        rule = form.save()
        preview_amount = form.cleaned_data.get("preview_amount")
        if preview_amount is not None:
            preview_fee = rule.preview_fee(preview_amount)
        messages.success(request, "Commission rule saved.")
        return redirect("platform_payments:settings")
    context = _payment_context(
        request,
        page_title="Add commission rule",
        active_payment_nav="platform_payments_settings",
        form=form,
        form_title="Add commission rule",
        form_intro="Create a reusable commission policy for gateway, country, plan, or currency-specific payout behavior.",
        cancel_href=redirect("platform_payments:settings").url,
        preview_fee=preview_fee,
    )
    return render(request, "system_pay/form_page.html", context)


@platform_staff_required
def commission_rule_edit(request, rule_id):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    if setup_warning:
        messages.warning(request, setup_warning)
        return redirect("platform_payments:home")
    rule = get_object_or_404(PlatformCommissionRule, pk=rule_id)
    form = PlatformCommissionRuleForm(request.POST or None, instance=rule)
    preview_fee = None
    if request.method == "POST" and form.is_valid():
        updated = form.save()
        preview_amount = form.cleaned_data.get("preview_amount")
        if preview_amount is not None:
            preview_fee = updated.preview_fee(preview_amount)
        messages.success(request, "Commission rule updated.")
        return redirect("platform_payments:settings")
    context = _payment_context(
        request,
        page_title=f"Edit commission rule: {rule.name}",
        active_payment_nav="platform_payments_settings",
        form=form,
        form_title=f"Edit commission rule: {rule.name}",
        form_intro="Adjust the percentage, flat fee, caps, and applicability for this rule without leaving the payment settings workspace.",
        cancel_href=redirect("platform_payments:settings").url,
        preview_fee=preview_fee,
    )
    return render(request, "system_pay/form_page.html", context)


class PaymentGatewaysAPIView(View):
    """API endpoint to list available payment gateways."""

    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

    def get(self, request):
        gateways = safe_platform_call(lambda: PaymentGatewayDefinition.objects.filter(is_enabled=True), PaymentGatewayDefinition.objects.none)
        data = [
            {
                "id": str(gateway.id),
                "provider": gateway.provider,
                "name": gateway.name,
                "description": gateway.description,
                "logo_url": gateway.logo_url,
                "is_available_for_direct_mode": gateway.is_available_for_direct_mode,
                "supports_recurring": gateway.supports_recurring,
                "supports_refunds": gateway.supports_refunds,
                "supported_currencies": gateway.supported_currencies,
            }
            for gateway in gateways
        ]
        return JsonResponse({"gateways": data})

    def post(self, request):
        return JsonResponse({"error": "POST method not implemented"}, status=405)


def health_check(request):
    setup_warning = setup_warning_for("Platform payments", *PAYMENT_SHARED_MODELS)
    active_gateways = safe_platform_call(lambda: PlatformGatewayCredential.objects.filter(is_active=True).count(), 0)
    total_gateways = safe_platform_call(lambda: PaymentGatewayDefinition.objects.count(), 0)
    webhook_configs = safe_platform_call(lambda: GatewayWebhookConfig.objects.filter(is_active=True).count(), 0)
    status = {
        "system_pay_status": "healthy" if not setup_warning else "degraded",
        "active_gateways": active_gateways,
        "total_gateways": total_gateways,
        "configured_webhooks": webhook_configs,
        "setup_warning": setup_warning,
    }
    return JsonResponse(status)


def _request_payload(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
    return request.POST.dict() or request.GET.dict()


def _normalize_marketplace_status(raw_status: str, raw_event: str = "") -> str:
    status = (raw_status or "").strip().lower()
    event = (raw_event or "").strip().lower()
    if status:
        return status
    event_map = {
        "charge.success": "success",
        "payment.success": "success",
        "payment.completed": "success",
        "charge.failed": "failed",
        "payment.failed": "failed",
        "payment.cancelled": "cancelled",
        "payment.canceled": "cancelled",
    }
    return event_map.get(event, "")


def _marketplace_payload_data(payload):
    data = payload.get("data", {})
    return data if isinstance(data, dict) else {}


def _extract_marketplace_purchase_reference(provider: str, payload: dict) -> str:
    data = _marketplace_payload_data(payload)
    stripe_object = data.get("object", {}) if isinstance(data.get("object", {}), dict) else {}
    metadata = stripe_object.get("metadata", {}) if isinstance(stripe_object.get("metadata", {}), dict) else {}
    return (
        payload.get("purchase_reference", "")
        or data.get("purchase_reference", "")
        or metadata.get("order_number", "")
        or stripe_object.get("client_reference_id", "")
    )


def _extract_marketplace_gateway_reference(provider: str, payload: dict) -> str:
    data = _marketplace_payload_data(payload)
    stripe_object = data.get("object", {}) if isinstance(data.get("object", {}), dict) else {}
    metadata = stripe_object.get("metadata", {}) if isinstance(stripe_object.get("metadata", {}), dict) else {}

    if provider == "paystack":
        return payload.get("reference", "") or payload.get("trxref", "") or data.get("reference", "")
    if provider == "flutterwave":
        return payload.get("tx_ref", "") or data.get("tx_ref", "") or payload.get("gateway_reference", "")
    if provider == "stripe":
        return (
            stripe_object.get("client_reference_id", "")
            or metadata.get("reference", "")
            or payload.get("gateway_reference", "")
        )
    return payload.get("gateway_reference", "") or data.get("gateway_reference", "")


def _extract_marketplace_transaction_id(provider: str, payload: dict) -> str:
    data = _marketplace_payload_data(payload)
    stripe_object = data.get("object", {}) if isinstance(data.get("object", {}), dict) else {}

    if provider == "paystack":
        return str(data.get("id", "") or payload.get("gateway_transaction_id", ""))
    if provider == "flutterwave":
        return str(payload.get("transaction_id", "") or data.get("id", "") or payload.get("id", ""))
    if provider == "stripe":
        return str(stripe_object.get("payment_intent", "") or stripe_object.get("id", "") or payload.get("session_id", ""))
    return str(payload.get("gateway_transaction_id", "") or data.get("id", ""))


def _transaction_status_for_marketplace(payment_status: str) -> str:
    from dashboard.payments_tenant.models import TransactionStatus

    normalized = (payment_status or "").strip().lower()
    if normalized in {"success", "successful", "completed", "paid"}:
        return TransactionStatus.SUCCESS
    if normalized in {"processing", "pending"}:
        return TransactionStatus.PROCESSING
    if normalized in {"cancelled", "canceled", "abandoned"}:
        return TransactionStatus.CANCELLED
    return TransactionStatus.FAILED


def _verify_and_record_marketplace_payment(*, purchase_reference: str, provider: str, payload: dict, headers=None):
    index = get_object_or_404(FeaturePurchaseIndex, purchase_reference=purchase_reference)
    with schema_context(index.schema_name):
        from dashboard.feature_marketplace.models import FeaturePurchase
        from dashboard.payments_tenant.models import PaymentIntent
        from dashboard.payments_tenant.services.intent_transactions import confirm_transaction
        from dashboard.payments_tenant.services.provider_checkout import verify_gateway_checkout

        purchase = get_object_or_404(FeaturePurchase, purchase_reference=purchase_reference)
        intent = (
            PaymentIntent.objects.select_related(
                "payment_profile",
                "gateway_mode__gateway",
                "gateway_mode__platform_credential",
                "gateway_mode__direct_credential",
            )
            .filter(order_number=purchase_reference)
            .order_by("-created_at")
            .first()
        )
        if intent is None:
            return {
                "purchase": purchase,
                "intent": None,
                "status_value": _normalize_marketplace_status(
                    payload.get("status", ""),
                    payload.get("event", ""),
                ),
                "gateway_reference": _extract_marketplace_gateway_reference(provider, payload),
                "gateway_transaction_id": _extract_marketplace_transaction_id(provider, payload),
                "metadata": {},
            }

        verification = verify_gateway_checkout(intent, payload, headers=dict(headers or {}))
        if not verification.success:
            raise ValueError(verification.error or "Payment verification failed.")

        status_value = verification.payment_status or _normalize_marketplace_status(
            payload.get("status", ""),
            payload.get("event", ""),
        )
        gateway_reference = verification.gateway_reference or _extract_marketplace_gateway_reference(provider, payload)
        gateway_transaction_id = verification.gateway_transaction_id or _extract_marketplace_transaction_id(provider, payload)

        confirm_transaction(
            payment_profile=intent.payment_profile,
            gateway_reference=gateway_reference,
            gateway_transaction_id=gateway_transaction_id,
            amount=verification.amount or intent.amount,
            currency=verification.currency or intent.currency,
            status=_transaction_status_for_marketplace(status_value),
            gateway_provider=provider,
            raw_response=verification.raw_response,
            gateway_message=verification.gateway_message,
            payment_channel=verification.payment_channel,
        )
        return {
            "purchase": purchase,
            "intent": intent,
            "status_value": status_value,
            "gateway_reference": gateway_reference,
            "gateway_transaction_id": gateway_transaction_id,
            "metadata": {"verified_response": verification.raw_response},
        }


@require_http_methods(["GET", "POST"])
def marketplace_checkout(request, purchase_reference):
    index = get_object_or_404(FeaturePurchaseIndex, purchase_reference=purchase_reference)
    with schema_context(index.schema_name):
        from dashboard.feature_marketplace.models import FeaturePurchase

        purchase = get_object_or_404(FeaturePurchase, purchase_reference=purchase_reference)

    provider_checkout_url = (purchase.payment_metadata or {}).get("provider_checkout_url", "")
    if request.method == "GET" and provider_checkout_url and purchase.status in {
        purchase.Status.PENDING,
        purchase.Status.PROCESSING,
    }:
        return redirect(provider_checkout_url)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "confirm":
            result = process_marketplace_payment_event(
                payment_status="success",
                purchase_reference=purchase_reference,
                gateway_reference=f"marketplace_{purchase_reference}",
                gateway_transaction_id=f"marketplace_tx_{purchase_reference}",
                metadata={
                    "payment_surface": "system_pay_marketplace_checkout",
                    "provider": purchase.gateway_provider,
                },
            )
            if result.success and result.redirect_url:
                return redirect(result.redirect_url)
            messages.success(request, "Marketplace purchase completed.")
            return redirect(result.redirect_url or purchase.success_redirect_url or "/")
        if action == "cancel":
            result = process_marketplace_payment_event(
                payment_status="cancelled",
                purchase_reference=purchase_reference,
                metadata={
                    "payment_surface": "system_pay_marketplace_checkout",
                    "provider": purchase.gateway_provider,
                },
            )
            if result.success and result.redirect_url:
                return redirect(result.redirect_url)
            messages.info(request, "Marketplace purchase cancelled.")
            return redirect(result.redirect_url or purchase.cancel_redirect_url or "/")

    context = {
        "page_title": "Marketplace Payment",
        "purchase": purchase,
        "index": index,
        "selected_gateway": {
            "provider": purchase.gateway_provider,
            "name": purchase.gateway_name,
        },
    }
    return render(request, "system_pay/marketplace_checkout.html", context)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def marketplace_payment_callback(request, purchase_reference):
    payload = _request_payload(request)
    index = get_object_or_404(FeaturePurchaseIndex, purchase_reference=purchase_reference)
    with schema_context(index.schema_name):
        from dashboard.feature_marketplace.models import FeaturePurchase

        purchase = get_object_or_404(FeaturePurchase, purchase_reference=purchase_reference)
    provider = purchase.gateway_provider or payload.get("provider", "")
    callback_metadata = {
        "callback_source": "system_pay",
        "provider": provider,
        "payload": payload,
    }
    try:
        verification_data = _verify_and_record_marketplace_payment(
            purchase_reference=purchase_reference,
            provider=provider,
            payload=payload,
            headers=request.headers,
        )
        status_value = verification_data["status_value"] or _normalize_marketplace_status(
            payload.get("status") or request.GET.get("status", ""),
            payload.get("event", ""),
        )
        gateway_reference = verification_data["gateway_reference"]
        gateway_transaction_id = verification_data["gateway_transaction_id"]
        callback_metadata.update(verification_data["metadata"])
    except ValueError as exc:
        if request.method == "GET":
            messages.error(request, str(exc))
            return redirect(purchase.cancel_redirect_url or purchase.success_redirect_url or "/")
        return JsonResponse(
            {
                "success": False,
                "message": str(exc),
                "purchase_reference": purchase_reference,
            },
            status=400,
        )

    result = process_marketplace_payment_event(
        payment_status=status_value or "success",
        purchase_reference=purchase_reference,
        gateway_reference=gateway_reference,
        gateway_transaction_id=gateway_transaction_id,
        metadata=callback_metadata,
    )
    if request.method == "GET" and result.redirect_url:
        return redirect(result.redirect_url)
    status_code = 200 if result.success else 400
    return JsonResponse(
        {
            "success": result.success,
            "message": result.message,
            "errors": result.errors,
            "purchase_reference": result.purchase_reference,
            "schema_name": result.schema_name,
            "status": result.status,
            "redirect_url": result.redirect_url,
        },
        status=status_code,
    )


@csrf_exempt
@require_http_methods(["POST"])
def marketplace_webhook(request, provider):
    """
    Receive a payment gateway webhook, validate its signature, deduplicate it
    using ProcessedWebhookEvent, then route the event to the marketplace
    fulfillment layer.

    Security layers (in order)
    --------------------------
    1. Signature validation — rejects events whose HMAC doesn't match the
       webhook secret configured for this gateway.
    2. Idempotency guard  — if (gateway_provider, gateway_event_id) already
       exists in ProcessedWebhookEvent, the event is ACK'd and discarded.
    3. Purchase verification — amount is cross-checked against the stored
       PaymentIntent (see confirm_transaction / amount mismatch detection).
    """
    import time as _time

    start_ms = int(_time.time() * 1000)
    raw_body = request.body

    # ── 1. Signature validation ──────────────────────────────────────────────
    webhook_config = GatewayWebhookConfig.objects.filter(
        gateway__provider=provider,
        is_active=True,
    ).first()

    if webhook_config is not None:
        GatewayWebhookConfig.objects.filter(pk=webhook_config.pk).update(
            last_received_at=timezone.now(),
            total_events_received=F("total_events_received") + 1,
        )
        webhook_secret = webhook_config.webhook_secret or ""
        sig_header_name = webhook_config.signature_header or ""
        if webhook_secret and sig_header_name:
            signature = request.headers.get(sig_header_name, "")
            from dashboard.payments_tenant.services.provider_checkout import (
                validate_webhook_signature_for_provider,
            )
            if not validate_webhook_signature_for_provider(
                provider=provider,
                payload_bytes=raw_body,
                signature=signature,
                secret=webhook_secret,
            ):
                return JsonResponse(
                    {"success": False, "message": "Webhook signature invalid."},
                    status=401,
                )

    # ── 2. Extract gateway event ID for idempotency ──────────────────────────
    payload = _request_payload(request)
    # Extract a stable, gateway-specific event identifier.
    gateway_event_id = (
        # Paystack: `data.id` or `id` field on the event envelope
        str(payload.get("id", "")
            or payload.get("data", {}).get("id", "")
            or payload.get("event", "")
            or payload.get("tx_ref", "")  # Flutterwave tx_ref
            or payload.get("reference", "")  # Paystack reference
        )
    )

    # ── 3. Idempotency guard (within tenant schema) ──────────────────────────
    # We need the purchase_reference to look up the tenant schema first,
    # since ProcessedWebhookEvent is a tenant-scoped model.
    purchase_reference = _extract_marketplace_purchase_reference(provider, payload)
    if gateway_event_id and purchase_reference:
        try:
            idx = FeaturePurchaseIndex.objects.filter(purchase_reference=purchase_reference).first()
            if idx:
                with schema_context(idx.schema_name):
                    from dashboard.payments_tenant.models import ProcessedWebhookEvent
                    if ProcessedWebhookEvent.is_duplicate(
                        gateway_provider=provider,
                        gateway_event_id=gateway_event_id,
                    ):
                        return JsonResponse(
                            {
                                "success": True,
                                "message": "Duplicate event — already processed.",
                                "action": "duplicate_skipped",
                            },
                            status=200,
                        )
        except Exception:
            pass  # If the table isn't migrated yet, fall through gracefully.

    # ── 4. Route to fulfillment ──────────────────────────────────────────────
    gateway_reference = _extract_marketplace_gateway_reference(provider, payload)
    gateway_transaction_id = _extract_marketplace_transaction_id(provider, payload)
    webhook_metadata = {
        "webhook_source": "system_pay",
        "provider": provider,
        "payload": payload,
    }

    if purchase_reference:
        try:
            verification_data = _verify_and_record_marketplace_payment(
                purchase_reference=purchase_reference,
                provider=provider,
                payload=payload,
                headers=request.headers,
            )
            gateway_reference = verification_data["gateway_reference"] or gateway_reference
            gateway_transaction_id = verification_data["gateway_transaction_id"] or gateway_transaction_id
            webhook_metadata.update(verification_data["metadata"])
            payment_status = verification_data["status_value"]
        except ValueError as exc:
            return JsonResponse(
                {
                    "success": False,
                    "message": str(exc),
                    "purchase_reference": purchase_reference,
                },
                status=400,
            )
    else:
        payment_status = _normalize_marketplace_status(payload.get("status", ""), payload.get("event", ""))

    result = process_marketplace_payment_event(
        payment_status=payment_status,
        purchase_reference=purchase_reference,
        gateway_reference=gateway_reference,
        gateway_transaction_id=gateway_transaction_id,
        metadata=webhook_metadata,
    )

    # ── 5. Record idempotency marker (within tenant schema) ──────────────────
    if gateway_event_id and result.schema_name:
        try:
            from dashboard.payments_tenant.models import ProcessedWebhookEvent
            processing_ms = int(_time.time() * 1000) - start_ms
            with schema_context(result.schema_name):
                ProcessedWebhookEvent.record(
                    gateway_provider=provider,
                    gateway_event_id=gateway_event_id,
                    event_type=payload.get("event", ""),
                    order_number=purchase_reference,
                    action_taken=result.status or "processed",
                    raw_payload=payload,
                    processing_ms=processing_ms,
                )
        except Exception:
            pass  # Never let idempotency bookkeeping fail the response.

    status_code = 200 if result.success else 400
    return JsonResponse(
        {
            "success": result.success,
            "message": result.message,
            "errors": result.errors,
            "purchase_reference": result.purchase_reference,
            "schema_name": result.schema_name,
            "status": result.status,
        },
        status=status_code,
    )
