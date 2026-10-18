from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.urls import re_path
from dashboard.domain import views as domain_views
from sabistart import deploy_status
from sabistart import favicon
from sabistart import health
from sabistart.media_proxy import media_proxy
from system.account.tenant_sso_views import tenant_sso_login

# ============================================================
# TENANT URL CONF  (sabistart/urls.py)
# Loaded for every TENANT subdomain / custom domain.
#
# ⚠  Platform-admin routes (/platform/, /account/, worker
#    endpoints, etc.) must NEVER appear here.
#    They live exclusively in urls_public.py (platform domain).
# ============================================================

urlpatterns = [
    # ── Health / utility (safe on any domain) ────────────────
    path('favicon.ico', favicon.favicon, name='favicon'),
    path('deployz/', deploy_status.deployz, name='deployz'),
    path('healthz/', health.healthz, name='healthz'),
    path('readyz/', health.readyz, name='readyz'),

    # ── ACME / Let's Encrypt challenge (needed for custom domains) ──
    path('.well-known/acme-challenge/<str:token>/', domain_views.acme_challenge, name='acme_challenge'),

    # ── Tenant SSO login (platform → tenant handshake only) ──
    path('account/auth/sso/', tenant_sso_login, name='tenant_sso_login'),

    # ── Tenant store dashboard ────────────────────────────────
    path('dashboard/', include('dashboard.urls')),

    # ── Tenant storefront (public-facing store pages) ─────────
    path('', include('public.storefront.urls')),
]

# Media serving
using_vercel_blob_media = (
    settings.STORAGES.get('default', {}).get('BACKEND')
    == 'sabistart.storage_backends.VercelBlobStorage'
)

if using_vercel_blob_media:
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', media_proxy, name='media_proxy'),
    ]
elif settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]

handler404 = 'public.home.views.custom_404_view'
handler500 = 'public.home.views.custom_500_view'
