from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from dashboard.decorators import dashboard_prefix_required
from dashboard.feature_marketplace.services import require_feature
from dashboard.domain.forms import AddDomainForm, DomainSettingsForm
from dashboard.domain.models import ACMEChallenge, CustomDomain, DomainEventLog
from dashboard.domain.tasks import verify_domain_dns
from dashboard.domain.view_utils import build_page_context, get_domain_quota, get_tenant_domains


def _tenant_domain_or_404(request, domain_id):
    domain = get_object_or_404(CustomDomain, id=domain_id)
    if domain.tenant_id != request.tenant.id:
        raise Http404("Domain not found")
    return domain


@login_required
@dashboard_prefix_required
@require_feature("max_custom_domains")
def domain_list(request, prefix):
    quota = get_domain_quota(request.tenant)
    domains = get_tenant_domains(request.tenant)
    context = build_page_context(
        prefix,
        "Domains",
        "domains_list",
        add_form=AddDomainForm(),
        quota=quota,
        domains=domains,
        active_count=sum(1 for domain in domains if domain.status == CustomDomain.Status.ACTIVE),
        pending_count=sum(
            1
            for domain in domains
            if domain.status in {CustomDomain.Status.PENDING, CustomDomain.Status.DNS_CHECKING, CustomDomain.Status.SSL_PENDING}
        ),
        failed_count=sum(1 for domain in domains if domain.status == CustomDomain.Status.FAILED),
    )
    return render(request, "dashboard/domain/domain_list.html", context)


@login_required
@dashboard_prefix_required
@require_feature("max_custom_domains")
@require_http_methods(["POST"])
def domain_add(request, prefix):
    quota = get_domain_quota(request.tenant)
    if not quota.has_capacity:
        messages.error(
            request,
            f"You have reached your limit of {quota.max_custom_domains} custom domain(s).",
        )
        return redirect("dashboard:domain:list", prefix=prefix)

    form = AddDomainForm(request.POST)
    if not form.is_valid():
        context = build_page_context(
            prefix,
            "Domains",
            "domains_list",
            add_form=form,
            quota=quota,
            domains=get_tenant_domains(request.tenant),
        )
        return render(request, "dashboard/domain/domain_list.html", context, status=400)

    is_primary = not get_tenant_domains(request.tenant).exists()
    custom_domain = CustomDomain.objects.create(
        tenant=request.tenant,
        domain=form.cleaned_data["domain"],
        is_primary=is_primary,
        status=CustomDomain.Status.PENDING,
        notes="Added from dashboard.",
    )
    verify_domain_dns.delay(str(custom_domain.id))
    messages.success(request, f"{custom_domain.domain} added. DNS verification has started.")
    return redirect("dashboard:domain:detail", prefix=prefix, domain_id=custom_domain.id)


@login_required
@dashboard_prefix_required
@require_feature("max_custom_domains")
def domain_detail(request, prefix, domain_id):
    custom_domain = _tenant_domain_or_404(request, domain_id)
    if request.method == "POST":
        form = DomainSettingsForm(request.POST, instance=custom_domain)
        if form.is_valid():
            updated_domain = form.save()
            if updated_domain.is_primary:
                DomainEventLog.objects.create(
                    custom_domain=updated_domain,
                    event_type=DomainEventLog.EventType.PRIMARY_SET,
                    actor="tenant",
                    message="Domain marked as primary from dashboard.",
                )
            messages.success(request, "Domain settings updated.")
            return redirect("dashboard:domain:detail", prefix=prefix, domain_id=custom_domain.id)
    else:
        form = DomainSettingsForm(instance=custom_domain)

    context = build_page_context(
        prefix,
        custom_domain.domain,
        "domains_list",
        domain=custom_domain,
        settings_form=form,
        dns_records=custom_domain.dns_records.order_by("purpose", "record_type", "host"),
        verification_attempts=custom_domain.verification_attempts.order_by("-attempted_at")[:10],
        events=custom_domain.events.order_by("-created_at")[:20],
        health_checks=custom_domain.health_checks.order_by("-checked_at")[:10],
        certificate=getattr(custom_domain, "certificate", None),
        redirect_rules=custom_domain.incoming_redirects.order_by("-created_at"),
        quota=get_domain_quota(request.tenant),
    )
    return render(request, "dashboard/domain/domain_detail.html", context)


@login_required
@dashboard_prefix_required
@require_feature("max_custom_domains")
@require_POST
def domain_delete(request, prefix, domain_id):
    custom_domain = _tenant_domain_or_404(request, domain_id)
    custom_domain.status = CustomDomain.Status.REMOVED
    was_primary = custom_domain.is_primary
    custom_domain.is_primary = False
    custom_domain.save(update_fields=["status", "is_primary", "updated_at"])

    DomainEventLog.objects.create(
        custom_domain=custom_domain,
        event_type=DomainEventLog.EventType.DOMAIN_REMOVED,
        actor="tenant",
        message="Domain removed from dashboard.",
    )

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
@require_feature("max_custom_domains")
@require_POST
def domain_set_primary(request, prefix, domain_id):
    custom_domain = _tenant_domain_or_404(request, domain_id)
    if custom_domain.status == CustomDomain.Status.REMOVED:
        messages.error(request, "Removed domains cannot be set as primary.")
        return redirect("dashboard:domain:detail", prefix=prefix, domain_id=custom_domain.id)

    custom_domain.is_primary = True
    custom_domain.save(update_fields=["is_primary", "updated_at"])
    DomainEventLog.objects.create(
        custom_domain=custom_domain,
        event_type=DomainEventLog.EventType.PRIMARY_SET,
        actor="tenant",
        message="Domain set as primary.",
    )
    messages.success(request, f"{custom_domain.domain} is now your primary domain.")
    return redirect("dashboard:domain:detail", prefix=prefix, domain_id=custom_domain.id)


@login_required
@dashboard_prefix_required
@require_feature("max_custom_domains")
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
@require_feature("max_custom_domains")
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
