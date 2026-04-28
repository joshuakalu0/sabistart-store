from __future__ import annotations

import hashlib
import logging
import socket
import ssl
import time
from datetime import timedelta
from urllib.error import URLError
from urllib.request import urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from dashboard.domain.models import (
    ACMEChallenge,
    CustomDomain,
    DomainEventLog,
    DomainHealthCheck,
    DomainQuota,
    DomainVerificationAttempt,
    NginxVhostConfig,
    SSLCertificate,
    SSLProvisioningLog,
)

try:
    import dns.resolver
except Exception:  # pragma: no cover - optional dependency
    dns = None
else:  # pragma: no cover - import alias for readability
    dns = dns

try:
    from celery import shared_task
except Exception:  # pragma: no cover - Celery is optional in local dev
    def shared_task(*dargs, **dkwargs):
        bind = dkwargs.get("bind", False)

        def decorator(func):
            if bind:
                def delay(*args, **kwargs):
                    return func(None, *args, **kwargs)
                func.delay = delay
            else:
                func.delay = func
            return func
        return decorator


logger = logging.getLogger("dashboard.domain.tasks")

DNS_RESOLVERS = ["8.8.8.8", "1.1.1.1", "8.8.4.4"]
SIMULATE_INFRA = getattr(settings, "DOMAIN_SIMULATE_INFRA", settings.DEBUG)


def _get_domain(domain_id: str) -> CustomDomain:
    return CustomDomain.objects.select_related("tenant").get(pk=domain_id)


def _resolve_txt(hostname: str) -> list[str]:
    if dns is None:
        return []
    values: list[str] = []
    for nameserver in DNS_RESOLVERS:
        resolver = dns.resolver.Resolver(configure=True)
        resolver.nameservers = [nameserver]
        resolver.lifetime = 4
        try:
            answer = resolver.resolve(hostname, "TXT")
        except Exception:
            continue
        for item in answer:
            text = "".join(part.decode() if isinstance(part, bytes) else str(part) for part in item.strings)
            values.append(text)
    return list(dict.fromkeys(values))


def _resolve_cname(hostname: str) -> list[str]:
    if dns is None:
        return []
    values: list[str] = []
    for nameserver in DNS_RESOLVERS:
        resolver = dns.resolver.Resolver(configure=True)
        resolver.nameservers = [nameserver]
        resolver.lifetime = 4
        try:
            answer = resolver.resolve(hostname, "CNAME")
        except Exception:
            continue
        values.extend(str(item.target).rstrip(".") for item in answer)
    return list(dict.fromkeys(values))


def _resolve_a(hostname: str) -> list[str]:
    try:
        _, _, ips = socket.gethostbyname_ex(hostname)
    except OSError:
        return []
    return sorted(set(ips))


def _log_verification_attempt(custom_domain: CustomDomain, result: str, resolved_value: str = "", expected_value: str = "", error_message: str = "", resolver_used: str = ""):
    DomainVerificationAttempt.objects.create(
        custom_domain=custom_domain,
        result=result,
        resolved_value=resolved_value,
        expected_value=expected_value,
        error_message=error_message,
        resolver_used=resolver_used or ",".join(DNS_RESOLVERS),
    )


def _build_nginx_config(custom_domain: CustomDomain) -> str:
    cert_path = custom_domain.ssl_cert_path or f"/etc/ssl/sabistart/{custom_domain.domain}/fullchain.pem"
    key_path = custom_domain.ssl_key_path or f"/etc/ssl/sabistart/{custom_domain.domain}/privkey.pem"
    return "\n".join(
        [
            f"# Generated config for {custom_domain.domain}",
            "server {",
            "    listen 80;",
            f"    server_name {custom_domain.domain};",
            "    location /.well-known/acme-challenge/ {",
            "        proxy_pass http://127.0.0.1:8000;",
            "    }",
            "    location / {",
            "        return 301 https://$host$request_uri;",
            "    }",
            "}",
            "",
            "server {",
            "    listen 443 ssl http2;",
            f"    server_name {custom_domain.domain};",
            f"    ssl_certificate {cert_path};",
            f"    ssl_certificate_key {key_path};",
            "    location / {",
            "        proxy_pass http://127.0.0.1:8000;",
            "        proxy_set_header Host $host;",
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            "        proxy_set_header X-Forwarded-Proto $scheme;",
            "    }",
            "}",
        ]
    )


@shared_task(bind=True, max_retries=3)
def verify_domain_dns(self, domain_id):
    custom_domain = _get_domain(domain_id)
    if custom_domain.status in {CustomDomain.Status.REMOVED, CustomDomain.Status.SUSPENDED}:
        return {"success": False, "message": "Domain is not eligible for verification."}

    custom_domain.status = CustomDomain.Status.DNS_CHECKING
    custom_domain.save(update_fields=["status", "updated_at"])

    DomainEventLog.objects.create(
        custom_domain=custom_domain,
        event_type=DomainEventLog.EventType.VERIFICATION_STARTED,
        actor="system",
        message="DNS verification started.",
    )

    required_records = custom_domain.dns_records.filter(is_required=True).order_by("created_at")
    failures: list[str] = []
    resolved_payload: list[str] = []

    for record in required_records:
        if record.record_type == record.RecordType.TXT:
            query_name = f"{record.host}.{custom_domain.domain}".strip(".")
            resolved_values = _resolve_txt(query_name)
            matches = record.value in resolved_values
        elif record.record_type == record.RecordType.CNAME:
            query_name = custom_domain.domain
            resolved_values = _resolve_cname(query_name)
            matches = any(value.rstrip(".") == record.value.rstrip(".") for value in resolved_values)
        else:
            query_name = custom_domain.domain
            resolved_values = _resolve_a(query_name)
            matches = record.value in resolved_values

        resolved_payload.append(f"{record.record_type}:{query_name}={resolved_values}")
        if not matches:
            failures.append(f"{record.record_type} {query_name} did not match {record.value}")

    if failures:
        result = DomainVerificationAttempt.Result.RECORD_MISSING if all("did not match" in item for item in failures) else DomainVerificationAttempt.Result.FAILED
        _log_verification_attempt(
            custom_domain,
            result=result,
            resolved_value="; ".join(resolved_payload),
            expected_value="; ".join(f"{record.record_type}:{record.value}" for record in required_records),
            error_message=" | ".join(failures),
        )
        custom_domain.status = CustomDomain.Status.DNS_CHECKING
        custom_domain.save(update_fields=["status", "updated_at"])
        return {"success": False, "message": "DNS records are not fully propagated yet.", "errors": failures}

    _log_verification_attempt(
        custom_domain,
        result=DomainVerificationAttempt.Result.SUCCESS,
        resolved_value="; ".join(resolved_payload),
        expected_value="Verified required records",
    )
    custom_domain.verified_at = timezone.now()
    custom_domain.status = CustomDomain.Status.DNS_VERIFIED
    custom_domain.save(update_fields=["verified_at", "status", "updated_at"])

    quota, _ = DomainQuota.objects.get_or_create(tenant=custom_domain.tenant)
    if quota.ssl_auto_provision:
        provision_ssl_certificate.delay(str(custom_domain.id))

    return {"success": True, "message": "Domain DNS verified."}


@shared_task(bind=True, max_retries=3)
def provision_ssl_certificate(self, domain_id):
    custom_domain = _get_domain(domain_id)
    certificate, _ = SSLCertificate.objects.get_or_create(custom_domain=custom_domain)
    certificate.status = SSLCertificate.Status.PROVISIONING
    certificate.challenge_type = "http01"
    certificate.save(update_fields=["status", "challenge_type", "updated_at"])

    custom_domain.status = CustomDomain.Status.SSL_PENDING
    custom_domain.ssl_status = "provisioning"
    custom_domain.save(update_fields=["status", "ssl_status", "updated_at"])

    SSLProvisioningLog.objects.create(
        certificate=certificate,
        step=SSLProvisioningLog.Step.INITIATED,
        success=True,
        message="SSL provisioning started.",
    )
    DomainEventLog.objects.create(
        custom_domain=custom_domain,
        event_type=DomainEventLog.EventType.SSL_REQUESTED,
        actor="system",
        message="SSL provisioning queued.",
    )

    if not SIMULATE_INFRA:
        ACMEChallenge.objects.update_or_create(
            custom_domain=custom_domain,
            token=custom_domain.verification_token[:32],
            defaults={
                "key_auth": f"{custom_domain.verification_token}.pending",
                "is_active": True,
                "expires_at": timezone.now() + timedelta(minutes=15),
            },
        )
        SSLProvisioningLog.objects.create(
            certificate=certificate,
            step=SSLProvisioningLog.Step.CHALLENGE_CREATED,
            success=True,
            message="ACME challenge prepared. Awaiting infrastructure validation.",
        )
        return {"success": True, "message": "SSL challenge created."}

    certificate.status = SSLCertificate.Status.ACTIVE
    certificate.issued_at = timezone.now()
    certificate.expires_at = timezone.now() + timedelta(days=90)
    certificate.last_renewed_at = timezone.now()
    certificate.cert_fingerprint = hashlib.sha256(custom_domain.domain.encode("utf-8")).hexdigest()
    certificate.cert_path = f"/etc/ssl/sabistart/{custom_domain.domain}/fullchain.pem"
    certificate.key_path = f"/etc/ssl/sabistart/{custom_domain.domain}/privkey.pem"
    certificate.chain_path = f"/etc/ssl/sabistart/{custom_domain.domain}/chain.pem"
    certificate.save()

    custom_domain.ssl_status = "active"
    custom_domain.ssl_expires_at = certificate.expires_at
    custom_domain.ssl_cert_path = certificate.cert_path
    custom_domain.ssl_key_path = certificate.key_path
    custom_domain.save(
        update_fields=[
            "ssl_status",
            "ssl_expires_at",
            "ssl_cert_path",
            "ssl_key_path",
            "updated_at",
        ]
    )

    SSLProvisioningLog.objects.create(
        certificate=certificate,
        step=SSLProvisioningLog.Step.CERT_ISSUED,
        success=True,
        message="Simulated certificate issued in debug mode.",
    )
    DomainEventLog.objects.create(
        custom_domain=custom_domain,
        event_type=DomainEventLog.EventType.SSL_ISSUED,
        actor="system",
        message="SSL certificate issued.",
    )
    generate_nginx_config.delay(str(custom_domain.id))
    return {"success": True, "message": "SSL certificate provisioned."}


@shared_task
def generate_nginx_config(domain_id):
    custom_domain = _get_domain(domain_id)
    config_content = _build_nginx_config(custom_domain)
    config_hash = hashlib.sha256(config_content.encode("utf-8")).hexdigest()

    with transaction.atomic():
        NginxVhostConfig.objects.filter(custom_domain=custom_domain, is_active=True).update(is_active=False)
        snapshot = NginxVhostConfig.objects.create(
            custom_domain=custom_domain,
            config_content=config_content,
            config_hash=config_hash,
            is_active=SIMULATE_INFRA,
            applied_at=timezone.now() if SIMULATE_INFRA else None,
            nginx_reloaded=SIMULATE_INFRA,
        )

        if SIMULATE_INFRA:
            custom_domain.status = CustomDomain.Status.ACTIVE
            custom_domain.ssl_status = "active"
            custom_domain.save(update_fields=["status", "ssl_status", "updated_at"])
            DomainEventLog.objects.create(
                custom_domain=custom_domain,
                event_type=DomainEventLog.EventType.NGINX_UPDATED,
                actor="system",
                message="Nginx configuration generated and marked active in debug mode.",
            )

    return {"success": True, "snapshot_id": str(snapshot.id)}


@shared_task
def run_domain_health_check(domain_id):
    custom_domain = _get_domain(domain_id)

    dns_resolves = False
    ssl_valid = False
    http_reachable = False
    response_code = None
    response_time_ms = None
    resolved_ip = None
    error_detail = ""

    try:
        ips = _resolve_a(custom_domain.domain)
        if ips:
            dns_resolves = True
            resolved_ip = ips[0]
    except Exception as exc:  # pragma: no cover - network/environment dependent
        error_detail = str(exc)

    try:
        certificate = getattr(custom_domain, "certificate", None)
        if certificate and certificate.status == SSLCertificate.Status.ACTIVE and certificate.expires_at and certificate.expires_at > timezone.now():
            ssl_valid = True
    except Exception as exc:  # pragma: no cover
        error_detail = error_detail or str(exc)

    try:
        start = time.monotonic()
        with urlopen(f"http://{custom_domain.domain}", timeout=5) as response:  # nosec - health check only
            response_code = response.getcode()
            http_reachable = 200 <= response_code < 400
        response_time_ms = int((time.monotonic() - start) * 1000)
    except URLError as exc:  # pragma: no cover - network/environment dependent
        error_detail = error_detail or str(exc)
    except Exception as exc:  # pragma: no cover
        error_detail = error_detail or str(exc)

    health = DomainHealthCheck.objects.create(
        custom_domain=custom_domain,
        dns_resolves=dns_resolves,
        ssl_valid=ssl_valid,
        http_reachable=http_reachable,
        response_code=response_code,
        response_time_ms=response_time_ms,
        resolved_ip=resolved_ip,
        error_detail=error_detail,
    )

    recent_failures = custom_domain.health_checks.filter(
        dns_resolves=False,
        ssl_valid=False,
        http_reachable=False,
    ).count()
    if recent_failures >= 3:
        DomainEventLog.objects.create(
            custom_domain=custom_domain,
            event_type=DomainEventLog.EventType.VERIFICATION_FAILED,
            actor="system",
            message="Health check has failed repeatedly.",
            metadata={"recent_failures": recent_failures},
        )

    return {
        "success": dns_resolves and ssl_valid and http_reachable,
        "health_check_id": health.id,
    }


@shared_task
def run_all_health_checks():
    count = 0
    for domain_id in CustomDomain.objects.filter(status=CustomDomain.Status.ACTIVE).values_list("id", flat=True):
        run_domain_health_check.delay(str(domain_id))
        count += 1
    return {"success": True, "count": count}


@shared_task
def renew_expiring_certificates():
    count = 0
    for certificate in SSLCertificate.objects.filter(
        status=SSLCertificate.Status.ACTIVE,
        auto_renew=True,
        expires_at__lte=timezone.now() + timedelta(days=30),
    ).select_related("custom_domain"):
        if SIMULATE_INFRA:
            certificate.status = SSLCertificate.Status.ACTIVE
            certificate.last_renewed_at = timezone.now()
            certificate.expires_at = timezone.now() + timedelta(days=90)
            certificate.save(update_fields=["status", "last_renewed_at", "expires_at", "updated_at"])
            certificate.custom_domain.ssl_expires_at = certificate.expires_at
            certificate.custom_domain.save(update_fields=["ssl_expires_at", "updated_at"])
            DomainEventLog.objects.create(
                custom_domain=certificate.custom_domain,
                event_type=DomainEventLog.EventType.SSL_RENEWED,
                actor="system",
                message="SSL certificate renewed in debug mode.",
            )
            count += 1
        else:
            certificate.status = SSLCertificate.Status.RENEWING
            certificate.save(update_fields=["status", "updated_at"])
            provision_ssl_certificate.delay(str(certificate.custom_domain_id))
            count += 1
    return {"success": True, "count": count}


@shared_task
def cleanup_expired_acme_challenges():
    deleted, _ = ACMEChallenge.objects.filter(expires_at__lt=timezone.now()).delete()
    return {"success": True, "deleted": deleted}


@shared_task
def poll_pending_domains():
    count = 0
    for domain_id in CustomDomain.objects.filter(
        status__in=[CustomDomain.Status.PENDING, CustomDomain.Status.DNS_CHECKING, CustomDomain.Status.FAILED]
    ).values_list("id", flat=True):
        verify_domain_dns.delay(str(domain_id))
        count += 1
    return {"success": True, "count": count}
