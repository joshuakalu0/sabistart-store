from django.urls import path, include

app_name = 'dashboard'

urlpatterns = [
    # Dynamic prefix pattern - validates against database
    path('<prefix>/', include([
        path('', include('dashboard.home.urls'), ),
        path('products/', include('dashboard.product_settings.urls')),
        path('settings/', include('dashboard.settings.urls')),
        path('categories/', include('dashboard.categories_settings.urls')),
    ])),
    # path('<str:prefix>/', include([
    #     path('', include('dashboard.home.urls')),
    #     path('products/', include('dashboard.products.urls')),
    #     path('settings/', include('dashboard.settings.urls')),
    # ])),
]
