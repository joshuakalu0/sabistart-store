"""
system/account/tenant_sso_views.py
====================================
Tenant-side SSO ticket consumer view.
This runs inside the TENANT schema (sabistart/urls.py, not urls_public.py).

When a user is redirected from the platform provisioning page after their
store is READY, they land on:
  https://<subdomain>.<platform_cname>/account/auth/sso/?ticket=<token>

This view:
1. Validates and consumes the SSO ticket (single-use, 5 min TTL)
2. Looks up or creates the TenantUser by email in the current tenant schema
3. Logs them into the tenant session
4. Redirects to the tenant dashboard (/dashboard/)
"""
import logging
from django.shortcuts import redirect
from django.contrib.auth import login
from django.http import HttpResponseBadRequest
from django.db import connection

logger = logging.getLogger('sabistart.account.tenant_sso')


def tenant_sso_login(request):
    """
    Consume an SSO ticket and log the user into this tenant schema.
    """
    ticket = request.GET.get('ticket', '').strip()
    next_path = request.GET.get('next', '/dashboard/').strip() or '/dashboard/'

    # Ensure next_path stays on-domain
    if not next_path.startswith('/'):
        next_path = '/dashboard/'

    if not ticket:
        logger.warning('[TenantSSO] No ticket provided.')
        return redirect('/dashboard/')

    # Get current tenant schema from the connection
    schema_name = getattr(connection, 'schema_name', 'public')
    if schema_name == 'public':
        logger.warning('[TenantSSO] SSO view called on public schema.')
        return redirect('/platform/login/')

    # Consume the SSO ticket
    try:
        from system.account.sso import consume_tenant_sso_ticket
        payload = consume_tenant_sso_ticket(ticket, schema_name)
    except Exception as exc:
        logger.warning('[TenantSSO] Error consuming SSO ticket: %s', exc)
        payload = None

    if not payload:
        logger.warning('[TenantSSO] Invalid or expired SSO ticket for schema %s.', schema_name)
        # Redirect to tenant login page if ticket invalid
        return redirect('/account/login/?next=' + next_path)

    email = payload.get('email', '').strip().lower()
    user_id = payload.get('user_id', '')

    if not email:
        logger.warning('[TenantSSO] SSO payload missing email.')
        return redirect('/dashboard/')

    # Find the TenantUser in the current schema
    try:
        from public.userauth.models import TenantUser
        tenant_user = TenantUser.objects.filter(email__iexact=email).first()

        if not tenant_user:
            # Try to find by platform_user_id
            if user_id:
                tenant_user = TenantUser.objects.filter(platform_user_id=user_id).first()

        if not tenant_user:
            logger.warning('[TenantSSO] No TenantUser found for email %s in schema %s', email, schema_name)
            return redirect('/dashboard/')

        # Log the tenant user in
        backend = 'django.contrib.auth.backends.ModelBackend'
        tenant_user.backend = backend
        login(request, tenant_user, backend=backend)
        logger.info('[TenantSSO] Logged in TenantUser %s in schema %s -> redirecting to %s', email, schema_name, next_path)
        return redirect(next_path)

    except Exception as exc:
        logger.exception('[TenantSSO] Error during SSO login for schema %s: %s', schema_name, exc)
        return redirect('/dashboard/')
