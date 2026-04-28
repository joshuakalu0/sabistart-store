from django.urls import path
from . import views


app_name = 'system_pay'


urlpatterns = [
    path('', views.system_pay_home, name='home'),
    path('gateways/', views.gateways, name='gateways'),
    path('gateways/create/', views.gateway_create, name='gateway_create'),
    path('gateways/<uuid:gateway_id>/', views.gateway_detail, name='gateway_detail'),
    path('gateways/<uuid:gateway_id>/edit/', views.gateway_edit, name='gateway_edit'),
    path('gateways/<uuid:gateway_id>/credentials/create/', views.credential_create, name='credential_create'),
    path('credentials/<uuid:credential_id>/edit/', views.credential_edit, name='credential_edit'),
    path('gateways/<uuid:gateway_id>/webhook/', views.webhook_edit, name='webhook_edit'),
    path('tenants/', views.tenants, name='tenants'),
    path('tenants/<str:schema_name>/', views.tenant_detail, name='tenant_detail'),
    path('transactions/', views.transactions, name='transactions'),
    path('payouts/', views.payouts, name='payouts'),
    path('refunds/', views.refunds, name='refunds'),
    path('disputes/', views.disputes, name='disputes'),
    path('settings/', views.settings_view, name='settings'),
    path('settings/platform/', views.payment_settings_edit, name='payment_settings_edit'),
    path('settings/commissions/create/', views.commission_rule_create, name='commission_rule_create'),
    path('settings/commissions/<uuid:rule_id>/edit/', views.commission_rule_edit, name='commission_rule_edit'),
    path('api/gateways/', views.PaymentGatewaysAPIView.as_view(), name='api_gateways'),
    path('health/', views.health_check, name='health_check'),
    path('marketplace/checkout/<str:purchase_reference>/', views.marketplace_checkout, name='marketplace_checkout'),
    path('marketplace/callback/<str:purchase_reference>/', views.marketplace_payment_callback, name='marketplace_payment_callback'),
    path('webhooks/marketplace/<str:provider>/', views.marketplace_webhook, name='marketplace_webhook'),
    # Add more URLs as needed
]
