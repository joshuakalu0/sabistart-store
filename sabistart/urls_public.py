"""
sabistart/urls_public.py
========================
Platform domain (main site) URL configuration.
Loaded exclusively when the request arrives on the PLATFORM domain
(e.g. sabistart.com, localhost, direct IP).

NEVER include:
  - Tenant-storefront URLs (those live in urls.py / ROOT_URLCONF)
  - Tenant account/auth (customer auth lives in public.userauth on tenant subdomains)
  - public.storefront.urls (those belong to per-tenant subdomains)

Routing summary:
  /                           → platform landing page
  /platform/                  → platform admin dashboard, auth, onboarding, stores, users
  /platform/payments/         → platform payment management
  /platform/features/         → feature marketplace (platform)
  /platform/themes/           → theme marketplace (platform)
  /platform/domains/          → custom domain management (platform)
  /admin/                     → Django admin (platform only)
  /__monitoring/              → internal monitoring
  /.well-known/acme-challenge/ → ACME/Let's Encrypt (needed on platform too)
  /api/v1/tenants/status/     → platform status API
  /api/v1/tenants/migration-callback/ → worker webhook
  /api/v1/worker/migrate/     → worker migration trigger
"""

from django.urls import path, include
from django.contrib import admin
from django.conf import settings
from django.urls import re_path
from django.views.generic import RedirectView
from dashboard.domain import views as domain_views
from sabistart import deploy_status
from sabistart import favicon
from sabistart import health
from sabistart.media_proxy import media_proxy
from system.account.api_views import tenant_status_api
from system.account.worker_views import (
    tenant_migration_webhook_callback,
    worker_migrate_endpoint,
)

urlpatterns = [
    # ── Platform landing ──────────────────────────────────────────────────────
    path('', include(('public.landing.urls', 'public.landing'), namespace='landing')),

    # ── Django admin (platform superadmin only) ──────────────────────────────
    path('admin/', admin.site.urls),

    # ── Utility / health endpoints ────────────────────────────────────────────
    path("favicon.ico", favicon.favicon, name="favicon"),
    path("deployz/", deploy_status.deployz, name="deployz"),
    path("healthz/", health.healthz, name="healthz"),
    path("readyz/", health.readyz, name="readyz"),

    # ── Platform admin, onboarding, stores & users (all under /platform/) ────
    path(
        'platform/',
        include(('system.account.urls', 'system.account'), namespace='platform'),
    ),
    path('platform/payments/', include(('system.system_pay.urls', 'system.system_pay'), namespace='platform_payments')),
    path('platform/features/', include(('system.feature_marketplace.urls', 'system.feature_marketplace'), namespace='platform_features')),
    path('platform/themes/', include(('system.theme_marketplace.urls', 'system.theme_marketplace'), namespace='platform_themes')),
    path('platform/domains/', include(('dashboard.domain.platform_urls', 'dashboard.domain'), namespace='platform_domains')),
    path('dashboard/', include('dashboard.urls')),

    # ── Internal monitoring ───────────────────────────────────────────────────
    path('__monitoring/', include(('public.monitoring.urls', 'public.monitoring'), namespace='monitoring')),

    # ── ACME / Let's Encrypt (platform domain may also need this) ────────────
    path('.well-known/acme-challenge/<str:token>/', domain_views.acme_challenge, name='acme_challenge'),

    # ── Platform status & worker API endpoints ───────────────────────────────
    path('api/v1/tenants/status/', tenant_status_api, name='tenant_status_api'),
    path('api/v1/tenants/<str:tenant_id>/status/', tenant_status_api, name='tenant_status_by_id'),
    path('api/v1/tenants/migration-callback/', tenant_migration_webhook_callback, name='tenant_migration_callback'),
    path('api/v1/worker/migrate/', worker_migrate_endpoint, name='worker_migrate_endpoint'),

    # ── Legacy /account/ and /accounts/ redirects: redirect old platform links to /platform/
    path('account/login/', RedirectView.as_view(pattern_name='platform:login', permanent=True), name='account_login_redirect'),
    path('account/logout/', RedirectView.as_view(pattern_name='platform:logout', permanent=False), name='account_logout_redirect'),
    path('account/register/', RedirectView.as_view(pattern_name='platform:register', permanent=True), name='account_register_redirect'),
    path('account/register/provisioning/', RedirectView.as_view(pattern_name='platform:onboarding_provisioning', permanent=True), name='account_provisioning_redirect'),
    path('account/', RedirectView.as_view(url='/platform/', permanent=False), name='account_catchall_redirect'),
    path('accounts/login/', RedirectView.as_view(pattern_name='platform:login', permanent=False)),
    path('accounts/logout/', RedirectView.as_view(pattern_name='platform:logout', permanent=False)),
    path('accounts/', RedirectView.as_view(url='/platform/', permanent=False)),
]

if settings.STORAGES.get("default", {}).get("BACKEND") == "sabistart.storage_backends.VercelBlobStorage":
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", media_proxy, name="media_proxy"),
    ]
