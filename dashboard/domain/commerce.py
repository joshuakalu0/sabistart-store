from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django_tenants.utils import schema_context

from dashboard.domain.commerce_models import (
    DomainActivityLog,
    DomainAvailabilityCache,
    DomainNotification,
    DomainProvider,
    DomainProviderCredential,
    DomainProvisioningAttempt,
    DomainPurchaseOrder,
    ManagedDomain,
    ManagedDomainDNSRecord,
    ManagedDomainRenewal,
    TenantDomainContact,
    TldCatalogEntry,
)
from dashboard.domain.domain_utils import normalize_domain_name
from dashboard.domain.models import CustomDomain
from dashboard.domain.providers import DomainContactPayload, ProviderDnsRecord, get_provider_adapter
from dashboard.domain.tasks import verify_domain_dns


DEFAULT_TLDS = (
    (".com", Decimal("15.99"), Decimal("18.99")),
    (".net", Decimal("16.99"), Decimal("19.99")),
    (".org", Decimal("14.99"), Decimal("16.99")),
    (".shop", Decimal("34.99"), Decimal("39.99")),
    (".store", Decimal("49.99"), Decimal("54.99")),
    (".co", Decimal("29.99"), Decimal("34.99")),
)


@dataclass
class DomainSearchBundle:
    query: str
    normalized_query: str
    exact_domain: str = ""
    results: list[DomainAvailabilityCache] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def build_domain_purchase_reference() -> str:
    return f"DM-{uuid.uuid4().hex[:12].upper()}"


def ensure_default_domain_catalog() -> tuple[DomainProvider, list[TldCatalogEntry]]:
    provider, _ = DomainProvider.objects.get_or_create(
        code="namecheap",
        defaults={
            "name": "Namecheap",
            "is_active": True,
            "is_default": True,
            "supports_availability": True,
            "supports_registration": True,
            "supports_renewal": True,
            "supports_dns": True,
            "supports_nameserver_update": True,
            "supports_contact_management": True,
            "supports_privacy": True,
            "docs_url": "https://www.namecheap.com/support/api/intro/",
            "display_order": 10,
        },
    )
    entries: list[TldCatalogEntry] = []
    for idx, (tld, registration_price, renewal_price) in enumerate(DEFAULT_TLDS, start=1):
        entry, _ = TldCatalogEntry.objects.get_or_create(
            provider=provider,
            tld=tld,
            defaults={
                "currency": "USD",
                "registration_price": registration_price,
                "renewal_price": renewal_price,
                "supports_registration": True,
                "supports_renewal": True,
                "supports_dns": True,
                "is_enabled": True,
                "sort_order": idx * 10,
            },
        )
        entries.append(entry)
    return provider, entries


def get_default_provider() -> DomainProvider:
    provider, _ = ensure_default_domain_catalog()
    return provider


def get_default_credential(provider: DomainProvider | None = None) -> DomainProviderCredential | None:
    provider = provider or get_default_provider()
    return (
        DomainProviderCredential.objects.filter(provider=provider, is_active=True)
        .order_by("-is_default", "environment", "name")
        .first()
    )


def get_provider_client(provider: DomainProvider | None = None, credential: DomainProviderCredential | None = None):
    provider = provider or get_default_provider()
    credential = credential or get_default_credential(provider)
    if credential is None:
        raise ValueError("No active registrar credential is configured.")
    adapter_cls = get_provider_adapter(provider.code)
    if adapter_cls is None:
        raise ValueError(f"No provider adapter is registered for {provider.code}.")
    return adapter_cls(credential)


def log_domain_activity(*, tenant, event_type: str, message: str, actor: str = "", managed_domain=None, custom_domain=None, purchase_order=None, metadata: dict | None = None):
    return DomainActivityLog.objects.create(
        tenant=tenant,
        managed_domain=managed_domain,
        custom_domain=custom_domain,
        purchase_order=purchase_order,
        event_type=event_type,
        actor=actor,
        message=message,
        metadata=metadata or {},
    )


def create_domain_notification(*, tenant, title: str, message: str, level: str = DomainNotification.Level.INFO, managed_domain=None, purchase_order=None, action_url: str = ""):
    return DomainNotification.objects.create(
        tenant=tenant,
        managed_domain=managed_domain,
        purchase_order=purchase_order,
        title=title,
        message=message,
        level=level,
        action_url=action_url,
    )


def get_contact_payload(contact: TenantDomainContact) -> DomainContactPayload:
    return DomainContactPayload(
        first_name=contact.first_name,
        last_name=contact.last_name,
        organization=contact.organization,
        email=contact.email,
        phone=contact.phone,
        address1=contact.address1,
        address2=contact.address2,
        city=contact.city,
        state_province=contact.state_province,
        postal_code=contact.postal_code,
        country_code=contact.country_code,
    )


def _candidate_domains(query: str) -> tuple[str, list[str]]:
    provider, tlds = ensure_default_domain_catalog()
    normalized = normalize_domain_name(query)
    entries = [entry for entry in tlds if entry.is_enabled]
    if "." in normalized:
        base = normalized.split(".")[0]
        variants = [normalized]
        variants.extend(f"{base}{entry.tld}" for entry in entries[:5] if f"{base}{entry.tld}" != normalized)
        return normalized, variants[:8]
    variants = [f"{normalized}{entry.tld}" for entry in entries[:8]]
    return normalized, variants


def search_domain_availability(query: str, *, refresh: bool = False) -> DomainSearchBundle:
    normalized, candidates = _candidate_domains(query)
    provider = get_default_provider()
    now = timezone.now()
    cached_map = {
        row.domain_name: row
        for row in DomainAvailabilityCache.objects.filter(
            provider=provider,
            domain_name__in=candidates,
            expires_at__gt=now,
        )
    }
    missing = [domain for domain in candidates if refresh or domain not in cached_map]
    results: list[DomainAvailabilityCache] = list(cached_map.values())
    errors: list[str] = []

    if missing:
        try:
            client = get_provider_client(provider=provider)
            provider_results = client.check_availability(missing)
            for item in provider_results:
                cache_row, _ = DomainAvailabilityCache.objects.update_or_create(
                    provider=provider,
                    domain_name=item.domain_name,
                    defaults={
                        "currency": item.currency,
                        "is_available": item.is_available,
                        "is_premium": item.is_premium,
                        "is_supported": item.is_supported,
                        "registration_price": item.registration_price,
                        "renewal_price": item.renewal_price,
                        "suggestion_score": item.suggestion_score,
                        "status_reason": item.status_reason,
                        "source_payload": item.raw_payload,
                        "checked_at": now,
                        "expires_at": now + timezone.timedelta(minutes=15),
                    },
                )
                results.append(cache_row)
        except Exception as exc:
            errors.append(str(exc))

    deduped = {item.domain_name: item for item in results}
    ordered = [deduped[name] for name in candidates if name in deduped]
    return DomainSearchBundle(
        query=query,
        normalized_query=normalized,
        exact_domain=ordered[0].domain_name if ordered else "",
        results=ordered,
        errors=errors,
    )


@transaction.atomic
def create_domain_purchase_order(
    *,
    tenant,
    domain_name: str,
    years: int,
    contact: TenantDomainContact,
    auto_renew: bool = True,
    privacy_enabled: bool = False,
    nameserver_mode: str = DomainPurchaseOrder.NameserverMode.PROVIDER_DEFAULT,
    custom_nameservers: list[str] | None = None,
    gateway_provider: str = "",
    initiated_by=None,
    order_type: str = DomainPurchaseOrder.OrderType.REGISTER,
    managed_domain: ManagedDomain | None = None,
):
    provider = get_default_provider()
    credential = get_default_credential(provider)
    if credential is None:
        raise ValueError("No active registrar credential is configured. Add one in the platform domain settings first.")

    search_bundle = search_domain_availability(domain_name)
    search_row = next((row for row in search_bundle.results if row.domain_name == normalize_domain_name(domain_name)), None)
    if order_type == DomainPurchaseOrder.OrderType.REGISTER:
        if search_row is None:
            raise ValueError("Domain availability could not be confirmed right now.")
        if not search_row.is_available:
            raise ValueError("That domain is not available for registration.")
        subtotal = (search_row.registration_price * years).quantize(Decimal("0.01"))
        currency = search_row.currency
    else:
        if managed_domain is None:
            raise ValueError("Renewal orders require an existing managed domain.")
        subtotal = (managed_domain.renewal_price * years).quantize(Decimal("0.01"))
        currency = managed_domain.currency

    purchase = DomainPurchaseOrder.objects.create(
        tenant=tenant,
        provider=provider,
        provider_credential=credential,
        contact=contact,
        managed_domain=managed_domain,
        purchase_reference=build_domain_purchase_reference(),
        order_type=order_type,
        status=DomainPurchaseOrder.Status.AWAITING_PAYMENT,
        domain_name=normalize_domain_name(domain_name),
        years=years,
        currency=currency,
        subtotal=subtotal,
        privacy_amount=Decimal("0.00"),
        total_amount=subtotal,
        auto_renew=auto_renew,
        privacy_enabled=privacy_enabled,
        nameserver_mode=nameserver_mode,
        custom_nameservers=custom_nameservers or [],
        payment_schema_name=getattr(tenant, "schema_name", ""),
        gateway_provider=gateway_provider,
        initiated_by_email=getattr(initiated_by, "email", "") or "",
        initiated_by_name=getattr(initiated_by, "get_full_name", lambda: "")() if initiated_by else "",
    )
    log_domain_activity(
        tenant=tenant,
        purchase_order=purchase,
        event_type="domain_order_created",
        actor="tenant",
        message=f"Domain order {purchase.purchase_reference} created for {purchase.domain_name}.",
        metadata={"order_type": order_type},
    )
    create_domain_notification(
        tenant=tenant,
        purchase_order=purchase,
        title="Domain order created",
        message=f"{purchase.domain_name} is ready for payment.",
        level=DomainNotification.Level.INFO,
    )
    return purchase


def initialize_domain_purchase_payment(*, purchase: DomainPurchaseOrder, initiated_by=None, customer_ip: str = "", callback_url: str = ""):
    from dashboard.payments_tenant.services.intent_transactions import create_payment_intent
    from dashboard.payments_tenant.models import TenantPaymentProfile
    from dashboard.payments_tenant.view_utils import bootstrap_payment_profile

    with schema_context(purchase.payment_schema_name or purchase.tenant.schema_name):
        profile = TenantPaymentProfile.objects.order_by("created_at").first()
        if profile is None:
            profile = TenantPaymentProfile.objects.create(
                account_status=TenantPaymentProfile.AccountStatus.ACTIVE,
                business_name=purchase.tenant.name,
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
            payment_method_type="managed_domain",
            metadata={
                "source": "domain_commerce",
                "purchase_reference": purchase.purchase_reference,
                "domain_name": purchase.domain_name,
                "order_type": purchase.order_type,
            },
            success_url=purchase.success_redirect_url,
            failure_url=purchase.cancel_redirect_url,
            cancel_url=purchase.cancel_redirect_url,
            callback_url=callback_url,
        )
    if not intent_result.success:
        raise ValueError("; ".join(intent_result.errors) or "Unable to initialize payment.")

    purchase.gateway_reference = intent_result.gateway_reference or purchase.gateway_reference
    purchase.payment_metadata = {
        **(purchase.payment_metadata or {}),
        "payment_intent_id": intent_result.intent_id,
        "authorization_url": intent_result.authorization_url,
        "provider_checkout_url": intent_result.authorization_url,
        "checkout_url": intent_result.authorization_url or reverse("platform_domains:checkout_session", kwargs={"purchase_reference": purchase.purchase_reference}),
    }
    purchase.save(update_fields=["gateway_reference", "payment_metadata", "updated_at"])
    return intent_result


def _create_or_update_managed_domain(order: DomainPurchaseOrder, result) -> ManagedDomain:
    managed_domain = order.managed_domain
    if managed_domain is None:
        managed_domain, _ = ManagedDomain.objects.update_or_create(
            domain_name=order.domain_name,
            defaults={
                "tenant": order.tenant,
                "provider": order.provider,
                "provider_credential": order.provider_credential,
                "contact": order.contact,
                "source_order": order,
                "status": ManagedDomain.Status.ACTIVE,
                "nameserver_mode": order.nameserver_mode,
                "current_nameservers": result.current_nameservers,
                "desired_nameservers": order.custom_nameservers if order.nameserver_mode == DomainPurchaseOrder.NameserverMode.CUSTOM else result.current_nameservers,
                "provider_domain_id": result.provider_domain_id,
                "provider_order_id": result.provider_order_id,
                "provider_status": result.provider_status,
                "auto_renew": order.auto_renew,
                "privacy_enabled": order.privacy_enabled,
                "registration_price": order.subtotal,
                "renewal_price": order.subtotal,
                "currency": order.currency,
                "is_premium": False,
                "registered_at": timezone.now(),
                "expires_at": result.expires_at,
                "last_synced_at": timezone.now(),
                "connection_status": ManagedDomain.ConnectionStatus.DETACHED,
                "metadata": result.raw_payload,
            },
        )
    else:
        managed_domain.provider_order_id = result.provider_order_id or managed_domain.provider_order_id
        managed_domain.provider_status = result.provider_status or managed_domain.provider_status
        managed_domain.current_nameservers = result.current_nameservers or managed_domain.current_nameservers
        managed_domain.expires_at = result.expires_at or managed_domain.expires_at
        managed_domain.status = ManagedDomain.Status.ACTIVE
        managed_domain.last_synced_at = timezone.now()
        managed_domain.last_error = ""
        managed_domain.save()
    return managed_domain


def _save_managed_domain_dns(managed_domain: ManagedDomain, records: Iterable[ProviderDnsRecord]):
    ManagedDomainDNSRecord.objects.filter(managed_domain=managed_domain).delete()
    for record in records:
        ManagedDomainDNSRecord.objects.create(
            managed_domain=managed_domain,
            host=record.host,
            record_type=record.record_type,
            value=record.value,
            ttl=record.ttl,
            priority=record.priority,
            provider_record_id=record.provider_record_id,
            last_synced_at=timezone.now(),
        )


def _schedule_renewal(managed_domain: ManagedDomain):
    if managed_domain.expires_at is None:
        return None
    scheduled_for = managed_domain.expires_at - timezone.timedelta(days=30)
    renewal, _ = ManagedDomainRenewal.objects.update_or_create(
        managed_domain=managed_domain,
        status=ManagedDomainRenewal.Status.SCHEDULED,
        defaults={
            "scheduled_for": scheduled_for,
            "years": 1,
            "amount": managed_domain.renewal_price,
            "currency": managed_domain.currency,
            "message": "Auto-scheduled from registration lifecycle.",
        },
    )
    return renewal


def provision_registration_order(order: DomainPurchaseOrder):
    if order.status == DomainPurchaseOrder.Status.ACTIVE and order.managed_domain_id:
        return order.managed_domain
    client = get_provider_client(order.provider, order.provider_credential)
    attempt = DomainProvisioningAttempt.objects.create(
        provider=order.provider,
        order=order,
        action=DomainProvisioningAttempt.Action.REGISTER,
        status=DomainProvisioningAttempt.Status.PENDING,
        request_payload={
            "domain_name": order.domain_name,
            "years": order.years,
            "nameserver_mode": order.nameserver_mode,
        },
    )
    order.status = DomainPurchaseOrder.Status.PROVISIONING
    order.save(update_fields=["status", "updated_at"])
    try:
        result = client.register_domain(
            domain_name=order.domain_name,
            years=order.years,
            contact=get_contact_payload(order.contact),
            privacy_enabled=order.privacy_enabled,
            nameserver_mode=order.nameserver_mode,
            custom_nameservers=order.custom_nameservers,
        )
        managed_domain = _create_or_update_managed_domain(order, result)
        order.managed_domain = managed_domain
        order.status = DomainPurchaseOrder.Status.ACTIVE
        order.completed_at = timezone.now()
        order.provider_order_id = result.provider_order_id or order.provider_order_id
        order.payment_metadata = {**(order.payment_metadata or {}), **(result.raw_payload or {})}
        order.error_message = ""
        order.save(
            update_fields=[
                "managed_domain",
                "status",
                "completed_at",
                "provider_order_id",
                "payment_metadata",
                "error_message",
                "updated_at",
            ]
        )
        attempt.status = DomainProvisioningAttempt.Status.SUCCESS
        attempt.message = result.message
        attempt.response_payload = result.raw_payload
        attempt.managed_domain = managed_domain
        attempt.save(update_fields=["status", "message", "response_payload", "managed_domain", "updated_at"])
        _schedule_renewal(managed_domain)
        log_domain_activity(
            tenant=order.tenant,
            purchase_order=order,
            managed_domain=managed_domain,
            event_type="domain_registration_completed",
            actor="system",
            message=f"{managed_domain.domain_name} was registered successfully.",
            metadata={"provider_order_id": result.provider_order_id},
        )
        create_domain_notification(
            tenant=order.tenant,
            managed_domain=managed_domain,
            purchase_order=order,
            title="Domain registration complete",
            message=f"{managed_domain.domain_name} is now in your portfolio and ready to connect.",
            level=DomainNotification.Level.SUCCESS,
        )
        return managed_domain
    except Exception as exc:
        order.status = DomainPurchaseOrder.Status.FAILED
        order.failed_at = timezone.now()
        order.error_message = str(exc)
        order.save(update_fields=["status", "failed_at", "error_message", "updated_at"])
        attempt.status = DomainProvisioningAttempt.Status.FAILED
        attempt.message = str(exc)
        attempt.save(update_fields=["status", "message", "updated_at"])
        log_domain_activity(
            tenant=order.tenant,
            purchase_order=order,
            event_type="domain_registration_failed",
            actor="system",
            message=f"Registration failed for {order.domain_name}: {exc}",
        )
        create_domain_notification(
            tenant=order.tenant,
            purchase_order=order,
            title="Domain registration failed",
            message=f"We received payment for {order.domain_name}, but provisioning failed. The order is ready for retry.",
            level=DomainNotification.Level.ERROR,
        )
        raise


def provision_renewal_order(order: DomainPurchaseOrder):
    if order.managed_domain is None:
        raise ValueError("Renewal order is missing its managed domain.")
    client = get_provider_client(order.provider, order.provider_credential)
    attempt = DomainProvisioningAttempt.objects.create(
        provider=order.provider,
        order=order,
        managed_domain=order.managed_domain,
        action=DomainProvisioningAttempt.Action.RENEW,
        status=DomainProvisioningAttempt.Status.PENDING,
        request_payload={"domain_name": order.domain_name, "years": order.years},
    )
    order.status = DomainPurchaseOrder.Status.PROVISIONING
    order.save(update_fields=["status", "updated_at"])
    try:
        result = client.renew_domain(domain_name=order.domain_name, years=order.years)
        managed_domain = order.managed_domain
        managed_domain.status = ManagedDomain.Status.ACTIVE
        managed_domain.expires_at = result.expires_at or managed_domain.expires_at
        managed_domain.last_synced_at = timezone.now()
        managed_domain.last_error = ""
        managed_domain.save(update_fields=["status", "expires_at", "last_synced_at", "last_error", "updated_at"])
        order.status = DomainPurchaseOrder.Status.ACTIVE
        order.completed_at = timezone.now()
        order.error_message = ""
        order.provider_order_id = result.provider_order_id or order.provider_order_id
        order.save(update_fields=["status", "completed_at", "error_message", "provider_order_id", "updated_at"])
        ManagedDomainRenewal.objects.create(
            managed_domain=managed_domain,
            order=order,
            scheduled_for=timezone.now(),
            executed_at=timezone.now(),
            years=order.years,
            amount=order.total_amount,
            currency=order.currency,
            status=ManagedDomainRenewal.Status.COMPLETED,
            message=result.message,
        )
        attempt.status = DomainProvisioningAttempt.Status.SUCCESS
        attempt.message = result.message
        attempt.response_payload = result.raw_payload
        attempt.save(update_fields=["status", "message", "response_payload", "updated_at"])
        _schedule_renewal(managed_domain)
        log_domain_activity(
            tenant=order.tenant,
            purchase_order=order,
            managed_domain=managed_domain,
            event_type="domain_renewal_completed",
            actor="system",
            message=f"{managed_domain.domain_name} renewed successfully.",
        )
        create_domain_notification(
            tenant=order.tenant,
            managed_domain=managed_domain,
            purchase_order=order,
            title="Domain renewed",
            message=f"{managed_domain.domain_name} has been renewed successfully.",
            level=DomainNotification.Level.SUCCESS,
        )
        return managed_domain
    except Exception as exc:
        order.status = DomainPurchaseOrder.Status.FAILED
        order.failed_at = timezone.now()
        order.error_message = str(exc)
        order.save(update_fields=["status", "failed_at", "error_message", "updated_at"])
        attempt.status = DomainProvisioningAttempt.Status.FAILED
        attempt.message = str(exc)
        attempt.save(update_fields=["status", "message", "updated_at"])
        ManagedDomainRenewal.objects.create(
            managed_domain=order.managed_domain,
            order=order,
            scheduled_for=timezone.now(),
            years=order.years,
            amount=order.total_amount,
            currency=order.currency,
            status=ManagedDomainRenewal.Status.FAILED,
            message=str(exc),
        )
        raise


def process_domain_payment_event(
    *,
    payment_status: str,
    purchase_reference: str,
    gateway_reference: str = "",
    gateway_transaction_id: str = "",
    metadata: dict | None = None,
):
    order = DomainPurchaseOrder.objects.select_related("tenant", "provider", "provider_credential", "contact", "managed_domain").get(
        purchase_reference=purchase_reference
    )
    normalized = (payment_status or "").strip().lower()
    merged_metadata = {**(order.payment_metadata or {}), **(metadata or {})}
    if normalized in {"success", "successful", "completed", "paid"}:
        if order.status == DomainPurchaseOrder.Status.ACTIVE:
            return order
        order.status = DomainPurchaseOrder.Status.PAID
        order.paid_at = timezone.now()
        order.gateway_reference = gateway_reference or order.gateway_reference
        order.gateway_transaction_id = gateway_transaction_id or order.gateway_transaction_id
        order.payment_metadata = merged_metadata
        order.save(update_fields=["status", "paid_at", "gateway_reference", "gateway_transaction_id", "payment_metadata", "updated_at"])
        if order.order_type == DomainPurchaseOrder.OrderType.REGISTER:
            provision_registration_order(order)
        else:
            provision_renewal_order(order)
        return order
    if normalized in {"processing", "pending"}:
        order.status = DomainPurchaseOrder.Status.PAID
        order.gateway_reference = gateway_reference or order.gateway_reference
        order.gateway_transaction_id = gateway_transaction_id or order.gateway_transaction_id
        order.payment_metadata = merged_metadata
        order.save(update_fields=["status", "gateway_reference", "gateway_transaction_id", "payment_metadata", "updated_at"])
        return order
    if normalized in {"cancel", "cancelled", "canceled", "abandoned"}:
        order.status = DomainPurchaseOrder.Status.CANCELLED
        order.cancelled_at = timezone.now()
        order.payment_metadata = merged_metadata
        order.save(update_fields=["status", "cancelled_at", "payment_metadata", "updated_at"])
        return order
    order.status = DomainPurchaseOrder.Status.FAILED
    order.failed_at = timezone.now()
    order.gateway_reference = gateway_reference or order.gateway_reference
    order.gateway_transaction_id = gateway_transaction_id or order.gateway_transaction_id
    order.payment_metadata = merged_metadata
    order.save(update_fields=["status", "failed_at", "gateway_reference", "gateway_transaction_id", "payment_metadata", "updated_at"])
    return order


def generate_required_dns_records(custom_domain: CustomDomain) -> list[ProviderDnsRecord]:
    return [
        ProviderDnsRecord(
            host=record.host,
            record_type=record.record_type,
            value=record.value,
            ttl=record.ttl,
            priority=10,
        )
        for record in custom_domain.dns_records.order_by("purpose", "record_type", "host")
    ]


@transaction.atomic
def connect_managed_domain_to_storefront(*, managed_domain: ManagedDomain, make_primary: bool = False, use_provider_dns: bool = False):
    custom_domain = getattr(managed_domain, "custom_connection", None)
    if custom_domain is None:
        custom_domain = CustomDomain.objects.create(
            tenant=managed_domain.tenant,
            domain=managed_domain.domain_name,
            is_primary=make_primary or not managed_domain.tenant.custom_domains.exclude(status=CustomDomain.Status.REMOVED).exists(),
            status=CustomDomain.Status.PENDING,
            notes="Connected from managed domain portfolio.",
            managed_domain=managed_domain,
            connection_source="managed",
        )
    else:
        custom_domain.managed_domain = managed_domain
        custom_domain.connection_source = "managed"
        if make_primary:
            custom_domain.is_primary = True
        custom_domain.save(update_fields=["managed_domain", "connection_source", "is_primary", "updated_at"])

    managed_domain.connection_status = ManagedDomain.ConnectionStatus.PENDING
    managed_domain.connected_at = timezone.now()
    managed_domain.save(update_fields=["connection_status", "connected_at", "updated_at"])

    if use_provider_dns and managed_domain.provider.supports_dns:
        records = generate_required_dns_records(custom_domain)
        set_provider_dns_records(managed_domain, records)

    verify_domain_dns.delay(str(custom_domain.id))
    log_domain_activity(
        tenant=managed_domain.tenant,
        managed_domain=managed_domain,
        custom_domain=custom_domain,
        event_type="managed_domain_connected",
        actor="tenant",
        message=f"{managed_domain.domain_name} connected to the storefront.",
        metadata={"custom_domain_id": str(custom_domain.id)},
    )
    create_domain_notification(
        tenant=managed_domain.tenant,
        managed_domain=managed_domain,
        title="Domain connection started",
        message=f"We started verification for {managed_domain.domain_name}.",
        level=DomainNotification.Level.INFO,
        action_url=reverse("dashboard:domain:detail", kwargs={"prefix": "admin", "domain_id": custom_domain.id}),
    )
    return custom_domain


def sync_managed_domain(managed_domain: ManagedDomain):
    client = get_provider_client(managed_domain.provider, managed_domain.provider_credential)
    attempt = DomainProvisioningAttempt.objects.create(
        provider=managed_domain.provider,
        managed_domain=managed_domain,
        action=DomainProvisioningAttempt.Action.SYNC,
        status=DomainProvisioningAttempt.Status.PENDING,
        request_payload={"domain_name": managed_domain.domain_name},
    )
    try:
        result = client.get_domain_info(managed_domain.domain_name)
        managed_domain.current_nameservers = result.current_nameservers or managed_domain.current_nameservers
        managed_domain.provider_status = result.provider_status or managed_domain.provider_status
        managed_domain.expires_at = result.expires_at or managed_domain.expires_at
        managed_domain.last_synced_at = timezone.now()
        managed_domain.last_error = ""
        if managed_domain.expires_at and managed_domain.expires_at <= timezone.now() + timezone.timedelta(days=30):
            managed_domain.status = ManagedDomain.Status.EXPIRING
        elif managed_domain.status in {ManagedDomain.Status.EXPIRING, ManagedDomain.Status.RENEWAL_DUE, ManagedDomain.Status.FAILED}:
            managed_domain.status = ManagedDomain.Status.ACTIVE
        managed_domain.save(
            update_fields=[
                "current_nameservers",
                "provider_status",
                "expires_at",
                "last_synced_at",
                "last_error",
                "status",
                "updated_at",
            ]
        )
        attempt.status = DomainProvisioningAttempt.Status.SUCCESS
        attempt.message = result.message
        attempt.response_payload = result.raw_payload
        attempt.save(update_fields=["status", "message", "response_payload", "updated_at"])
        return managed_domain
    except Exception as exc:
        managed_domain.last_error = str(exc)
        managed_domain.save(update_fields=["last_error", "updated_at"])
        attempt.status = DomainProvisioningAttempt.Status.FAILED
        attempt.message = str(exc)
        attempt.save(update_fields=["status", "message", "updated_at"])
        raise


def pull_provider_dns_records(managed_domain: ManagedDomain):
    client = get_provider_client(managed_domain.provider, managed_domain.provider_credential)
    result = client.get_dns_records(managed_domain.domain_name)
    _save_managed_domain_dns(managed_domain, result.dns_records)
    return result


def set_provider_dns_records(managed_domain: ManagedDomain, records: list[ProviderDnsRecord]):
    client = get_provider_client(managed_domain.provider, managed_domain.provider_credential)
    result = client.set_dns_records(domain_name=managed_domain.domain_name, records=records)
    _save_managed_domain_dns(managed_domain, records)
    return result


def update_managed_domain_nameservers(managed_domain: ManagedDomain, nameservers: list[str]):
    client = get_provider_client(managed_domain.provider, managed_domain.provider_credential)
    result = client.set_nameservers(domain_name=managed_domain.domain_name, nameservers=nameservers)
    managed_domain.current_nameservers = nameservers
    managed_domain.desired_nameservers = nameservers
    managed_domain.nameserver_mode = ManagedDomain.NameserverMode.CUSTOM if nameservers else ManagedDomain.NameserverMode.PROVIDER_DEFAULT
    managed_domain.last_synced_at = timezone.now()
    managed_domain.save(
        update_fields=["current_nameservers", "desired_nameservers", "nameserver_mode", "last_synced_at", "updated_at"]
    )
    return result


def process_paid_domain_orders(limit: int = 25) -> int:
    processed = 0
    orders = DomainPurchaseOrder.objects.select_related(
        "tenant", "provider", "provider_credential", "contact", "managed_domain"
    ).filter(status=DomainPurchaseOrder.Status.PAID).order_by("created_at")[:limit]
    for order in orders:
        if order.order_type == DomainPurchaseOrder.OrderType.REGISTER:
            provision_registration_order(order)
        else:
            provision_renewal_order(order)
        processed += 1
    return processed


def process_due_domain_renewals(limit: int = 25) -> int:
    processed = 0
    due = ManagedDomainRenewal.objects.select_related("managed_domain__tenant", "managed_domain__provider", "managed_domain__provider_credential", "managed_domain__contact").filter(
        status=ManagedDomainRenewal.Status.SCHEDULED,
        scheduled_for__lte=timezone.now(),
    ).order_by("scheduled_for")[:limit]
    for renewal in due:
        managed_domain = renewal.managed_domain
        order = create_domain_purchase_order(
            tenant=managed_domain.tenant,
            domain_name=managed_domain.domain_name,
            years=renewal.years,
            contact=managed_domain.contact,
            auto_renew=managed_domain.auto_renew,
            privacy_enabled=managed_domain.privacy_enabled,
            nameserver_mode=managed_domain.nameserver_mode,
            custom_nameservers=managed_domain.current_nameservers,
            gateway_provider="manual",
            initiated_by=None,
            order_type=DomainPurchaseOrder.OrderType.RENEW,
            managed_domain=managed_domain,
        )
        order.status = DomainPurchaseOrder.Status.PAID
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "paid_at", "updated_at"])
        provision_renewal_order(order)
        renewal.status = ManagedDomainRenewal.Status.PROCESSING
        renewal.executed_at = timezone.now()
        renewal.order = order
        renewal.save(update_fields=["status", "executed_at", "order", "updated_at"])
        processed += 1
    return processed


def reconcile_managed_domain_integrity() -> dict:
    fixed_connections = 0
    synced = 0
    for managed_domain in ManagedDomain.objects.select_related("tenant", "provider", "provider_credential").all():
        custom_domain = getattr(managed_domain, "custom_connection", None)
        if custom_domain and custom_domain.managed_domain_id != managed_domain.id:
            custom_domain.managed_domain = managed_domain
            custom_domain.connection_source = "managed"
            custom_domain.save(update_fields=["managed_domain", "connection_source", "updated_at"])
            fixed_connections += 1
        if managed_domain.status in {ManagedDomain.Status.ACTIVE, ManagedDomain.Status.EXPIRING, ManagedDomain.Status.RENEWAL_DUE}:
            try:
                sync_managed_domain(managed_domain)
                synced += 1
            except Exception:
                continue
    return {"fixed_connections": fixed_connections, "synced": synced}
