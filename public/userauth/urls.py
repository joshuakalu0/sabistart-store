"""
public/userauth/urls.py
====================
URL configuration for tenant-level authentication.

These URLs are used within tenant schemas.
"""

from django.urls import path

from public.userauth import views, profile_views

app_name = 'tenant'

urlpatterns = [
    # Authentication
    path('register/', views.tenant_register_view, name='register'),
    path('login/', views.tenant_login_view, name='login'),
    path('logout/', views.tenant_logout_view, name='logout'),
    path('auth/sso/', views.tenant_sso_login_view, name='sso_login'),
    
    # Extended Auth Flows
    path('verify-email/', profile_views.verify_email_view, name='verify_email'),
    path('password-reset/', profile_views.password_reset_view, name='password_reset'),
    path('password-reset/confirm/<uidb64>/<token>/', profile_views.password_reset_confirm_view, name='password_reset_confirm'),

    # Account Dashboard
    path('dashboard/', profile_views.account_overview_view, name='account_overview'),
    path('orders/', profile_views.account_orders_view, name='account_orders'),
    path('orders/<uuid:order_id>/', profile_views.account_order_detail_view, name='account_order_detail'),
    path('orders/<uuid:order_id>/tracking/', profile_views.order_tracking_view, name='order_tracking'),
    path('orders/<uuid:order_id>/return/', profile_views.order_return_view, name='order_return'),
    path('profile/', profile_views.profile_edit_view, name='profile_edit'),
    path('security/', profile_views.account_security_view, name='account_security'),
    path('addresses/', profile_views.address_book_view, name='address_book'),
    path('payments/', profile_views.payment_methods_view, name='payment_methods'),
    path('wishlist/', profile_views.wishlist_view, name='wishlist'),
    path('recently-viewed/', profile_views.recently_viewed_view, name='recently_viewed'),
    path('loyalty/', profile_views.loyalty_portal_view, name='loyalty_portal'),
    path('referrals/', profile_views.referral_dashboard_view, name='referral_dashboard'),
    path('store-credit/', profile_views.store_credit_view, name='store_credit'),
    path('subscriptions/', profile_views.user_subscriptions_view, name='user_subscriptions'),
    path('notifications/', profile_views.notification_settings_view, name='notification_settings'),
    path('privacy/', profile_views.privacy_settings_view, name='privacy_settings'),
    path('delete/', profile_views.account_delete_view, name='account_delete'),
    path('reviews/', profile_views.user_reviews_view, name='user_reviews'),
]