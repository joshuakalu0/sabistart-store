"""
public/storefront/tenant_urls.py
===============================
URL configuration for tenant storefront pages.

These are the public-facing pages of a tenant store.
"""

from django.urls import path, include
from django.contrib import admin
from django.conf import settings
from django.urls import re_path
from dashboard.domain import views as domain_views
from sabistart_store import health
from sabistart_store.media_proxy import media_proxy

# app_name = ''

urlpatterns = [
    path('', include(('public.landing.urls', 'public.landing'), namespace='landing')),
    path('admin/', admin.site.urls),
    path("healthz/", health.healthz, name="healthz"),
    path("readyz/", health.readyz, name="readyz"),
    path(
        'platform/',
        include(('system.account.urls', 'system.account'), namespace='platform'),
    ),
    path('platform/payments/', include(('system.system_pay.urls', 'system.system_pay'), namespace='platform_payments')),
    path('platform/features/', include(('system.feature_marketplace.urls', 'system.feature_marketplace'), namespace='platform_features')),
    path('platform/themes/', include(('system.theme_marketplace.urls', 'system.theme_marketplace'), namespace='platform_themes')),
    path('dashboard/', include('dashboard.urls')),
    path('account/', include('system.account.urls', namespace='tenant')),
    path('__monitoring/', include(('public.monitoring.urls', 'public.monitoring'), namespace='monitoring')),
    path('.well-known/acme-challenge/<str:token>/', domain_views.acme_challenge, name='acme_challenge'),
]

if settings.STORAGES.get("default", {}).get("BACKEND") == "sabistart_store.storage_backends.VercelBlobStorage":
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", media_proxy, name="media_proxy"),
    ]
