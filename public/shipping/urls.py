from django.urls import path
from . import views

app_name = 'shipping'

urlpatterns = [
    path('stores/', views.store_locator_view, name='store_locator'),
    path('stores/<slug:store_slug>/', views.store_detail_view, name='store_detail'),
    path('stores/<slug:store_slug>/click-collect/', views.click_collect_info_view, name='click_collect_info'),
    path('shipping-info/', views.shipping_info_view, name='shipping_info'),
]
