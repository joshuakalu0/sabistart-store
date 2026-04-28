"""
system/account/urls.py
====================
URL configuration for platform-level authentication.
"""

from django.urls import path

from system.account import views
from system.account.dashboard_views import (
    PlatformDashboardView,
    PlatformStoreDetailView,
    PlatformStoresView,
)

app_name = 'account'

urlpatterns = [
    # Dashboard
    path('', PlatformDashboardView.as_view(), name='dashboard'),
    path('dashboard/', PlatformDashboardView.as_view(), name='dashboard'),
    path('stores/', PlatformStoresView.as_view(), name='stores'),
    path('stores/<str:schema_name>/', PlatformStoreDetailView.as_view(), name='store_detail'),

    # Authentication
    path('register/', views.onboarding_start, name='register'),
    path('register/account/', views.onboarding_account, name='onboarding_account'),
    path('register/plan/', views.onboarding_plan, name='onboarding_plan'),
    path('register/checkout/', views.onboarding_checkout, name='onboarding_checkout'),
    path('register/payment/', views.onboarding_payment_session, name='onboarding_payment_session'),
    path('register/subdomain/', views.onboarding_subdomain, name='onboarding_subdomain'),
    path('register/review/', views.onboarding_review, name='onboarding_review'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),

    # Password reset
    path('password/reset/', views.PasswordResetRequestView.as_view(),
         name='password_reset'),

    # AJAX
    path('register/check-subdomain/', views.check_subdomain, name='check_subdomain'),
    path('check-subdomain/', views.check_subdomain, name='legacy_check_subdomain'),
]
