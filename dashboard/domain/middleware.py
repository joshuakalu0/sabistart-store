import ipaddress
import logging
from types import SimpleNamespace

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponseNotFound, HttpResponseRedirect
from django_tenants.middleware.main import TenantMainMiddleware


logger = logging.getLogger("dashboard.domain.middleware")

CACHE_TTL = getattr(settings, "DOMAIN_RESOLUTION_CACHE_TTL", 300)


def _is_ip_address(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


class CustomDomainMiddleware(TenantMainMiddleware):
    """
    Extends django-tenants resolution with shared-schema custom domains.

    Resolution order:
    1. Native django-tenants lookup via parent middleware
    2. Redis cache
    3. Shared DB cache table
    4. Active custom domain lookup
    5. Pending-domain ACME challenge lookup
    6. Redirect rule
    """

    def process_request(self, request):
        from django.db import connection
        try:
            with connection.cursor() as cursor:
                cursor.execute('SET search_path = "public";')
        except Exception:
            pass
        connection.set_schema_to_public()

        hostname = self._get_hostname(request)
        request.hostname = hostname

        platform_cname = getattr(settings, "PLATFORM_CNAME", "localhost").lower().strip()
        platform_hosts = [h.lower().strip() for h in getattr(settings, "PLATFORM_HOSTS", [])]
        normalized_host = hostname.lower().strip()
        is_platform_host = (
            normalized_host in {"localhost", "127.0.0.1", "0.0.0.0", "[::1]", "testserver"}
            or _is_ip_address(normalized_host)
            or (platform_cname and normalized_host == platform_cname)
            or (platform_cname and normalized_host == f"www.{platform_cname}")
            or normalized_host in platform_hosts
        )

        if is_platform_host:
            from django.db import connection
            from django_tenants.utils import get_public_schema_name, get_tenant_model

            connection.set_schema_to_public()
            public_schema_name = get_public_schema_name()
            public_tenant = get_tenant_model().objects.filter(schema_name=public_schema_name).first()
            request.tenant = public_tenant or SimpleNamespace(schema_name=public_schema_name)
            request.urlconf = getattr(settings, "PUBLIC_SCHEMA_URLCONF", None)
            self.setup_url_routing(request, force_public=True)
            return None

        try:
            return super().process_request(request)
        except Http404:
            pass

        cached = self._redis_get(hostname)
        if cached:
            logger.debug("[middleware] Redis cache hit for %s", hostname)
            return self._resolve_by_schema(request, cached["tenant_schema"], hostname)

        from dashboard.domain.models import ACMEChallenge, CustomDomain, DomainRedirectRule, DomainResolutionCache

        try:
            entry = DomainResolutionCache.objects.get(hostname=hostname, is_valid=True)
            DomainResolutionCache.objects.filter(pk=entry.pk).update(hit_count=entry.hit_count + 1)
            self._redis_set(
                hostname,
                {
                    "tenant_id": entry.tenant_id,
                    "tenant_schema": entry.tenant_schema,
                },
            )
            logger.debug("[middleware] DB cache hit for %s", hostname)
            return self._resolve_by_schema(request, entry.tenant_schema, hostname)
        except DomainResolutionCache.DoesNotExist:
            pass

        try:
            custom_domain = (
                CustomDomain.objects.select_related("tenant")
                .get(domain=hostname, status=CustomDomain.Status.ACTIVE)
            )
            tenant = custom_domain.tenant
            DomainResolutionCache.objects.update_or_create(
                hostname=hostname,
                defaults={
                    "tenant_id": tenant.id,
                    "tenant_schema": tenant.schema_name,
                    "domain_type": "custom",
                    "is_valid": True,
                },
            )
            self._redis_set(
                hostname,
                {
                    "tenant_id": tenant.id,
                    "tenant_schema": tenant.schema_name,
                },
            )
            logger.info("[middleware] Resolved custom domain %s -> %s", hostname, tenant.schema_name)
            return self._set_tenant(request, tenant)
        except CustomDomain.DoesNotExist:
            pass

        if request.path.startswith("/.well-known/acme-challenge/"):
            token = request.path.rstrip("/").rsplit("/", 1)[-1]
            challenge = (
                ACMEChallenge.objects.select_related("custom_domain__tenant")
                .filter(token=token, is_active=True, custom_domain__domain=hostname)
                .first()
            )
            if challenge is not None:
                logger.info("[middleware] Resolved ACME challenge for %s", hostname)
                return self._set_tenant(request, challenge.custom_domain.tenant)

        try:
            rule = (
                DomainRedirectRule.objects.select_related("to_domain")
                .get(from_domain=hostname, is_active=True)
            )
            if rule.to_domain and rule.to_domain.status == rule.to_domain.Status.ACTIVE:
                target = f"https://{rule.to_domain.domain}"
                if rule.preserve_path:
                    target += request.get_full_path()
                response = HttpResponseRedirect(target)
                response.status_code = int(rule.redirect_type)
                logger.info("[middleware] Redirect %s -> %s [%s]", hostname, target, rule.redirect_type)
                return response
        except DomainRedirectRule.DoesNotExist:
            pass

        logger.warning("[middleware] Unresolved hostname: %s, falling back to default tenant", hostname)
        return self._fallback_to_default_tenant(request, hostname)

    def _fallback_to_default_tenant(self, request, hostname):
        from django_tenants.utils import get_tenant_model

        tenant_model = get_tenant_model()
        default_schema = getattr(settings, "DEFAULT_TENANT_SCHEMA", "sho")
        try:
            tenant = tenant_model.objects.get(schema_name=default_schema)
        except tenant_model.DoesNotExist:
            return self._domain_not_found(hostname)

        logger.info("[middleware] Fallback: %s -> %s", hostname, tenant.schema_name)
        return self._set_tenant(request, tenant)

    def _get_hostname(self, request):
        try:
            host = request.get_host().lower().strip()
            return host.split(":", 1)[0]
        except Exception:
            raw = request.META.get("HTTP_HOST", "") or request.META.get("SERVER_NAME", "localhost")
            return raw.lower().strip().split(":", 1)[0]

    def _redis_get(self, hostname):
        try:
            return cache.get(f"domain_resolve:{hostname}")
        except Exception as exc:
            logger.warning("[middleware] Redis get failed for %s: %s", hostname, exc)
            return None

    def _redis_set(self, hostname, data):
        try:
            cache.set(f"domain_resolve:{hostname}", data, timeout=CACHE_TTL)
        except Exception as exc:
            logger.warning("[middleware] Redis set failed for %s: %s", hostname, exc)

    def _resolve_by_schema(self, request, schema_name, hostname):
        from django_tenants.utils import get_tenant_model

        tenant_model = get_tenant_model()
        try:
            tenant = tenant_model.objects.get(schema_name=schema_name)
        except tenant_model.DoesNotExist:
            from dashboard.domain.models import DomainResolutionCache

            DomainResolutionCache.objects.filter(hostname=hostname).update(is_valid=False)
            cache.delete(f"domain_resolve:{hostname}")
            logger.error("[middleware] Stale cache entry for %s -> %s", hostname, schema_name)
            return self._domain_not_found(hostname)
        return self._set_tenant(request, tenant)

    def _set_tenant(self, request, tenant):
        from django.db import connection

        request.tenant = tenant
        request.urlconf = getattr(tenant, "urlconf", None)
        connection.set_tenant(tenant)
        self.setup_url_routing(request)
        return None

    def _domain_not_found(self, hostname):
        return HttpResponseNotFound(
            "<html><body>"
            "<h1>Domain not found</h1>"
            f"<p><strong>{hostname}</strong> is not associated with any store on this platform.</p>"
            "</body></html>"
        )
