"""URLs for store settings management."""

"""
Settings URL Configuration
Professional settings system routing
"""

from django.urls import path
from . import views

app_name = 'dashboard_settings'

urlpatterns = [
    # Settings index
    path('', views.settings_index, name='index'),

    # Settings categories
    path('general/', views.general_settings, name='general'),
    path('branding/', views.branding_settings, name='branding'),
    path('seo/', views.seo_settings, name='seo'),
    path('payment/', views.payment_settings, name='payment'),
    path('shipping/', views.shipping_settings, name='shipping'),
    path('tax/', views.tax_settings, name='tax'),
    path('notification/', views.notification_settings, name='notification'),
    path('policy/', views.policy_settings, name='policy'),
    path('checkout/', views.checkout_settings, name='checkout'),
    path('security/', views.security_settings, name='security'),
    path('feature/', views.feature_settings, name='feature'),

    # AJAX endpoints
    path('api/toggle-maintenance/', views.toggle_maintenance_mode, name='toggle_maintenance'),
]
