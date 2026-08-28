"""
system/account/urls.py
====================
URL configuration for platform-level authentication.
"""

from django.urls import path

from system.account import views
from system.account.dashboard_views import (
    PlatformDashboardView,
    PlatformDiagnosticsRunView,
    PlatformDiagnosticsView,
    PlatformStoreDetailView,
    PlatformStoresView,
    PlatformUsersView,
    PlatformUserDetailView,
    PlatformUserDeleteView,
    PlatformUserStatusToggleView,
    PlatformProvisioningLogsView,
    PlatformProvisioningRetryView,
    PlatformProvisioningDropSchemaView,
)

app_name = 'account'

urlpatterns = [
    # Dashboard
    path('', PlatformDashboardView.as_view(), name='dashboard'),
    path('dashboard/', PlatformDashboardView.as_view(), name='dashboard'),
    path('stores/', PlatformStoresView.as_view(), name='stores'),
    path('stores/<str:schema_name>/', PlatformStoreDetailView.as_view(), name='store_detail'),

    # User Management
    path('users/', PlatformUsersView.as_view(), name='users'),
    path('users/<uuid:user_id>/', PlatformUserDetailView.as_view(), name='user_detail'),
    path('users/<uuid:user_id>/delete/', PlatformUserDeleteView.as_view(), name='user_delete'),
    path('users/<uuid:user_id>/status/', PlatformUserStatusToggleView.as_view(), name='user_status_toggle'),

    # Provisioning & Migration Logs
    path('provisioning/', PlatformProvisioningLogsView.as_view(), name='provisioning_logs'),
    path('provisioning/retry/<str:schema_name>/', PlatformProvisioningRetryView.as_view(), name='provisioning_retry'),
    path('provisioning/drop-schema/<str:schema_name>/', PlatformProvisioningDropSchemaView.as_view(), name='provisioning_drop_schema'),

    # Authentication
    path('register/', views.onboarding_start, name='register'),
    path('register/account/', views.onboarding_account, name='onboarding_account'),
    path('register/plan/', views.onboarding_plan, name='onboarding_plan'),
    path('register/checkout/', views.onboarding_checkout, name='onboarding_checkout'),
    path('register/payment/', views.onboarding_payment_session, name='onboarding_payment_session'),
    path('register/payment/callback/<str:purchase_reference>/', views.onboarding_payment_callback, name='onboarding_payment_callback'),
    path('register/subdomain/', views.onboarding_subdomain, name='onboarding_subdomain'),
    path('register/provisioning/', views.onboarding_provisioning, name='onboarding_provisioning'),
    path('register/provisioning/status/', views.onboarding_provisioning_status, name='onboarding_provisioning_status'),
    path('register/review/', views.onboarding_review, name='onboarding_review'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),

    # Password reset
    path('password/reset/', views.PasswordResetRequestView.as_view(),
         name='password_reset'),

    # AJAX
    path('register/check-subdomain/', views.check_subdomain, name='check_subdomain'),
    path('check-subdomain/', views.check_subdomain, name='legacy_check_subdomain'),

    # Diagnostics
    path('diagnostics/', PlatformDiagnosticsView.as_view(), name='diagnostics'),
    path('diagnostics/run/', PlatformDiagnosticsRunView.as_view(), name='diagnostics_run'),
]
