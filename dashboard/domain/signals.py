# domains/signals.py

import logging
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
from django.conf import settings
from .models import CustomDomain, DomainEventLog, DomainResolutionCache, DomainDNSRecord

logger = logging.getLogger("dashboard.domain.signals")

# Maps a domain status → the event log entry type to auto-create
STATUS_EVENT_MAP = {
    CustomDomain.Status.DNS_VERIFIED: DomainEventLog.EventType.VERIFICATION_SUCCESS,
    CustomDomain.Status.ACTIVE:       DomainEventLog.EventType.DOMAIN_ACTIVATED,
    CustomDomain.Status.SUSPENDED:    DomainEventLog.EventType.DOMAIN_SUSPENDED,
    CustomDomain.Status.REMOVED:      DomainEventLog.EventType.DOMAIN_REMOVED,
    CustomDomain.Status.FAILED:       DomainEventLog.EventType.VERIFICATION_FAILED,
}


# ── Track status changes (pre_save) ───────────────────────────────────────────

@receiver(pre_save, sender=CustomDomain)
def capture_old_status(sender, instance, **kwargs):
    """
    Store the current DB status on the instance before saving,
    so post_save can compare old vs new.
    """
    if instance.pk:
        try:
            instance._old_status = CustomDomain.objects.get(pk=instance.pk).status
        except CustomDomain.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


# ── Main post-save handler ─────────────────────────────────────────────────────

@receiver(post_save, sender=CustomDomain)
def on_domain_saved(sender, instance, created, **kwargs):
    """
    Central handler for CustomDomain saves:
      - On create: log event + generate DNS instructions
      - On update: log status transitions + manage resolution cache
      - Auto-trigger SSL provisioning after DNS is verified
    """
    if created:
        _handle_domain_created(instance)
    else:
        _handle_domain_updated(instance)


def _handle_domain_created(instance):
    """Called once when a new CustomDomain row is created."""
    logger.info(f"[signals] New custom domain added: {instance.domain}")

    DomainEventLog.objects.create(
        custom_domain=instance,
        event_type=DomainEventLog.EventType.DOMAIN_ADDED,
        actor='tenant',
        message=f"Custom domain {instance.domain} added.",
        metadata={'domain_type': 'root' if instance.is_root_domain else 'subdomain'},
    )

    # Generate the DNS instructions the tenant needs to add at their registrar
    _create_dns_instructions(instance)


def _handle_domain_updated(instance):
    """Called on every subsequent save of an existing CustomDomain."""
    old_status = getattr(instance, '_old_status', None)
    new_status = instance.status

    # ── 1. Log status transitions ──────────────────────────────────────────
    if old_status and old_status != new_status:
        event_type = STATUS_EVENT_MAP.get(new_status)
        if event_type:
            DomainEventLog.objects.create(
                custom_domain=instance,
                event_type=event_type,
                actor='system',
                message=f"Status changed: {old_status} → {new_status}",
                metadata={'old_status': old_status, 'new_status': new_status},
            )
        logger.info(f"[signals] {instance.domain}: {old_status} → {new_status}")

    # ── 2. Always invalidate resolution cache on save ──────────────────────
    _invalidate_resolution_cache(instance.domain)

    # ── 3. Warm up cache if domain is now active ───────────────────────────
    if new_status == CustomDomain.Status.ACTIVE:
        _warm_resolution_cache(instance)

    # ── 4. Auto-trigger SSL after DNS verified ─────────────────────────────
    if old_status != new_status and new_status == CustomDomain.Status.DNS_VERIFIED:
        _trigger_ssl_provisioning(instance)


def _invalidate_resolution_cache(domain):
    """Invalidate DB resolution cache for this hostname."""
    DomainResolutionCache.objects.filter(hostname=domain).update(is_valid=False)

    # Also invalidate Redis cache
    try:
        from django.core.cache import cache
        cache.delete(f'domain_resolve:{domain}')
    except Exception as e:
        logger.warning(f"[signals] Redis cache invalidation failed for {domain}: {e}")


def _warm_resolution_cache(instance):
    """Upsert a valid DB cache entry when domain goes ACTIVE."""
    DomainResolutionCache.objects.update_or_create(
        hostname=instance.domain,
        defaults={
            'tenant_id':     instance.tenant_id,
            'tenant_schema': instance.tenant.schema_name,
            'domain_type':   'custom',
            'is_valid':      True,
        }
    )
    logger.info(f"[signals] Resolution cache warmed for {instance.domain}")


def _trigger_ssl_provisioning(instance):
    """Fire the SSL provisioning Celery task."""
    try:
        from .tasks import provision_ssl_certificate
        provision_ssl_certificate.delay(str(instance.id))
        logger.info(f"[signals] SSL provisioning triggered for {instance.domain}")
    except Exception as e:
        logger.error(f"[signals] Failed to trigger SSL for {instance.domain}: {e}")


# ── Enforce single primary per tenant ─────────────────────────────────────────

@receiver(post_save, sender=CustomDomain)
def enforce_single_primary(sender, instance, **kwargs):
    """
    If this domain was just marked as primary, unset is_primary on
    all other domains for the same tenant.
    """
    if instance.is_primary:
        updated = (
            CustomDomain.objects
            .filter(tenant=instance.tenant, is_primary=True)
            .exclude(pk=instance.pk)
            .update(is_primary=False)
        )
        if updated:
            logger.info(
                f"[signals] Cleared is_primary on {updated} other domain(s) "
                f"for tenant {instance.tenant}"
            )


# ── Clean up on delete ────────────────────────────────────────────────────────

@receiver(post_delete, sender=CustomDomain)
def on_domain_deleted(sender, instance, **kwargs):
    """Remove resolution cache entry when domain is deleted."""
    DomainResolutionCache.objects.filter(hostname=instance.domain).delete()
    try:
        from django.core.cache import cache
        cache.delete(f'domain_resolve:{instance.domain}')
    except Exception:
        pass
    logger.info(f"[signals] Resolution cache cleared for deleted domain: {instance.domain}")


# ── DNS instruction generator ──────────────────────────────────────────────────

def _create_dns_instructions(domain_instance):
    """
    Generate the DNS records the tenant must add at their registrar.
    Called once on domain creation.

    Root domain (mycoolbrand.com):
        A    @    → SERVER_IP         (routes traffic to your server)
        A    www  → SERVER_IP         (covers www.mycoolbrand.com too)
        TXT  _platform-verify → token (proves ownership)

    Subdomain (shop.mycoolbrand.com):
        CNAME  shop  → PLATFORM_CNAME  (CNAME is fine for subdomains)
        TXT    _platform-verify → token
    """
    server_ip       = getattr(settings, 'SERVER_IP', '0.0.0.0')
    platform_cname  = getattr(settings, 'PLATFORM_CNAME', 'proxy.yourplatform.com')
    records_to_create = []

    if domain_instance.is_root_domain:
        # Root/apex domain — must use A records (CNAME forbidden on @)
        records_to_create = [
            dict(
                record_type=DomainDNSRecord.RecordType.A,
                host='@',
                value=server_ip,
                ttl=3600,
                purpose='routing',
                is_required=True,
            ),
            dict(
                record_type=DomainDNSRecord.RecordType.A,
                host='www',
                value=server_ip,
                ttl=3600,
                purpose='routing',
                is_required=False,  # optional but recommended
            ),
        ]
    else:
        # Subdomain — CNAME is fine and preferred
        subdomain_part = domain_instance.domain.split('.')[0]  # e.g. "shop"
        records_to_create = [
            dict(
                record_type=DomainDNSRecord.RecordType.CNAME,
                host=subdomain_part,
                value=platform_cname,
                ttl=3600,
                purpose='routing',
                is_required=True,
            ),
        ]

    # Verification TXT record — required for ALL domain types
    records_to_create.append(
        dict(
            record_type=DomainDNSRecord.RecordType.TXT,
            host='_platform-verify',
            value=domain_instance.txt_record_value,
            ttl=300,   # short TTL — we want to detect it quickly
            purpose='verification',
            is_required=True,
        )
    )

    for record_data in records_to_create:
        DomainDNSRecord.objects.create(
            custom_domain=domain_instance,
            **record_data,
        )

    logger.info(
        f"[signals] Created {len(records_to_create)} DNS instructions "
        f"for {domain_instance.domain} "
        f"({'root domain' if domain_instance.is_root_domain else 'subdomain'})"
    )
