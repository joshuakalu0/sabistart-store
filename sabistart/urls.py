from django.contrib import admin
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
from system.account.worker_views import worker_migrate_endpoint, tenant_migration_webhook_callback
from system.account.api_views import tenant_status_api
from system.account.tenant_sso_views import tenant_sso_login

urlpatterns = [
    path('admin/', admin.site.urls),
    path('favicon.ico', favicon.favicon, name='favicon'),
    path('deployz/', deploy_status.deployz, name='deployz'),
    path('healthz/', health.healthz, name='healthz'),
    path('readyz/', health.readyz, name='readyz'),
    path('platform/', include(('system.account.urls', 'system.account'), namespace='platform')),
    path('platform/payments/', include(('system.system_pay.urls', 'system.system_pay'), namespace='platform_payments')),
    path('platform/features/', include(('system.feature_marketplace.urls', 'system.feature_marketplace'), namespace='platform_features')),
    path('platform/themes/', include(('system.theme_marketplace.urls', 'system.theme_marketplace'), namespace='platform_themes')),
    path('platform/domains/', include(('dashboard.domain.platform_urls', 'dashboard.domain'), namespace='platform_domains')),
    path('.well-known/acme-challenge/<str:token>/', domain_views.acme_challenge, name='acme_challenge'),
    path('api/v1/tenants/status/', tenant_status_api, name='tenant_status_api'),
    path('api/v1/tenants/<str:tenant_id>/status/', tenant_status_api, name='tenant_status_by_id'),
    path('api/v1/tenants/migration-callback/', tenant_migration_webhook_callback, name='tenant_migration_callback'),
    path('api/v1/worker/migrate/', worker_migrate_endpoint, name='worker_migrate_endpoint'),
    path('account/auth/sso/', tenant_sso_login, name='tenant_sso_login'),
    path('dashboard/', include('dashboard.urls')),
    path('', include('public.storefront.urls')),
]


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
