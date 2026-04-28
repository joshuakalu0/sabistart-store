from django.urls import path
from .views import index, channels, templates, preferences, delivery, webhooks, inapp

urlpatterns = [
    # Dashboard Home
    path('', index.notification_dashboard_index, name='notification_dashboard_index'),
    
    # Channels
    path('channels/', channels.channel_list, name='notification_channel_list'),
    path('channels/create/', channels.channel_create, name='notification_channel_create'),
    path('channels/<uuid:pk>/', channels.channel_detail, name='notification_channel_detail'),
    path('channels/<uuid:pk>/edit/', channels.channel_update, name='notification_channel_update'),
    path('channels/<uuid:pk>/delete/', channels.channel_delete, name='notification_channel_delete'),
    
    # Categories
    path('categories/', templates.category_list, name='notification_category_list'),
    path('categories/create/', templates.category_create, name='notification_category_create'),
    path('categories/<uuid:pk>/edit/', templates.category_update, name='notification_category_update'),
    
    # Templates
    path('templates/', templates.template_list, name='notification_template_list'),
    path('templates/create/', templates.template_create, name='notification_template_create'),
    path('templates/<uuid:pk>/edit/', templates.template_update, name='notification_template_update'),
    path('templates/<uuid:template_pk>/versions/', templates.template_version_history, name='notification_template_version_history'),
    path('templates/<uuid:template_pk>/versions/create/', templates.template_version_create, name='notification_template_version_create'),
    path('versions/<uuid:pk>/activate/', templates.template_version_activate, name='notification_template_version_activate'),
    
    # Preferences & Suppressions
    path('preferences/', preferences.preference_list, name='notification_preference_list'),
    path('blacklist/', preferences.blacklist_list, name='notification_blacklist_list'),
    
    # Delivery (Jobs, Logs, Bounces)
    path('jobs/', delivery.job_list, name='notification_job_list'),
    path('logs/', delivery.log_list, name='notification_log_list'),
    path('logs/<uuid:pk>/', delivery.log_detail, name='notification_log_detail'),
    path('bounces/', delivery.bounce_list, name='notification_bounce_list'),
    
    # Webhooks
    path('webhooks/', webhooks.webhook_list, name='notification_webhook_list'),
    path('webhooks/create/', webhooks.webhook_create, name='notification_webhook_create'),
    path('webhooks/<uuid:pk>/', webhooks.webhook_detail, name='notification_webhook_detail'),
    path('webhooks/<uuid:pk>/edit/', webhooks.webhook_update, name='notification_webhook_update'),
    path('webhooks/<uuid:pk>/logs/', webhooks.webhook_delivery_logs, name='notification_webhook_delivery_log'),
    
    # In-App Notifications
    path('inapp/', inapp.inapp_list, name='notification_inapp_list'),
    path('inapp/create/', inapp.inapp_create, name='notification_inapp_create'),
    path('inapp/<uuid:pk>/edit/', inapp.inapp_update, name='notification_inapp_update'),
]
