from django.urls import path
from . import views

app_name = 'pos'

urlpatterns = [
    path('', views.pos_dashboard, name='dashboard'),
    path('places/', views.stores, name='stores'),
    path('sessions/', views.sessions, name='sessions'),
    # Register (server-side cart)
    path('register/', views.pos_register, name='register'),
    path('cart/add/', views.cart_api_add, name='cart_add'),
    path('cart/update/', views.cart_api_update, name='cart_update'),
    path('cart/remove/', views.cart_api_remove, name='cart_remove'),
    path('cart/hold/', views.cart_api_hold, name='cart_hold'),
    path('cart/resume/', views.cart_api_resume, name='cart_resume'),
    path('cart/clear/', views.cart_api_clear, name='cart_clear'),
    path('cart/checkout/', views.cart_api_checkout, name='cart_checkout'),
    path('offline/sync/', views.offline_sync, name='offline_sync'),
    # Transactions
    path('transaction/create/', views.create_transaction, name='create_transaction'),
    path('products/search/', views.search_products, name='search_products'),
    path('products/', views.pos_products, name='products'),
    path('products/sync-catalog/', views.sync_catalog_bridge_view, name='sync_catalog_bridge'),
    path('products/create/', views.create_pos_product, name='product_create'),
    path('products/<uuid:product_id>/edit/', views.edit_pos_product, name='product_edit'),
    path('products/<uuid:product_id>/toggle/', views.toggle_product, name='product_toggle'),
    path('receipt/<uuid:transaction_id>/', views.generate_receipt, name='receipt'),
    path('invoice/<uuid:transaction_id>/', views.generate_receipt, name='invoice'),
    path('inventory/adjust/', views.adjust_inventory, name='adjust_inventory'),
    path('inventory/', views.inventory, name='inventory'),
    path('sales/', views.sales, name='sales'),
    path('sales/<uuid:transaction_id>/', views.sale_detail, name='sale_detail'),
    path('discounts/', views.discounts, name='discounts'),
]
