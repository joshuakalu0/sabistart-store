from django.urls import path, include

urlpatterns = [
    path('', include('public.home.urls', namespace='home')),
    path('', include('public.category.urls', namespace='category')),
    path('', include('public.product.urls', namespace='product')),
    path('account/', include('public.userauth.urls', namespace='tenant')),
    path('__monitoring/', include('public.monitoring.urls', namespace='monitoring')),
    path('search/', include('public.search.urls', namespace='search')),
    path('cart/', include('public.cart.urls', namespace='cart')),
    path('checkout/', include('public.checkout.urls', namespace='checkout')),
    path('promotions/', include('public.promotions.urls', namespace='promotions')),
    path('', include('public.shipping.urls', namespace='shipping')),
    path('', include('public.support.urls', namespace='support')),
    path('legal/', include('public.legal.urls', namespace='legal')),
    path('i18n/', include('public.i18n.urls', namespace='i18n')),
    path('b2b/', include('public.b2b.urls', namespace='b2b')),
    path('', include('public.content.urls', namespace='content')),
]
