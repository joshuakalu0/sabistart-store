# domains/models.py

import uuid
import secrets
from django.db import models
from django.utils import timezone


# ─────────────────────────────────────────────
# 1. CUSTOM DOMAIN
# ─────────────────────────────────────────────
class CustomDomain(models.Model):
    """
    A tenant-owned custom domain (e.g. mycoolbrand.com or shop.mycoolbrand.com).
    Separate from django-tenants' Domain model which handles subdomains.
    Supports both root domains (A record) and subdomains (CNAME).
    """

    class Status(models.TextChoices):
        PENDING      = 'pending',      'Pending Setup'
        DNS_CHECKING = 'dns_checking', 'Checking DNS'
        DNS_VERIFIED = 'dns_verified', 'DNS Verified'
        SSL_PENDING  = 'ssl_pending',  'SSL Provisioning'
        ACTIVE       = 'active',       'Active'
        FAILED       = 'failed',       'Failed'
        SUSPENDED    = 'suspended',    'Suspended'
        REMOVED      = 'removed',      'Removed'

    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant     = models.ForeignKey(
                   'core.Shop',
                   on_delete=models.CASCADE,
                   related_name='custom_domains',
                 )
    domain     = models.CharField(max_length=253, unique=True, db_index=True)
    status     = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    is_primary = models.BooleanField(default=False)  # all others redirect here
    managed_domain = models.OneToOneField(
        "ManagedDomain",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="custom_connection",
    )
    connection_source = models.CharField(
        max_length=20,
        choices=[("manual", "Manual"), ("managed", "Managed Domain")],
        default="manual",
    )

    # Verification
    verification_token  = models.CharField(max_length=64, unique=True, editable=False)
    verification_method = models.CharField(
                            max_length=10,
                            choices=[('txt', 'TXT Record'), ('cname', 'CNAME Record')],
                            default='txt',
                          )
    verified_at = models.DateTimeField(null=True, blank=True)

    # SSL
    ssl_status = models.CharField(
                   max_length=20,
                   choices=[
                       ('none',         'None'),
                       ('provisioning', 'Provisioning'),
                       ('active',       'Active'),
                       ('expiring_soon','Expiring Soon'),
                       ('expired',      'Expired'),
                       ('failed',       'Failed'),
                   ],
                   default='none',
                 )
    ssl_expires_at = models.DateTimeField(null=True, blank=True)
    ssl_provider   = models.CharField(max_length=50, default='letsencrypt')
    ssl_cert_path  = models.CharField(max_length=500, blank=True)
    ssl_key_path   = models.CharField(max_length=500, blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes      = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes  = [
            models.Index(fields=['domain', 'status']),
            models.Index(fields=['tenant', 'status']),
        ]

    def save(self, *args, **kwargs):
        if not self.verification_token:
            self.verification_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.domain} → {self.tenant} [{self.status}]"

    @property
    def is_root_domain(self):
        """True if this is a root/apex domain (e.g. mycoolbrand.com), not a subdomain."""
        parts = self.domain.split('.')
        return len(parts) == 2

    @property
    def txt_record_name(self):
        return f"_platform-verify.{self.domain}"

    @property
    def txt_record_value(self):
        return f"platform-verify={self.verification_token}"


# ─────────────────────────────────────────────
# 2. DOMAIN DNS RECORD INSTRUCTION
# ─────────────────────────────────────────────
class DomainDNSRecord(models.Model):
    """
    The exact DNS records the tenant must add at their registrar.
    We store what we told them to add, for audit and re-display.
    Root domains get A records; subdomains get CNAME records.
    """

    class RecordType(models.TextChoices):
        A     = 'A',     'A Record'
        CNAME = 'CNAME', 'CNAME Record'
        TXT   = 'TXT',   'TXT Record'
        AAAA  = 'AAAA',  'AAAA Record'

    custom_domain = models.ForeignKey(CustomDomain, on_delete=models.CASCADE, related_name='dns_records')
    record_type   = models.CharField(max_length=10, choices=RecordType.choices)
    host          = models.CharField(max_length=253)   # e.g. "@", "www", "_platform-verify"
    value         = models.CharField(max_length=512)   # IP, target hostname, or TXT value
    ttl           = models.PositiveIntegerField(default=3600)
    purpose       = models.CharField(
                      max_length=20,
                      choices=[
                          ('routing',      'Routing'),
                          ('verification', 'Verification'),
                          ('ssl',          'SSL'),
                      ],
                      default='routing',
                    )
    is_required = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.record_type} {self.host} → {self.value}"


# ─────────────────────────────────────────────
# 3. DOMAIN VERIFICATION ATTEMPT
# ─────────────────────────────────────────────
class DomainVerificationAttempt(models.Model):
    """
    Every time the system checks DNS for a domain — success or fail — log it.
    Celery polls on a schedule and writes a row here each time.
    """

    class Result(models.TextChoices):
        SUCCESS        = 'success',        'Success'
        FAILED         = 'failed',         'Failed'
        RECORD_MISSING = 'record_missing', 'Record Missing'
        WRONG_VALUE    = 'wrong_value',    'Wrong Value'
        DNS_ERROR      = 'dns_error',      'DNS Error'
        TIMEOUT        = 'timeout',        'Timeout'

    custom_domain  = models.ForeignKey(CustomDomain, on_delete=models.CASCADE, related_name='verification_attempts')
    attempted_at   = models.DateTimeField(auto_now_add=True)
    result         = models.CharField(max_length=20, choices=Result.choices)
    resolved_value = models.TextField(blank=True)  # what DNS actually returned
    expected_value = models.TextField(blank=True)  # what we expected
    error_message  = models.TextField(blank=True)
    resolver_used  = models.CharField(max_length=50, default='8.8.8.8')

    class Meta:
        ordering = ['-attempted_at']

    def __str__(self):
        return f"{self.custom_domain.domain} @ {self.attempted_at} → {self.result}"


# ─────────────────────────────────────────────
# 4. SSL CERTIFICATE
# ─────────────────────────────────────────────
class SSLCertificate(models.Model):
    """
    Tracks the full lifecycle of an SSL certificate for a custom domain.
    One certificate per custom domain (OneToOne).
    Auto-renews 30 days before expiry via Celery beat.
    """

    class Status(models.TextChoices):
        PENDING      = 'pending',      'Pending'
        PROVISIONING = 'provisioning', 'Provisioning'
        ACTIVE       = 'active',       'Active'
        RENEWING     = 'renewing',     'Renewing'
        EXPIRED      = 'expired',      'Expired'
        REVOKED      = 'revoked',      'Revoked'
        FAILED       = 'failed',       'Failed'

    custom_domain    = models.OneToOneField(CustomDomain, on_delete=models.CASCADE, related_name='certificate')
    status           = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    provider         = models.CharField(max_length=50, default='letsencrypt')
    challenge_type   = models.CharField(
                         max_length=10,
                         choices=[('http01', 'HTTP-01'), ('dns01', 'DNS-01')],
                         default='http01',
                       )
    issued_at        = models.DateTimeField(null=True, blank=True)
    expires_at       = models.DateTimeField(null=True, blank=True)
    auto_renew       = models.BooleanField(default=True)
    last_renewed_at  = models.DateTimeField(null=True, blank=True)
    cert_fingerprint = models.CharField(max_length=128, blank=True)
    acme_account_id  = models.CharField(max_length=255, blank=True)
    cert_path        = models.CharField(max_length=500, blank=True)
    key_path         = models.CharField(max_length=500, blank=True)
    chain_path       = models.CharField(max_length=500, blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    @property
    def days_until_expiry(self):
        if self.expires_at:
            return (self.expires_at - timezone.now()).days
        return None

    @property
    def needs_renewal(self):
        return self.days_until_expiry is not None and self.days_until_expiry <= 30

    def __str__(self):
        return f"SSL:{self.custom_domain.domain} [{self.status}] exp:{self.expires_at}"


# ─────────────────────────────────────────────
# 5. SSL PROVISIONING LOG
# ─────────────────────────────────────────────
class SSLProvisioningLog(models.Model):
    """
    Step-by-step log of every SSL provisioning or renewal attempt.
    Use this to debug exactly where an SSL issuance failed.
    """

    class Step(models.TextChoices):
        INITIATED         = 'initiated',         'Initiated'
        ACME_ORDER        = 'acme_order',         'ACME Order Created'
        CHALLENGE_CREATED = 'challenge_created',  'Challenge Created'
        CHALLENGE_PLACED  = 'challenge_placed',   'Challenge Placed'
        CHALLENGE_VERIFY  = 'challenge_verify',   'Challenge Verified'
        CERT_ISSUED       = 'cert_issued',        'Certificate Issued'
        NGINX_RELOADED    = 'nginx_reloaded',     'Nginx Reloaded'
        COMPLETED         = 'completed',          'Completed'
        FAILED            = 'failed',             'Failed'

    certificate = models.ForeignKey(SSLCertificate, on_delete=models.CASCADE, related_name='logs')
    step        = models.CharField(max_length=30, choices=Step.choices)
    success     = models.BooleanField(default=True)
    message     = models.TextField(blank=True)
    metadata    = models.JSONField(default=dict, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.certificate.custom_domain.domain} | {self.step} | {'✅' if self.success else '❌'}"


# ─────────────────────────────────────────────
# 6. DOMAIN REDIRECT RULE
# ─────────────────────────────────────────────
class DomainRedirectRule(models.Model):
    """
    Redirect rules:
    - non-www → www (or vice versa)
    - old domain → new domain
    - HTTP → HTTPS is handled by Nginx, not here
    """

    class RedirectType(models.TextChoices):
        PERMANENT = '301', '301 Permanent'
        TEMPORARY = '302', '302 Temporary'

    tenant        = models.ForeignKey('core.Shop', on_delete=models.CASCADE, related_name='redirect_rules')
    from_domain   = models.CharField(max_length=253)
    to_domain     = models.ForeignKey(
                      CustomDomain,
                      on_delete=models.SET_NULL,
                      null=True,
                      related_name='incoming_redirects',
                    )
    redirect_type = models.CharField(max_length=3, choices=RedirectType.choices, default=RedirectType.PERMANENT)
    is_active     = models.BooleanField(default=True)
    preserve_path = models.BooleanField(default=True)  # /about → newdomain.com/about
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('tenant', 'from_domain')

    def __str__(self):
        return f"{self.from_domain} → {self.to_domain} [{self.redirect_type}]"


# ─────────────────────────────────────────────
# 7. DOMAIN EVENT LOG (Audit Trail)
# ─────────────────────────────────────────────
class DomainEventLog(models.Model):
    """
    Immutable audit log of every significant event on a domain.
    Never delete rows from this table — it's your paper trail.
    """

    class EventType(models.TextChoices):
        DOMAIN_ADDED         = 'domain_added',          'Domain Added'
        VERIFICATION_STARTED = 'verification_started',  'Verification Started'
        VERIFICATION_SUCCESS = 'verification_success',  'Verification Success'
        VERIFICATION_FAILED  = 'verification_failed',   'Verification Failed'
        SSL_REQUESTED        = 'ssl_requested',         'SSL Requested'
        SSL_ISSUED           = 'ssl_issued',            'SSL Issued'
        SSL_RENEWED          = 'ssl_renewed',           'SSL Renewed'
        SSL_FAILED           = 'ssl_failed',            'SSL Failed'
        DOMAIN_ACTIVATED     = 'domain_activated',      'Domain Activated'
        DOMAIN_SUSPENDED     = 'domain_suspended',      'Domain Suspended'
        DOMAIN_REMOVED       = 'domain_removed',        'Domain Removed'
        PRIMARY_SET          = 'primary_set',           'Set as Primary'
        NGINX_UPDATED        = 'nginx_updated',         'Nginx Config Updated'

    custom_domain = models.ForeignKey(CustomDomain, on_delete=models.CASCADE, related_name='events')
    event_type    = models.CharField(max_length=30, choices=EventType.choices)
    actor         = models.CharField(max_length=100, blank=True)  # 'tenant', 'system', 'admin'
    message       = models.TextField(blank=True)
    metadata      = models.JSONField(default=dict, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.custom_domain.domain} | {self.event_type} | {self.created_at}"


# ─────────────────────────────────────────────
# 8. DOMAIN HEALTH CHECK
# ─────────────────────────────────────────────
class DomainHealthCheck(models.Model):
    """
    Periodic health snapshots — run by Celery beat every N minutes.
    Checks: DNS resolves correctly, SSL is valid, site responds with 200.
    """

    custom_domain    = models.ForeignKey(CustomDomain, on_delete=models.CASCADE, related_name='health_checks')
    checked_at       = models.DateTimeField(auto_now_add=True)
    dns_resolves     = models.BooleanField(default=False)
    ssl_valid        = models.BooleanField(default=False)
    http_reachable   = models.BooleanField(default=False)
    response_code    = models.PositiveIntegerField(null=True, blank=True)
    response_time_ms = models.PositiveIntegerField(null=True, blank=True)
    resolved_ip      = models.GenericIPAddressField(null=True, blank=True)
    error_detail     = models.TextField(blank=True)

    class Meta:
        ordering      = ['-checked_at']
        get_latest_by = 'checked_at'

    def __str__(self):
        status = '✅' if (self.dns_resolves and self.ssl_valid and self.http_reachable) else '❌'
        return f"{status} {self.custom_domain.domain} @ {self.checked_at}"


# ─────────────────────────────────────────────
# 9. DOMAIN QUOTA
# ─────────────────────────────────────────────
class DomainQuota(models.Model):
    """
    How many custom domains is this tenant allowed?
    Tied to their subscription plan. Enforce this before allowing domain adds.
    """

    tenant               = models.OneToOneField('core.Shop', on_delete=models.CASCADE, related_name='domain_quota')
    max_custom_domains   = models.PositiveIntegerField(default=1)
    max_redirects        = models.PositiveIntegerField(default=5)
    ssl_auto_provision   = models.BooleanField(default=True)
    wildcard_ssl_allowed = models.BooleanField(default=False)
    updated_at           = models.DateTimeField(auto_now=True)

    @property
    def domains_used(self):
        return self.tenant.custom_domains.exclude(status='removed').count()

    @property
    def has_capacity(self):
        return self.domains_used < self.max_custom_domains

    def __str__(self):
        return f"{self.tenant} — {self.domains_used}/{self.max_custom_domains} domains"


# ─────────────────────────────────────────────
# 10. NGINX VHOST CONFIG SNAPSHOT
# ─────────────────────────────────────────────
class NginxVhostConfig(models.Model):
    """
    Every time Nginx config is regenerated for a domain, store a snapshot.
    Enables rollback if a bad config is deployed.
    """

    custom_domain  = models.ForeignKey(CustomDomain, on_delete=models.CASCADE, related_name='nginx_configs')
    config_content = models.TextField()
    config_hash    = models.CharField(max_length=64)   # SHA256 of config_content
    is_active      = models.BooleanField(default=False)
    applied_at     = models.DateTimeField(null=True, blank=True)
    nginx_reloaded = models.BooleanField(default=False)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"NginxConfig:{self.custom_domain.domain} active={self.is_active}"


# ─────────────────────────────────────────────
# 11. DOMAIN RESOLUTION CACHE
# ─────────────────────────────────────────────
class DomainResolutionCache(models.Model):
    """
    In-DB cache: hostname → tenant.
    The middleware checks this before doing a full CustomDomain lookup.
    Invalidated automatically by signals whenever a domain's status changes.
    Works alongside Redis cache (Redis is layer 1, this is layer 2).
    """

    hostname      = models.CharField(max_length=253, unique=True, db_index=True)
    tenant_id     = models.IntegerField()
    tenant_schema = models.CharField(max_length=63)
    domain_type   = models.CharField(
                      max_length=10,
                      choices=[('subdomain', 'Subdomain'), ('custom', 'Custom Domain')],
                    )
    is_valid  = models.BooleanField(default=True)
    cached_at = models.DateTimeField(auto_now=True)
    hit_count = models.PositiveBigIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=['hostname', 'is_valid'])]

    def __str__(self):
        return f"{self.hostname} → schema:{self.tenant_schema} valid={self.is_valid}"


# ─────────────────────────────────────────────
# 12. ACME CHALLENGE STORE
# ─────────────────────────────────────────────
class ACMEChallenge(models.Model):
    """
    HTTP-01 ACME challenges served by Django during Let's Encrypt SSL validation.
    Django serves: GET /.well-known/acme-challenge/<token>
    Returns: key_auth value.
    Challenges expire after ~10 minutes; Celery cleans up stale rows.
    """

    custom_domain = models.ForeignKey(CustomDomain, on_delete=models.CASCADE, related_name='acme_challenges')
    token         = models.CharField(max_length=128, unique=True)
    key_auth      = models.CharField(max_length=512)  # token.account_thumbprint
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    expires_at    = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=['token', 'is_active'])]

    def __str__(self):
        return f"ACME:{self.custom_domain.domain} token={self.token[:12]}..."

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at


from .commerce_models import *  # noqa: E402,F401,F403
