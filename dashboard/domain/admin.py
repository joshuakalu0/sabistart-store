# domains/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    CustomDomain, DomainDNSRecord, DomainVerificationAttempt,
    SSLCertificate, SSLProvisioningLog, DomainRedirectRule,
    DomainEventLog, DomainHealthCheck, DomainQuota,
    NginxVhostConfig, DomainResolutionCache, ACMEChallenge,
)


# ── Inlines ───────────────────────────────────────────────────────────────────

class DomainDNSRecordInline(admin.TabularInline):
    model      = DomainDNSRecord
    extra      = 0
    readonly_fields = ('created_at',)


class DomainVerificationAttemptInline(admin.TabularInline):
    model       = DomainVerificationAttempt
    extra       = 0
    readonly_fields = (
        'attempted_at', 'result', 'resolved_value',
        'expected_value', 'error_message', 'resolver_used',
    )
    can_delete  = False
    max_num     = 0  # read-only — no adding manually
    ordering    = ('-attempted_at',)


class SSLCertificateInline(admin.StackedInline):
    model       = SSLCertificate
    extra       = 0
    readonly_fields = (
        'issued_at', 'expires_at', 'days_until_expiry',
        'needs_renewal', 'created_at', 'updated_at',
    )


class DomainEventLogInline(admin.TabularInline):
    model       = DomainEventLog
    extra       = 0
    readonly_fields = ('event_type', 'actor', 'message', 'metadata', 'created_at')
    can_delete  = False
    max_num     = 0
    ordering    = ('-created_at',)


class SSLProvisioningLogInline(admin.TabularInline):
    model       = SSLProvisioningLog
    extra       = 0
    readonly_fields = ('step', 'success', 'message', 'metadata', 'created_at')
    can_delete  = False
    max_num     = 0
    ordering    = ('created_at',)


# ── CustomDomain ──────────────────────────────────────────────────────────────

@admin.register(CustomDomain)
class CustomDomainAdmin(admin.ModelAdmin):
    list_display  = (
        'domain', 'tenant', 'status_badge', 'ssl_badge',
        'is_primary', 'is_root_domain', 'verified_at', 'created_at',
    )
    list_filter   = ('status', 'ssl_status', 'is_primary', 'verification_method')
    search_fields = ('domain', 'tenant__name', 'tenant__schema_name')
    readonly_fields = (
        'id', 'verification_token', 'txt_record_name', 'txt_record_value',
        'is_root_domain', 'verified_at', 'created_at', 'updated_at',
    )
    inlines = [
        DomainDNSRecordInline,
        DomainVerificationAttemptInline,
        SSLCertificateInline,
        DomainEventLogInline,
    ]
    actions = [
        'trigger_verification',
        'trigger_ssl_provisioning',
        'suspend_domains',
        'activate_domains',
    ]
    fieldsets = (
        ('Identity', {
            'fields': ('id', 'tenant', 'domain', 'is_primary', 'status', 'is_root_domain')
        }),
        ('Verification', {
            'fields': (
                'verification_method', 'verification_token',
                'txt_record_name', 'txt_record_value', 'verified_at',
            )
        }),
        ('SSL', {
            'fields': ('ssl_status', 'ssl_provider', 'ssl_expires_at', 'ssl_cert_path', 'ssl_key_path')
        }),
        ('Meta', {
            'fields': ('notes', 'created_at', 'updated_at')
        }),
    )

    # ── Badges ────────────────────────────────────────────────────────────────

    def status_badge(self, obj):
        colors = {
            'pending':      '#f59e0b',
            'dns_checking': '#3b82f6',
            'dns_verified': '#8b5cf6',
            'ssl_pending':  '#f97316',
            'active':       '#10b981',
            'failed':       '#ef4444',
            'suspended':    '#6b7280',
            'removed':      '#1f2937',
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="background:{};color:white;padding:2px 10px;'
            'border-radius:4px;font-size:11px;font-weight:bold">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def ssl_badge(self, obj):
        colors = {
            'none':         '#6b7280',
            'provisioning': '#f59e0b',
            'active':       '#10b981',
            'expiring_soon':'#f97316',
            'expired':      '#ef4444',
            'failed':       '#ef4444',
        }
        color = colors.get(obj.ssl_status, '#6b7280')
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;'
            'border-radius:4px;font-size:11px">SSL: {}</span>',
            color, obj.ssl_status.upper()
        )
    ssl_badge.short_description = 'SSL'

    def is_root_domain(self, obj):
        return obj.is_root_domain
    is_root_domain.boolean      = True
    is_root_domain.short_description = 'Root Domain'

    # ── Admin Actions ─────────────────────────────────────────────────────────

    @admin.action(description='🔍 Trigger DNS verification')
    def trigger_verification(self, request, queryset):
        from .tasks import verify_domain_dns
        count = 0
        for domain in queryset.exclude(status=CustomDomain.Status.ACTIVE):
            verify_domain_dns.delay(str(domain.id))
            count += 1
        self.message_user(request, f"Verification triggered for {count} domain(s).")

    @admin.action(description='🔒 Trigger SSL provisioning')
    def trigger_ssl_provisioning(self, request, queryset):
        from .tasks import provision_ssl_certificate
        count = 0
        for domain in queryset.filter(status=CustomDomain.Status.DNS_VERIFIED):
            provision_ssl_certificate.delay(str(domain.id))
            count += 1
        self.message_user(request, f"SSL provisioning triggered for {count} domain(s).")

    @admin.action(description='⏸ Suspend selected domains')
    def suspend_domains(self, request, queryset):
        updated = queryset.update(status=CustomDomain.Status.SUSPENDED)
        self.message_user(request, f"{updated} domain(s) suspended.")

    @admin.action(description='▶️ Activate selected domains')
    def activate_domains(self, request, queryset):
        updated = queryset.update(status=CustomDomain.Status.ACTIVE)
        self.message_user(request, f"{updated} domain(s) activated.")


# ── SSLCertificate ────────────────────────────────────────────────────────────

@admin.register(SSLCertificate)
class SSLCertificateAdmin(admin.ModelAdmin):
    list_display  = (
        'custom_domain', 'status', 'provider', 'challenge_type',
        'issued_at', 'expires_at', 'expiry_badge', 'auto_renew',
    )
    list_filter   = ('status', 'provider', 'challenge_type', 'auto_renew')
    readonly_fields = (
        'issued_at', 'expires_at', 'days_until_expiry',
        'needs_renewal', 'created_at', 'updated_at',
    )
    inlines = [SSLProvisioningLogInline]

    def expiry_badge(self, obj):
        d = obj.days_until_expiry
        if d is None:
            return '—'
        color = '#ef4444' if d < 7 else '#f59e0b' if d < 30 else '#10b981'
        return format_html(
            '<span style="color:{};font-weight:bold">{} days</span>', color, d
        )
    expiry_badge.short_description = 'Expires In'


# ── DomainHealthCheck ─────────────────────────────────────────────────────────

@admin.register(DomainHealthCheck)
class DomainHealthCheckAdmin(admin.ModelAdmin):
    list_display  = (
        'custom_domain', 'checked_at', 'dns_resolves', 'ssl_valid',
        'http_reachable', 'response_code', 'response_time_ms', 'resolved_ip',
    )
    list_filter   = ('dns_resolves', 'ssl_valid', 'http_reachable')
    readonly_fields = ('checked_at',)


# ── DomainQuota ───────────────────────────────────────────────────────────────

@admin.register(DomainQuota)
class DomainQuotaAdmin(admin.ModelAdmin):
    list_display  = (
        'tenant', 'max_custom_domains', 'domains_used',
        'has_capacity', 'ssl_auto_provision', 'wildcard_ssl_allowed',
    )
    readonly_fields = ('domains_used', 'has_capacity', 'updated_at')


# ── DomainResolutionCache ─────────────────────────────────────────────────────

@admin.register(DomainResolutionCache)
class DomainResolutionCacheAdmin(admin.ModelAdmin):
    list_display  = ('hostname', 'tenant_schema', 'domain_type', 'is_valid', 'hit_count', 'cached_at')
    list_filter   = ('domain_type', 'is_valid')
    search_fields = ('hostname', 'tenant_schema')
    readonly_fields = ('cached_at', 'hit_count')
    actions = ['invalidate_cache', 'revalidate_cache']

    @admin.action(description='❌ Invalidate selected cache entries')
    def invalidate_cache(self, request, queryset):
        updated = queryset.update(is_valid=False)
        self.message_user(request, f"{updated} cache entries invalidated.")

    @admin.action(description='✅ Revalidate selected cache entries')
    def revalidate_cache(self, request, queryset):
        updated = queryset.update(is_valid=True)
        self.message_user(request, f"{updated} cache entries revalidated.")


# ── DomainEventLog ────────────────────────────────────────────────────────────

@admin.register(DomainEventLog)
class DomainEventLogAdmin(admin.ModelAdmin):
    list_display  = ('custom_domain', 'event_type', 'actor', 'message', 'created_at')
    list_filter   = ('event_type', 'actor')
    search_fields = ('custom_domain__domain', 'message')
    readonly_fields = ('created_at',)

    def has_add_permission(self, request):
        return False  # logs are system-generated only

    def has_change_permission(self, request, obj=None):
        return False  # immutable


# ── Remaining models (simple registration) ────────────────────────────────────

@admin.register(DomainDNSRecord)
class DomainDNSRecordAdmin(admin.ModelAdmin):
    list_display = ('custom_domain', 'record_type', 'host', 'value', 'purpose', 'ttl')
    list_filter  = ('record_type', 'purpose', 'is_required')


@admin.register(DomainRedirectRule)
class DomainRedirectRuleAdmin(admin.ModelAdmin):
    list_display = ('from_domain', 'to_domain', 'redirect_type', 'is_active', 'preserve_path')
    list_filter  = ('redirect_type', 'is_active')


@admin.register(NginxVhostConfig)
class NginxVhostConfigAdmin(admin.ModelAdmin):
    list_display = ('custom_domain', 'is_active', 'nginx_reloaded', 'applied_at', 'created_at')
    list_filter  = ('is_active', 'nginx_reloaded')
    readonly_fields = ('config_hash', 'created_at')


@admin.register(ACMEChallenge)
class ACMEChallengeAdmin(admin.ModelAdmin):
    list_display = ('custom_domain', 'token', 'is_active', 'created_at', 'expires_at')
    list_filter  = ('is_active',)
    readonly_fields = ('created_at',)


@admin.register(DomainVerificationAttempt)
class DomainVerificationAttemptAdmin(admin.ModelAdmin):
    list_display = ('custom_domain', 'result', 'resolver_used', 'attempted_at')
    list_filter  = ('result', 'resolver_used')
    readonly_fields = ('attempted_at',)


@admin.register(SSLProvisioningLog)
class SSLProvisioningLogAdmin(admin.ModelAdmin):
    list_display = ('certificate', 'step', 'success', 'message', 'created_at')
    list_filter  = ('step', 'success')
    readonly_fields = ('created_at',)
