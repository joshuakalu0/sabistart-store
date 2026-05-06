"""
URL configuration for sabistart_store project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.urls import re_path
from dashboard.domain import views as domain_views
from sabistart_store import health
from sabistart_store.media_proxy import media_proxy

urlpatterns = [
    path('admin/', admin.site.urls),
    path("healthz/", health.healthz, name="healthz"),
    path("readyz/", health.readyz, name="readyz"),

    # Platform-level URLs (public schema)
    # Use 'platform' namespace for platform URLs
    path('platform/', include(('system.account.urls',
         'system.account'), namespace='platform')),
    path('platform/payments/', include(('system.system_pay.urls', 'system.system_pay'), namespace='platform_payments')),
    path('platform/features/', include(('system.feature_marketplace.urls', 'system.feature_marketplace'), namespace='platform_features')),
    path('platform/themes/', include(('system.theme_marketplace.urls', 'system.theme_marketplace'), namespace='platform_themes')),
    path('.well-known/acme-challenge/<str:token>/', domain_views.acme_challenge, name='acme_challenge'),

    # Tenant storefront URLs
    path('', include('public.storefront.urls')),

    # Dashboard URLs
    path('dashboard/', include('dashboard.urls')),
]

using_vercel_blob_media = (
    settings.STORAGES.get("default", {}).get("BACKEND")
    == "sabistart_store.storage_backends.VercelBlobStorage"
)

if using_vercel_blob_media:
    urlpatterns += [
        re_path(r"^media/(?P<path>.*)$", media_proxy, name="media_proxy"),
    ]
elif settings.DEBUG:
    # Serve media files during development
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
    # Add explicit media serving for tenant-aware storage
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {
            'document_root': settings.MEDIA_ROOT,
        }),
    ]

handler404 = 'public.home.views.custom_404_view'
handler500 = 'public.home.views.custom_500_view'
