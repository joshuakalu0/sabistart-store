from django.urls import path, include
from django.shortcuts import redirect


def dashboard_root_redirect(request):
    return redirect('/dashboard/admin/')


app_name = 'dashboard'

urlpatterns = [
    path('', dashboard_root_redirect, name='root'),
    # Dynamic prefix pattern - validates against database
    path('<prefix>/', include([

        path('', include('dashboard.home.urls'), ),
        path('products/', include('dashboard.product_settings.urls')),
        # path('settings/', include('dashboard.settings.urls')),
        path('theme_settings/', include('dashboard.store_settings.urls')),
        path('categories/', include('dashboard.categories_settings.urls')),
        path('users/', include('dashboard.user_s.urls', namespace='user_settings')),
        path('pos/', include('dashboard.pos.urls', namespace='pos')),
        path('pricing/', include('dashboard.pricing.urls', namespace='pricing')),
        path('payments/', include('dashboard.payments_tenant.urls', namespace='payments_tenant')),
        path('analytics/', include('dashboard.analytics.urls', namespace='analytics')),
        path('marketplace/', include('dashboard.feature_marketplace.urls', namespace='feature_marketplace')),
        path('monitoring/', include('dashboard.monitoring.urls', namespace='monitoring')),
        path('themes/', include('dashboard.theme_manager.urls', namespace='themes')),
        path('content/', include('dashboard.content_manager.urls', namespace='content_manager')),
        path('domains/', include('dashboard.domain.urls', namespace='domain')),
        path('notifications/', include('dashboard.notification.urls')),
    ])),
    # path('<str:prefix>/', include([
    #     path('', include('dashboard.home.urls')),
    #     path('products/', include('dashboard.products.urls')),
    #     path('settings/', include('dashboard.settings.urls')),
    # ])),
]
