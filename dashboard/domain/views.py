from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from dashboard.decorators import dashboard_prefix_required
from dashboard.domain.commerce import (
    connect_managed_domain_to_storefront,
    create_domain_purchase_order,
    ensure_default_domain_catalog,
    initialize_domain_purchase_payment,
    pull_provider_dns_records,
    search_domain_availability,
    set_provider_dns_records,
    update_managed_domain_nameservers,
)
from dashboard.domain.forms import (
    AddDomainForm,
    DomainCheckoutForm,
    DomainOrderFilterForm,
    DomainSearchForm,
    DomainSettingsForm,
    ManagedDomainDNSRecordForm,
    NameserverUpdateForm,
    TenantDomainContactForm,
)
from dashboard.domain.models import (
    ACMEChallenge,
    CustomDomain,
    DomainActivityLog,
    DomainNotification,
    DomainPurchaseOrder,
    ManagedDomain,
    ManagedDomainDNSRecord,
    TenantDomainContact,
)
from dashboard.domain.providers import ProviderDnsRecord
from dashboard.domain.tasks import verify_domain_dns
from dashboard.domain.view_utils import build_page_context, get_domain_quota, get_tenant_domains
from system.feature_marketplace.services import get_marketplace_gateways


def _tenant_domain_or_404(request, domain_id):
    domain = get_object_or_404(CustomDomain, id=domain_id)
    if domain.tenant_id != request.tenant.id:
        raise Http404("Domain not found")
    return domain


def _tenant_managed_domain_or_404(request, managed_domain_id):
    managed_domain = get_object_or_404(ManagedDomain, id=managed_domain_id)
    if managed_domain.tenant_id != request.tenant.id:
        raise Http404("Managed domain not found")
    return managed_domain


def _tenant_order_or_404(request, purchase_reference):
    order = get_object_or_404(DomainPurchaseOrder.objects.select_related("managed_domain"), purchase_reference=purchase_reference)
    if order.tenant_id != request.tenant.id:
        raise Http404("Order not found")
    return order


def _build_summary_context(request, prefix, active_menu="domains_list", **extra):
    quota = get_domain_quota(request.tenant)
    managed_domains = ManagedDomain.objects.filter(tenant=request.tenant).order_by("-created_at")
    notification_qs = DomainNotification.objects.filter(tenant=request.tenant).order_by("-created_at")
    notifications = notification_qs[:6]
    orders = DomainPurchaseOrder.objects.filter(tenant=request.tenant).order_by("-created_at")[:8]
    context = build_page_context(
        prefix,
        "Domains & SSL",
        active_menu,
        quota=quota,
        domains=get_tenant_domains(request.tenant),
        managed_domains=managed_domains[:5],
        order_count=orders.count(),
        managed_count=managed_domains.count(),
        unread_notification_count=notification_qs.filter(is_read=False).count(),
        recent_orders=orders,
        notifications=notifications,
        active_count=ManagedDomain.objects.filter(tenant=request.tenant, status=ManagedDomain.Status.ACTIVE).count(),
        expiring_count=ManagedDomain.objects.filter(tenant=request.tenant, status=ManagedDomain.Status.EXPIRING).count(),
        pending_count=CustomDomain.objects.filter(
            tenant=request.tenant,
            status__in=[
                CustomDomain.Status.PENDING,
                CustomDomain.Status.DNS_CHECKING,
                CustomDomain.Status.DNS_VERIFIED,
                CustomDomain.Status.SSL_PENDING,
            ],
        ).count(),
        failed_count=CustomDomain.objects.filter(tenant=request.tenant, status=CustomDomain.Status.FAILED).count(),
        connected_count=CustomDomain.objects.filter(tenant=request.tenant).exclude(status=CustomDomain.Status.REMOVED).count(),
    )
    context.update(extra)
    return context


def _inline_contact_from_checkout(request, form: DomainCheckoutForm):
    if form.cleaned_data.get("contact") is not None:
        return form.cleaned_data["contact"]
    contact = TenantDomainContact.objects.create(
        tenant=request.tenant,
        label="Checkout contact",
        first_name=form.cleaned_data["first_name"],
        last_name=form.cleaned_data["last_name"],
        organization=form.cleaned_data.get("organization", ""),
        email=form.cleaned_data["email"],
        phone=form.cleaned_data["phone"],
        address1=form.cleaned_data["address1"],
        address2=form.cleaned_data.get("address2", ""),
        city=form.cleaned_data["city"],
        state_province=form.cleaned_data["state_province"],
        postal_code=form.cleaned_data["postal_code"],
        country_code=form.cleaned_data["country_code"].upper(),
        is_default=form.cleaned_data.get("save_contact_as_default", True),
    )
    if contact.is_default:
        TenantDomainContact.objects.filter(tenant=request.tenant).exclude(pk=contact.pk).update(is_default=False)
    return contact


def _bind_gateway_choices(form, currency="USD"):
    gateways = get_marketplace_gateways(currency)
    choices = [("", "Select a payment gateway")]
    choices.extend((gateway["provider"], gateway["name"]) for gateway in gateways)
    form.fields["gateway_provider"].choices = choices
    if len(choices) == 2 and not form.initial.get("gateway_provider"):
        form.initial["gateway_provider"] = choices[1][0]
        form.fields["gateway_provider"].initial = choices[1][0]
    return gateways


@login_required
@dashboard_prefix_required
def domain_list(request, prefix):
    provider, tlds = ensure_default_domain_catalog()
    search_form = DomainSearchForm(request.GET or None)
    add_form = AddDomainForm()
    search_bundle = None
    if search_form.is_valid():
        search_bundle = search_domain_availability(search_form.cleaned_data["query"])
        for error in search_bundle.errors:
            messages.warning(request, error)
    context = _build_summary_context(
        request,
        prefix,
        "domains_list",
        provider=provider,
        search_form=search_form,
        add_form=add_form,
        featured_tlds=tlds[:6],
        search_bundle=search_bundle,
        existing_domains=get_tenant_domains(request.tenant),
    )
    return render(request, "dashboard/domain/domain_list.html", context)


@login_required
@dashboard_prefix_required
@require_http_methods(["POST"])
def domain_add(request, prefix):
    quota = get_domain_quota(request.tenant)
    if not quota.has_capacity:
        messages.error(
            request,
            f"You have reached your external custom domain limit of {quota.max_custom_domains}. Buy a domain here or increase your slots in the marketplace.",
        )
        return redirect("dashboard:domain:list", prefix=prefix)

    form = AddDomainForm(request.POST)
    if not form.is_valid():
        context = _build_summary_context(
            request,
            prefix,
            "domains_list",
            add_form=form,
            search_form=DomainSearchForm(),
            featured_tlds=ensure_default_domain_catalog()[1][:6],
        )
        return render(request, "dashboard/domain/domain_list.html", context, status=400)

    is_primary = not get_tenant_domains(request.tenant).exists()
    custom_domain = CustomDomain.objects.create(
        tenant=request.tenant,
        domain=form.cleaned_data["domain"],
        is_primary=is_primary,
        status=CustomDomain.Status.PENDING,
        notes="Added from dashboard.",
        connection_source="manual",
    )
    verify_domain_dns.delay(str(custom_domain.id))
    messages.success(request, f"{custom_domain.domain} added. DNS verification has started.")
    return redirect("dashboard:domain:detail", prefix=prefix, domain_id=custom_domain.id)


@login_required
@dashboard_prefix_required
def domain_checkout(request, prefix):
    domain_name = request.GET.get("domain") or request.POST.get("domain_name", "")
    search_bundle = search_domain_availability(domain_name) if domain_name else None
    result_row = None
    if search_bundle:
        normalized = domain_name.strip().lower()
        result_row = next((row for row in search_bundle.results if row.domain_name == normalized), None)
        if result_row is None and search_bundle.results:
            result_row = search_bundle.results[0]
            domain_name = result_row.domain_name
    form = DomainCheckoutForm(request.POST or None, tenant=request.tenant, initial={"domain_name": domain_name})
    gateways = _bind_gateway_choices(form, currency=result_row.currency if result_row else "USD")
    if request.method == "POST" and form.is_valid():
        try:
            contact = _inline_contact_from_checkout(request, form)
            purchase = create_domain_purchase_order(
                tenant=request.tenant,
                domain_name=form.cleaned_data["domain_name"],
                years=form.cleaned_data["years"],
                contact=contact,
                auto_renew=form.cleaned_data["auto_renew"],
                privacy_enabled=form.cleaned_data["privacy_enabled"],
                nameserver_mode=form.cleaned_data["nameserver_mode"],
                custom_nameservers=form.cleaned_data["custom_nameservers"],
                gateway_provider=form.cleaned_data.get("gateway_provider", ""),
                initiated_by=request.user,
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
            purchase = None
        if purchase is None:
            context = _build_summary_context(
                request,
                prefix,
                "domains_search",
                checkout_form=form,
                search_bundle=search_bundle,
                search_result=result_row,
                gateway_options=gateways,
                page_title="Buy a Domain",
            )
            return render(request, "dashboard/domain/domain_checkout.html", context, status=400)
        purchase.success_redirect_url = request.build_absolute_uri(
            reverse("dashboard:domain:order_detail", kwargs={"prefix": prefix, "purchase_reference": purchase.purchase_reference})
        )
        purchase.cancel_redirect_url = request.build_absolute_uri(
            reverse("dashboard:domain:order_detail", kwargs={"prefix": prefix, "purchase_reference": purchase.purchase_reference})
        )
        purchase.save(update_fields=["success_redirect_url", "cancel_redirect_url", "updated_at"])
        callback_url = request.build_absolute_uri(
            reverse("platform_domains:payment_callback", kwargs={"purchase_reference": purchase.purchase_reference})
        )
        intent_result = initialize_domain_purchase_payment(
            purchase=purchase,
            initiated_by=request.user,
            customer_ip=request.META.get("REMOTE_ADDR", ""),
            callback_url=callback_url,
        )
        hosted_url = intent_result.authorization_url or purchase.payment_metadata.get("provider_checkout_url", "")
        if hosted_url:
            messages.success(request, "Domain order created. Redirecting you to payment.")
            return redirect(hosted_url)
        return redirect("platform_domains:checkout_session", purchase_reference=purchase.purchase_reference)

    context = _build_summary_context(
        request,
        prefix,
        "domains_search",
        checkout_form=form,
        search_bundle=search_bundle,
        search_result=result_row,
        gateway_options=gateways,
        page_title="Buy a Domain",
    )
    return render(request, "dashboard/domain/domain_checkout.html", context)


@login_required
@dashboard_prefix_required
def domain_portfolio(request, prefix):
    managed_domains = ManagedDomain.objects.filter(tenant=request.tenant).order_by("-created_at")
    context = _build_summary_context(
        request,
        prefix,
        "domains_portfolio",
        portfolio=managed_domains,
    )
    return render(request, "dashboard/domain/domain_portfolio.html", context)


@login_required
@dashboard_prefix_required
def managed_domain_detail(request, prefix, managed_domain_id):
    managed_domain = _tenant_managed_domain_or_404(request, managed_domain_id)
    linked_custom = getattr(managed_domain, "custom_connection", None)
    dns_form = ManagedDomainDNSRecordForm()
    nameserver_form = NameserverUpdateForm(initial={"nameservers": "\n".join(managed_domain.current_nameservers)})
    renewal_gateways = get_marketplace_gateways(managed_domain.currency)
    context = _build_summary_context(
        request,
        prefix,
        "domains_portfolio",
        managed_domain=managed_domain,
        linked_custom_domain=linked_custom,
        orders=managed_domain.orders.order_by("-created_at"),
        activity=managed_domain.activity.order_by("-created_at")[:20],
        renewal_events=managed_domain.renewal_events.order_by("-scheduled_for")[:20],
        dns_records=managed_domain.dns_records.order_by("host", "record_type"),
        dns_form=dns_form,
        nameserver_form=nameserver_form,
        renewal_gateways=renewal_gateways,
    )
    return render(request, "dashboard/domain/managed_domain_detail.html", context)


@login_required
@dashboard_prefix_required
@require_POST
def managed_domain_connect(request, prefix, managed_domain_id):
    managed_domain = _tenant_managed_domain_or_404(request, managed_domain_id)
    use_provider_dns = request.POST.get("use_provider_dns") == "1"
    make_primary = request.POST.get("make_primary") == "1"
    custom_domain = connect_managed_domain_to_storefront(
        managed_domain=managed_domain,
        make_primary=make_primary,
        use_provider_dns=use_provider_dns,
    )
    messages.success(request, f"{managed_domain.domain_name} is now being connected to your storefront.")
    return redirect("dashboard:domain:detail", prefix=prefix, domain_id=custom_domain.id)


@login_required
@dashboard_prefix_required
@require_http_methods(["GET", "POST"])
def managed_domain_dns(request, prefix, managed_domain_id):
    managed_domain = _tenant_managed_domain_or_404(request, managed_domain_id)
    if request.method == "POST" and "save_nameservers" in request.POST:
        nameserver_form = NameserverUpdateForm(request.POST)
        if nameserver_form.is_valid():
            update_managed_domain_nameservers(managed_domain, nameserver_form.cleaned_data["nameservers"])
            messages.success(request, "Nameservers updated.")
            return redirect("dashboard:domain:managed_detail", prefix=prefix, managed_domain_id=managed_domain.id)
    elif request.method == "POST" and "add_dns_record" in request.POST:
        dns_form = ManagedDomainDNSRecordForm(request.POST)
        if dns_form.is_valid():
            record = dns_form.save(commit=False)
            record.managed_domain = managed_domain
            record.save()
            provider_records = [
                ProviderDnsRecord(
                    host=item.host,
                    record_type=item.record_type,
                    value=item.value,
                    ttl=item.ttl,
                    priority=item.priority,
                    provider_record_id=item.provider_record_id,
                )
                for item in managed_domain.dns_records.order_by("host", "record_type")
            ]
            set_provider_dns_records(managed_domain, provider_records)
            messages.success(request, "DNS records synced to the provider.")
            return redirect("dashboard:domain:managed_detail", prefix=prefix, managed_domain_id=managed_domain.id)
    try:
        pull_provider_dns_records(managed_domain)
    except Exception as exc:
        messages.warning(request, str(exc))
    return redirect("dashboard:domain:managed_detail", prefix=prefix, managed_domain_id=managed_domain.id)


@login_required
@dashboard_prefix_required
def domain_orders(request, prefix):
    form = DomainOrderFilterForm(request.GET or None)
    orders = DomainPurchaseOrder.objects.filter(tenant=request.tenant).select_related("managed_domain").order_by("-created_at")
    if form.is_valid():
        if form.cleaned_data.get("status"):
            orders = orders.filter(status=form.cleaned_data["status"])
        if form.cleaned_data.get("order_type"):
            orders = orders.filter(order_type=form.cleaned_data["order_type"])
    context = _build_summary_context(
        request,
        prefix,
        "domains_orders",
        order_filter_form=form,
        orders=orders,
    )
    return render(request, "dashboard/domain/domain_orders.html", context)


@login_required
@dashboard_prefix_required
def domain_order_detail(request, prefix, purchase_reference):
    order = _tenant_order_or_404(request, purchase_reference)
    context = _build_summary_context(
        request,
        prefix,
        "domains_orders",
        order=order,
        activity=order.activity.order_by("-created_at"),
        notifications=order.notifications.order_by("-created_at"),
    )
    return render(request, "dashboard/domain/domain_order_detail.html", context)


@login_required
@dashboard_prefix_required
@require_POST
def managed_domain_renew(request, prefix, managed_domain_id):
    managed_domain = _tenant_managed_domain_or_404(request, managed_domain_id)
    contact = managed_domain.contact or request.tenant.domain_contacts.order_by("-is_default", "created_at").first()
    if contact is None:
        messages.error(request, "Create a registrant contact before starting a renewal.")
        return redirect("dashboard:domain:contacts", prefix=prefix)
    try:
        order = create_domain_purchase_order(
            tenant=request.tenant,
            domain_name=managed_domain.domain_name,
            years=int(request.POST.get("years", "1") or 1),
            contact=contact,
            auto_renew=managed_domain.auto_renew,
            privacy_enabled=managed_domain.privacy_enabled,
            nameserver_mode=managed_domain.nameserver_mode,
            custom_nameservers=managed_domain.current_nameservers,
            gateway_provider=request.POST.get("gateway_provider", ""),
            initiated_by=request.user,
            order_type=DomainPurchaseOrder.OrderType.RENEW,
            managed_domain=managed_domain,
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("dashboard:domain:managed_detail", prefix=prefix, managed_domain_id=managed_domain.id)
    order.success_redirect_url = request.build_absolute_uri(
        reverse("dashboard:domain:order_detail", kwargs={"prefix": prefix, "purchase_reference": order.purchase_reference})
    )
    order.cancel_redirect_url = order.success_redirect_url
    order.save(update_fields=["success_redirect_url", "cancel_redirect_url", "updated_at"])
    callback_url = request.build_absolute_uri(
        reverse("platform_domains:payment_callback", kwargs={"purchase_reference": order.purchase_reference})
    )
    intent_result = initialize_domain_purchase_payment(
        purchase=order,
        initiated_by=request.user,
        customer_ip=request.META.get("REMOTE_ADDR", ""),
        callback_url=callback_url,
    )
    if intent_result.authorization_url:
        return redirect(intent_result.authorization_url)
    return redirect("platform_domains:checkout_session", purchase_reference=order.purchase_reference)


@login_required
@dashboard_prefix_required
def domain_contacts(request, prefix):
    form = TenantDomainContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        contact = form.save(commit=False)
        contact.tenant = request.tenant
        contact.save()
        if contact.is_default:
            TenantDomainContact.objects.filter(tenant=request.tenant).exclude(pk=contact.pk).update(is_default=False)
        messages.success(request, "Registrant contact saved.")
        return redirect("dashboard:domain:contacts", prefix=prefix)
    context = _build_summary_context(
        request,
        prefix,
        "domains_contacts",
        contact_form=form,
        contacts=request.tenant.domain_contacts.order_by("-is_default", "first_name", "last_name"),
    )
    return render(request, "dashboard/domain/domain_contacts.html", context)


@login_required
@dashboard_prefix_required
def domain_notifications(request, prefix):
    notifications = DomainNotification.objects.filter(tenant=request.tenant).order_by("-created_at")
    context = _build_summary_context(
        request,
        prefix,
        "domains_notifications",
        notifications_page=notifications,
    )
    return render(request, "dashboard/domain/domain_notifications.html", context)


@login_required
@dashboard_prefix_required
@require_POST
def domain_notification_read(request, prefix, notification_id):
    notification = get_object_or_404(DomainNotification, pk=notification_id, tenant=request.tenant)
    notification.is_read = True
    notification.read_at = timezone.now()
    notification.save(update_fields=["is_read", "read_at", "updated_at"])
    return redirect(request.POST.get("next") or reverse("dashboard:domain:notifications", kwargs={"prefix": prefix}))


@login_required
@dashboard_prefix_required
def domain_detail(request, prefix, domain_id):
    custom_domain = _tenant_domain_or_404(request, domain_id)
    if request.method == "POST":
        form = DomainSettingsForm(request.POST, instance=custom_domain)
        if form.is_valid():
            updated_domain = form.save()
            if updated_domain.is_primary:
                messages.success(request, "Domain marked as primary.")
            else:
                messages.success(request, "Domain settings updated.")
            return redirect("dashboard:domain:detail", prefix=prefix, domain_id=custom_domain.id)
    else:
        form = DomainSettingsForm(instance=custom_domain)

    context = _build_summary_context(
        request,
        prefix,
        "domains_list",
        domain=custom_domain,
        settings_form=form,
        dns_records=custom_domain.dns_records.order_by("purpose", "record_type", "host"),
        verification_attempts=custom_domain.verification_attempts.order_by("-attempted_at")[:10],
        events=custom_domain.events.order_by("-created_at")[:20],
        health_checks=custom_domain.health_checks.order_by("-checked_at")[:10],
        certificate=getattr(custom_domain, "certificate", None),
        redirect_rules=custom_domain.incoming_redirects.order_by("-created_at"),
        managed_domain=getattr(custom_domain, "managed_domain", None),
    )
    return render(request, "dashboard/domain/domain_detail.html", context)


@login_required
@dashboard_prefix_required
@require_POST
def domain_delete(request, prefix, domain_id):
    custom_domain = _tenant_domain_or_404(request, domain_id)
    custom_domain.status = CustomDomain.Status.REMOVED
    was_primary = custom_domain.is_primary
    custom_domain.is_primary = False
    custom_domain.save(update_fields=["status", "is_primary", "updated_at"])

    if custom_domain.managed_domain_id:
        managed_domain = custom_domain.managed_domain
        managed_domain.connection_status = ManagedDomain.ConnectionStatus.DETACHED
        managed_domain.save(update_fields=["connection_status", "updated_at"])

    if was_primary:
        replacement = (
            CustomDomain.objects.filter(tenant=request.tenant)
            .exclude(status=CustomDomain.Status.REMOVED)
            .order_by("-created_at")
            .first()
        )
        if replacement is not None:
            replacement.is_primary = True
            replacement.save(update_fields=["is_primary", "updated_at"])

    messages.success(request, f"{custom_domain.domain} removed.")
    return redirect("dashboard:domain:list", prefix=prefix)


@login_required
@dashboard_prefix_required
@require_POST
def domain_set_primary(request, prefix, domain_id):
    custom_domain = _tenant_domain_or_404(request, domain_id)
    if custom_domain.status == CustomDomain.Status.REMOVED:
        messages.error(request, "Removed domains cannot be set as primary.")
        return redirect("dashboard:domain:detail", prefix=prefix, domain_id=custom_domain.id)

    custom_domain.is_primary = True
    custom_domain.save(update_fields=["is_primary", "updated_at"])
    messages.success(request, f"{custom_domain.domain} is now your primary domain.")
    return redirect("dashboard:domain:detail", prefix=prefix, domain_id=custom_domain.id)


@login_required
@dashboard_prefix_required
@require_POST
def domain_retrigger_verification(request, prefix, domain_id):
    custom_domain = _tenant_domain_or_404(request, domain_id)
    custom_domain.status = CustomDomain.Status.DNS_CHECKING
    custom_domain.save(update_fields=["status", "updated_at"])
    verify_domain_dns.delay(str(custom_domain.id))
    messages.success(request, f"Verification retriggered for {custom_domain.domain}.")
    return redirect("dashboard:domain:detail", prefix=prefix, domain_id=custom_domain.id)


@login_required
@dashboard_prefix_required
@require_GET
def domain_status_partial(request, prefix, domain_id):
    custom_domain = _tenant_domain_or_404(request, domain_id)
    return render(request, "dashboard/domain/partials/domain_status_badge.html", {"domain": custom_domain})


@require_GET
def acme_challenge(request, token):
    hostname = getattr(request, "hostname", request.get_host().split(":", 1)[0].lower())
    challenge = (
        ACMEChallenge.objects.select_related("custom_domain")
        .filter(token=token, is_active=True, custom_domain__domain=hostname)
        .first()
    )
    if challenge is None or challenge.is_expired:
        return HttpResponseForbidden("Challenge not found or expired.")
    return HttpResponse(challenge.key_auth, content_type="text/plain")
