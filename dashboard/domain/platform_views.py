from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_tenants.utils import schema_context

from dashboard.domain.commerce import (
    ensure_default_domain_catalog,
    process_domain_payment_event,
    process_due_domain_renewals,
    process_paid_domain_orders,
    reconcile_managed_domain_integrity,
    sync_provider_tld_catalog,
)
from dashboard.domain.forms import DomainProviderCredentialForm, TldCatalogEntryForm
from dashboard.domain.models import (
    DomainActivityLog,
    DomainProvider,
    DomainProviderCredential,
    DomainProvisioningAttempt,
    DomainPurchaseOrder,
    ManagedDomain,
    ManagedDomainRenewal,
    TldCatalogEntry,
)
from sabistart_store.navigation import build_platform_navigation
from system.account.platform_support import setup_warning_for


def _is_platform_staff(user):
    return user.is_authenticated and (user.is_superuser or user.is_staff or getattr(user, "is_platform_admin", False))


def platform_staff_required(view_func):
    return login_required(user_passes_test(_is_platform_staff)(view_func), login_url="platform:login")


DOMAIN_NAVIGATION = (
    {"key": "platform_domains", "label": "Overview", "route": "platform_domains:home"},
    {"key": "platform_domains_providers", "label": "Providers", "route": "platform_domains:providers"},
    {"key": "platform_domains_tlds", "label": "TLD Pricing", "route": "platform_domains:tlds"},
    {"key": "platform_domains_orders", "label": "Orders", "route": "platform_domains:orders"},
    {"key": "platform_domains_managed", "label": "Managed Domains", "route": "platform_domains:managed_domains"},
    {"key": "platform_domains_renewals", "label": "Renewals", "route": "platform_domains:renewals"},
)

DOMAIN_SHARED_MODELS = (
    DomainProvider,
    DomainProviderCredential,
    TldCatalogEntry,
    DomainPurchaseOrder,
    ManagedDomain,
    ManagedDomainRenewal,
    DomainProvisioningAttempt,
    DomainActivityLog,
)


def _domain_nav(active_key: str):
    items = []
    for item in DOMAIN_NAVIGATION:
        items.append({**item, "url": reverse(item["route"]), "active": item["key"] == active_key})
    return items


def _context(request, *, page_title: str, active_domain_nav: str = "platform_domains", **extra):
    context = {
        "page_title": page_title,
        "active_platform_nav": "platform_domains",
        "platform_navigation": build_platform_navigation("platform_domains"),
        "domain_navigation": _domain_nav(active_domain_nav),
        "setup_warning": setup_warning_for("Domain commerce", *DOMAIN_SHARED_MODELS),
    }
    context.update(extra)
    return context


@platform_staff_required
def home(request):
    provider, _ = ensure_default_domain_catalog()
    action = request.GET.get("action", "")
    if action == "sync_tlds":
        synced = sync_provider_tld_catalog(provider=provider)
        messages.info(request, f"Synced {synced} TLD catalog row(s) for {provider.name}.")
        return redirect("platform_domains:home")
    if action == "process_orders":
        processed = process_paid_domain_orders()
        messages.success(request, f"Processed {processed} paid domain order(s).")
        return redirect("platform_domains:home")
    if action == "process_renewals":
        processed = process_due_domain_renewals()
        messages.success(request, f"Processed {processed} due renewal(s).")
        return redirect("platform_domains:home")
    if action == "reconcile":
        result = reconcile_managed_domain_integrity()
        messages.success(request, f"Reconciled {result['fixed_connections']} connection(s) and synced {result['synced']} domain(s).")
        return redirect("platform_domains:home")

    context = _context(
        request,
        page_title="Domain Commerce",
        active_domain_nav="platform_domains",
        provider_count=DomainProvider.objects.count(),
        credential_count=DomainProviderCredential.objects.filter(is_active=True).count(),
        order_count=DomainPurchaseOrder.objects.count(),
        managed_count=ManagedDomain.objects.count(),
        renewals_due=ManagedDomainRenewal.objects.filter(
            status=ManagedDomainRenewal.Status.SCHEDULED,
            scheduled_for__lte=timezone.now(),
        ).count(),
        recent_orders=DomainPurchaseOrder.objects.select_related("tenant", "provider", "managed_domain").order_by("-created_at")[:12],
        recent_activity=DomainActivityLog.objects.select_related("tenant").order_by("-created_at")[:15],
        failing_attempts=DomainProvisioningAttempt.objects.filter(status=DomainProvisioningAttempt.Status.FAILED).order_by("-created_at")[:10],
    )
    return render(request, "account/domains/index.html", context)


@platform_staff_required
def providers(request):
    ensure_default_domain_catalog()
    context = _context(
        request,
        page_title="Domain Providers",
        active_domain_nav="platform_domains_providers",
        providers=DomainProvider.objects.prefetch_related("credentials").order_by("display_order", "name"),
    )
    return render(request, "account/domains/providers.html", context)


@platform_staff_required
def provider_credential_create(request):
    ensure_default_domain_catalog()
    form = DomainProviderCredentialForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        credential = form.save()
        if credential.is_default:
            DomainProviderCredential.objects.filter(provider=credential.provider).exclude(pk=credential.pk).update(is_default=False)
        messages.success(request, "Registrar credential saved.")
        return redirect("platform_domains:providers")
    context = _context(
        request,
        page_title="Add Provider Credential",
        active_domain_nav="platform_domains_providers",
        form=form,
    )
    return render(request, "account/domains/provider_credential_form.html", context)


@platform_staff_required
def provider_credential_edit(request, credential_id):
    ensure_default_domain_catalog()
    credential = get_object_or_404(DomainProviderCredential, pk=credential_id)
    form = DomainProviderCredentialForm(request.POST or None, instance=credential)
    if request.method == "POST" and form.is_valid():
        updated = form.save()
        if updated.is_default:
            DomainProviderCredential.objects.filter(provider=updated.provider).exclude(pk=updated.pk).update(is_default=False)
        messages.success(request, "Registrar credential updated.")
        return redirect("platform_domains:providers")
    context = _context(
        request,
        page_title=f"Edit {credential.name}",
        active_domain_nav="platform_domains_providers",
        form=form,
        credential=credential,
    )
    return render(request, "account/domains/provider_credential_form.html", context)


@platform_staff_required
def tlds(request):
    ensure_default_domain_catalog()
    entry = None
    if request.GET.get("entry"):
        entry = get_object_or_404(TldCatalogEntry, pk=request.GET["entry"])
    form = TldCatalogEntryForm(request.POST or None, instance=entry)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "TLD pricing updated.")
        return redirect("platform_domains:tlds")
    context = _context(
        request,
        page_title="TLD Pricing",
        active_domain_nav="platform_domains_tlds",
        tlds=TldCatalogEntry.objects.select_related("provider").order_by("sort_order", "tld"),
        form=form,
        editing_entry=entry,
    )
    return render(request, "account/domains/tlds.html", context)


@platform_staff_required
def orders(request):
    orders = DomainPurchaseOrder.objects.select_related("tenant", "provider", "managed_domain").order_by("-created_at")
    q = request.GET.get("q", "").strip()
    if q:
        orders = orders.filter(
            Q(domain_name__icontains=q)
            | Q(purchase_reference__icontains=q)
            | Q(tenant__schema_name__icontains=q)
            | Q(tenant__name__icontains=q)
        )
    context = _context(
        request,
        page_title="Domain Orders",
        active_domain_nav="platform_domains_orders",
        orders=orders,
        q=q,
    )
    return render(request, "account/domains/orders.html", context)


@platform_staff_required
def managed_domains(request):
    domains = ManagedDomain.objects.select_related("tenant", "provider", "source_order").order_by("-created_at")
    context = _context(
        request,
        page_title="Managed Domains",
        active_domain_nav="platform_domains_managed",
        managed_domains=domains,
    )
    return render(request, "account/domains/managed_domains.html", context)


@platform_staff_required
def renewals(request):
    renewals = ManagedDomainRenewal.objects.select_related("managed_domain__tenant", "order").order_by("-scheduled_for")
    context = _context(
        request,
        page_title="Renewals",
        active_domain_nav="platform_domains_renewals",
        renewals=renewals,
    )
    return render(request, "account/domains/renewals.html", context)


def _request_payload(request):
    if request.method == "GET":
        return request.GET.dict()
    if request.content_type and "json" in request.content_type.lower():
        try:
            import json

            return json.loads(request.body.decode("utf-8"))
        except Exception:
            return {}
    return request.POST.dict()


def _normalize_payment_status(value: str = "", event: str = "") -> str:
    normalized = (value or event or "").strip().lower()
    if normalized in {"success", "successful", "completed", "paid", "charge.success"}:
        return "success"
    if normalized in {"processing", "pending"}:
        return "processing"
    if normalized in {"cancelled", "canceled", "abandoned"}:
        return "cancelled"
    return "failed"


def _verify_and_record_domain_payment(order: DomainPurchaseOrder, provider: str, payload: dict, headers=None):
    with schema_context(order.payment_schema_name or order.tenant.schema_name):
        from dashboard.payments_tenant.models import PaymentIntent
        from dashboard.payments_tenant.services.intent_transactions import confirm_transaction
        from dashboard.payments_tenant.services.provider_checkout import verify_gateway_checkout

        intent = (
            PaymentIntent.objects.select_related(
                "payment_profile",
                "gateway_mode__gateway",
                "gateway_mode__platform_credential",
                "gateway_mode__direct_credential",
            )
            .filter(order_number=order.purchase_reference)
            .order_by("-created_at")
            .first()
        )
        if intent is None:
            return {
                "status_value": _normalize_payment_status(payload.get("status", ""), payload.get("event", "")),
                "gateway_reference": payload.get("reference", ""),
                "gateway_transaction_id": str(payload.get("id", "")),
                "metadata": {},
            }

        verification = verify_gateway_checkout(intent, payload, headers=dict(headers or {}))
        if not verification.success:
            raise ValueError(verification.error or "Payment verification failed.")

        status_value = verification.payment_status or _normalize_payment_status(payload.get("status", ""), payload.get("event", ""))
        gateway_reference = verification.gateway_reference or payload.get("reference", "")
        gateway_transaction_id = verification.gateway_transaction_id or str(payload.get("id", ""))
        confirm_transaction(
            payment_profile=intent.payment_profile,
            gateway_reference=gateway_reference,
            gateway_transaction_id=gateway_transaction_id,
            amount=verification.amount or intent.amount,
            currency=verification.currency or intent.currency,
            status="paid" if status_value == "success" else "failed",
            gateway_provider=provider,
            raw_response=verification.raw_response,
            gateway_message=verification.gateway_message,
            payment_channel=verification.payment_channel,
        )
        return {
            "status_value": status_value,
            "gateway_reference": gateway_reference,
            "gateway_transaction_id": gateway_transaction_id,
            "metadata": {"verified_response": verification.raw_response},
        }


@require_http_methods(["GET", "POST"])
def checkout_session(request, purchase_reference):
    order = get_object_or_404(DomainPurchaseOrder, purchase_reference=purchase_reference)
    provider_checkout_url = (order.payment_metadata or {}).get("provider_checkout_url", "")
    if request.method == "GET" and provider_checkout_url and order.status in {
        order.Status.AWAITING_PAYMENT,
        order.Status.PAID,
        order.Status.PROVISIONING,
    }:
        return redirect(provider_checkout_url)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "confirm":
            order = process_domain_payment_event(
                payment_status="success",
                purchase_reference=purchase_reference,
                gateway_reference=f"domain_{purchase_reference}",
                gateway_transaction_id=f"domain_tx_{purchase_reference}",
                metadata={"payment_surface": "domain_checkout_session"},
            )
            return redirect(order.success_redirect_url or "/")
        if action == "cancel":
            order = process_domain_payment_event(
                payment_status="cancelled",
                purchase_reference=purchase_reference,
                metadata={"payment_surface": "domain_checkout_session"},
            )
            return redirect(order.cancel_redirect_url or "/")

    return render(
        request,
        "account/domains/checkout_session.html",
        {
            "page_title": "Domain Checkout",
            "order": order,
        },
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def payment_callback(request, purchase_reference):
    order = get_object_or_404(DomainPurchaseOrder.objects.select_related("tenant"), purchase_reference=purchase_reference)
    payload = _request_payload(request)
    provider = order.gateway_provider or payload.get("provider", "")
    callback_metadata = {"callback_source": "platform_domains", "provider": provider, "payload": payload}
    try:
        verification_data = _verify_and_record_domain_payment(order, provider, payload, headers=request.headers)
        status_value = verification_data["status_value"]
        gateway_reference = verification_data["gateway_reference"]
        gateway_transaction_id = verification_data["gateway_transaction_id"]
        callback_metadata.update(verification_data["metadata"])
    except ValueError as exc:
        if request.method == "GET":
            messages.error(request, str(exc))
            return redirect(order.cancel_redirect_url or order.success_redirect_url or "/")
        return JsonResponse({"success": False, "message": str(exc), "purchase_reference": purchase_reference}, status=400)

    order = process_domain_payment_event(
        payment_status=status_value or "success",
        purchase_reference=purchase_reference,
        gateway_reference=gateway_reference,
        gateway_transaction_id=gateway_transaction_id,
        metadata=callback_metadata,
    )
    redirect_url = order.success_redirect_url if order.status == DomainPurchaseOrder.Status.ACTIVE else order.cancel_redirect_url
    if request.method == "GET" and redirect_url:
        return redirect(redirect_url)
    return JsonResponse(
        {
            "success": order.status in {DomainPurchaseOrder.Status.ACTIVE, DomainPurchaseOrder.Status.PAID, DomainPurchaseOrder.Status.PROVISIONING},
            "purchase_reference": order.purchase_reference,
            "status": order.status,
            "redirect_url": redirect_url,
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def payment_webhook(request, provider):
    payload = _request_payload(request)
    purchase_reference = payload.get("purchase_reference") or payload.get("reference") or payload.get("metadata", {}).get("purchase_reference", "")
    if not purchase_reference:
        return JsonResponse({"success": False, "message": "Purchase reference missing."}, status=400)
    order = get_object_or_404(DomainPurchaseOrder, purchase_reference=purchase_reference)
    try:
        verification_data = _verify_and_record_domain_payment(order, provider, payload, headers=request.headers)
    except ValueError as exc:
        return JsonResponse({"success": False, "message": str(exc)}, status=400)
    order = process_domain_payment_event(
        payment_status=verification_data["status_value"],
        purchase_reference=purchase_reference,
        gateway_reference=verification_data["gateway_reference"],
        gateway_transaction_id=verification_data["gateway_transaction_id"],
        metadata={"webhook_source": "platform_domains", "provider": provider, **verification_data["metadata"]},
    )
    return JsonResponse({"success": True, "purchase_reference": order.purchase_reference, "status": order.status})
