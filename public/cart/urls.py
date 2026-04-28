from django.urls import path
from . import views

app_name = 'cart'

urlpatterns = [
    path('', views.cart_page_view, name='cart_page'),
    path('update/', views.cart_update_view, name='cart_update'),
    path('coupon/', views.apply_coupon_view, name='apply_coupon'),
    path('recover/<uuid:token>/', views.cart_recover_view, name='cart_recover'),
]
