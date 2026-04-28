from django.urls import path
from . import views

app_name = 'checkout'

urlpatterns = [
    path('auth/', views.checkout_auth_view, name='checkout_auth'),
    path('info/', views.checkout_info_view, name='checkout_info'),
    path('shipping/', views.checkout_shipping_view, name='checkout_shipping'),
    path('payment/', views.checkout_payment_view, name='checkout_payment'),
    path('review/', views.checkout_review_view, name='checkout_review'),
    path('callback/', views.payment_callback_view, name='payment_callback'),
    path('webhook/', views.payment_webhook_view, name='payment_webhook'),
    path('express/', views.express_checkout_view, name='express_checkout'),
    path('confirmation/<uuid:order_id>/', views.order_confirmation_view, name='order_confirmation'),
]
