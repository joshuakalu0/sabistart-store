"""
system/account/sso.py
=====================
Subdomain Single Sign-On (SSO) & Tenant Admin Auto-Provisioning Service.

Once 100% of tenant schema migrations are complete:
1. Ensures the tenant owner is provisioned as an active superuser/admin TenantUser
   inside their isolated tenant schema.
2. Generates secure single-use SSO tickets for seamless transition from platform to
   custom tenant subdomains without re-entering credentials.
3. Resolves full subdomain URLs for cross-domain browser redirection.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.cache import cache
from django_tenants.utils import schema_context

logger = logging.getLogger("sabistart.account.sso")

SSO_TICKET_PREFIX = "tenant_sso_ticket"
SSO_TICKET_TTL = 300  # 5 minutes expiry


class TenantSchemaNotReady(Exception):
    """Raised when a tenant schema is not yet fully migrated."""


def ensure_tenant_admin_user(shop, user) -> Any:
    """
    Provisions or updates the PlatformUser owner as a full Admin / Superuser
    TenantUser inside the tenant's isolated schema.
    Raises TenantSchemaNotReady if the schema tables have not been migrated yet.
    """
    if not shop or not user:
        return None

    try:
        from public.userauth.models import TenantUser

        with schema_context(shop.schema_name):
            email = (getattr(user, "email", "") or "").strip().lower()
            if not email:
                return None
            tenant_user = TenantUser.objects.filter(email__iexact=email).first()

            if not tenant_user:
                tenant_user = TenantUser(
                    email=email,
                    first_name=getattr(user, "first_name", "") or "",
                    last_name=getattr(user, "last_name", "") or "",
                    phone=getattr(user, "phone", "") or "",
                    is_staff=True,
                    is_superuser=True,
                    user_type=TenantUser.UserType.STAFF,
                    account_status=TenantUser.AccountStatus.ACTIVE,
                    is_verified=True,
                    platform_user_id=str(getattr(user, "id", "")),
                )
                if hasattr(user, "password") and user.password:
                    tenant_user.password = user.password
                else:
                    tenant_user.set_unusable_password()
                tenant_user.save()
                logger.info("[SSO] Created tenant admin user '%s' in schema '%s'.", email, shop.schema_name)
            else:
                updated = False
                if not tenant_user.is_staff or not tenant_user.is_superuser:
                    tenant_user.is_staff = True
                    tenant_user.is_superuser = True
                    tenant_user.user_type = TenantUser.UserType.STAFF
                    tenant_user.account_status = TenantUser.AccountStatus.ACTIVE
                    tenant_user.is_verified = True
                    updated = True
                if hasattr(user, "password") and user.password and tenant_user.password != user.password:
                    tenant_user.password = user.password
                    updated = True
                if updated:
                    tenant_user.save(update_fields=["is_staff", "is_superuser", "user_type", "account_status", "is_verified", "password"])
                    logger.info("[SSO] Updated tenant admin user permissions for '%s' in schema '%s'.", email, shop.schema_name)

            return tenant_user
    except Exception as exc:
        err = str(exc).lower()
        if any(phrase in err for phrase in (
            "relation", "does not exist", "no such table", "undefined table",
        )):
            raise TenantSchemaNotReady(
                f"Tenant schema '{shop.schema_name}' tables are not ready yet: {exc}"
            ) from exc
        logger.warning("[SSO] Could not ensure tenant admin user in schema '%s': %s", getattr(shop, "schema_name", ""), exc)
        return None



def generate_tenant_sso_ticket(shop, user) -> str:
    """
    Generates a cryptographically secure, single-use SSO ticket for cross-subdomain auth.
    """
    if not shop or not user:
        return ""

    ticket = secrets.token_urlsafe(32)
    payload = {
        "user_id": str(user.id),
        "email": user.email.lower().strip(),
        "schema_name": shop.schema_name,
    }
    try:
        cache.set(f"{SSO_TICKET_PREFIX}:{ticket}", payload, timeout=SSO_TICKET_TTL)
        logger.debug("[SSO] Generated SSO ticket for '%s' -> schema '%s'.", user.email, shop.schema_name)
    except Exception as exc:
        logger.warning("[SSO] Failed to cache SSO ticket: %s", exc)
    return ticket


def consume_tenant_sso_ticket(ticket: str, current_schema: str) -> Optional[Dict[str, Any]]:
    """
    Validates and immediately deletes an SSO ticket (guaranteeing single-use).
    Returns the payload if valid and matching the current tenant schema.
    """
    ticket = (ticket or "").strip()
    if not ticket:
        return None

    cache_key = f"{SSO_TICKET_PREFIX}:{ticket}"
    try:
        payload = cache.get(cache_key)
        if payload is not None:
            cache.delete(cache_key)  # Atomically consume
            if payload.get("schema_name") == current_schema.lower().strip():
                logger.info("[SSO] Consumed valid SSO ticket for '%s' in schema '%s'.", payload.get("email"), current_schema)
                return payload
            else:
                logger.warning(
                    "[SSO] SSO ticket schema mismatch: expected '%s', got '%s'.",
                    current_schema, payload.get("schema_name"),
                )
    except Exception as exc:
        logger.warning("[SSO] Error consuming SSO ticket: %s", exc)
    return None


def get_tenant_subdomain_redirect_url(
    shop,
    request=None,
    user=None,
    next_path: str = "",
) -> str:
    """
    Computes the complete redirect URL to the tenant storefront/admin dashboard,
    injecting a secure SSO ticket if an authenticated user is provided.
    """
    if not shop:
        return "/platform/"

    schema_name = shop.schema_name
    primary_domain = shop.domains.filter(is_primary=True).first() if hasattr(shop, "domains") else None
    domain_name = primary_domain.domain if primary_domain else schema_name

    ticket = ""
    if user and getattr(user, "is_authenticated", False):
        try:
            ensure_tenant_admin_user(shop, user)
        except TenantSchemaNotReady:
            raise
        except Exception as exc:
            logger.warning("[SSO] ensure_tenant_admin_user failed in get_tenant_subdomain_redirect_url: %s", exc)
        try:
            ticket = generate_tenant_sso_ticket(shop, user)
        except Exception as exc:
            logger.warning("[SSO] generate_tenant_sso_ticket failed: %s", exc)

    # Determine scheme and host
    protocol = "https"
    if request and not request.is_secure() and settings.DEBUG:
        protocol = "http"

    platform_cname = getattr(settings, "PLATFORM_CNAME", "localhost")
    root_domain = (getattr(settings, "SUBDOMAIN_SUFFIX", "") or platform_cname).lstrip(".")

    # If domain_name is just the subdomain without dots (e.g. 'mystore')
    if "." not in domain_name:
        host = f"{domain_name}.{root_domain}"
    else:
        host = domain_name

    port_suffix = ""
    if request:
        try:
            host_header = request.get_host()
            if ":" in host_header:
                port = host_header.split(":")[-1]
                if port not in ("80", "443"):
                    port_suffix = f":{port}"
        except Exception:
            pass

    base_url = f"{protocol}://{host}{port_suffix}"

    if ticket:
        from urllib.parse import urlencode
        params = {'ticket': ticket}
        if not next_path:
            next_path = '/dashboard/'
        if next_path:
            params['next'] = next_path
        return f"{base_url}/account/auth/sso/?{urlencode(params)}"

    return f"{base_url}{next_path or '/dashboard/'}"

