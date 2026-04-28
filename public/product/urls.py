from django.urls import path
from . import views

app_name = 'product'

urlpatterns = [
    path('p/<slug:product_slug>/', views.product_detail_view, name='product_detail'),
    path('p/<slug:product_slug>/quick-view/', views.product_quick_view, name='product_quick_view'),
    path('compare/', views.product_compare_view, name='product_compare'),
    path('bundles/<slug:bundle_slug>/', views.bundle_detail_view, name='bundle_detail'),
    path('d/<slug:digital_slug>/', views.digital_product_view, name='digital_product'),
    path('s/<slug:sub_slug>/', views.subscription_product_view, name='subscription_product'),
    path('conf/<slug:conf_slug>/', views.configurable_product_view, name='configurable_product'),
    path('p/<slug:product_slug>/notify/', views.notify_me_view, name='notify_me'),
    path('p/<slug:product_slug>/pre-order/', views.pre_order_view, name='pre_order'),
]