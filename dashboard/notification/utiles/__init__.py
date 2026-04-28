"""
notifications/utils/__init__.py
================================
Public surface of the notifications utility layer.

Sub-modules:
    dispatch        → Core send pipeline: resolve, validate, render, queue, deliver
    channels        → Channel CRUD, health monitoring, rate limit enforcement
    templates       → Template CRUD, version management, rendering, preview
    preferences     → Customer opt-in/out, blacklist, unsubscribe token flow
    webhooks        → Endpoint management, event dispatch, signature, retry queue
    inapp           → In-app notification creation, delivery, read-state management
    analytics       → Time-series metrics, funnel analysis, deliverability reporting
    dashboard       → KPI cards, health checks, attention queue, channel performance
"""

from .dispatch import (
    send_notification,
    send_notification_bulk,
    queue_notification,
    cancel_notification_job,
    resolve_template,
    render_template,
    check_suppression,
    check_preference,
    build_dedup_key,
    NotificationDispatchResult,
    BulkDispatchResult,
)

from .channels_templates_prefs import (
    get_channel_for_event,
    get_default_channel,
    list_channels,
    create_channel,
    update_channel,
    activate_channel,
    deactivate_channel,
    test_channel,
    reset_channel_failures,
    get_channel_health,
    check_rate_limit,
    increment_rate_counter,
    ChannelTestResult,
    ChannelHealthStatus,
)

from .channels_templates_prefs import (
    get_template_for_event,
    create_template,
    update_template,
    create_template_version,
    publish_template_version,
    rollback_template_version,
    preview_template,
    duplicate_template,
    validate_template_variables,
    list_templates,
    get_template_version_history,
    TemplatePreviewResult,
    TemplateValidationResult,
)

from .channels_templates_prefs import (
    get_customer_preferences,
    update_preference,
    bulk_update_preferences,
    unsubscribe_customer,
    resubscribe_customer,
    global_unsubscribe,
    process_unsubscribe_token,
    generate_unsubscribe_token,
    add_to_blacklist,
    remove_from_blacklist,
    is_recipient_suppressed,
    process_bounce,
    process_spam_complaint,
    register_device,
    unregister_device,
    get_customer_devices,
    PreferenceUpdateResult,
)

from .channels_templates_prefs import (
    dispatch_webhook_event,
    dispatch_webhook_bulk,
    retry_failed_webhooks,
    verify_endpoint,
    create_webhook_endpoint,
    update_webhook_endpoint,
    delete_webhook_endpoint,
    add_event_subscription,
    remove_event_subscription,
    rotate_signing_secret,
    get_endpoint_delivery_history,
    verify_webhook_signature,
    build_webhook_payload,
    WebhookDispatchResult,
)

from .channels_templates_prefs import (
    create_inapp_notification,
    broadcast_inapp_notification,
    get_unread_notifications,
    get_notification_feed,
    mark_notification_read,
    mark_notification_dismissed,
    mark_notification_actioned,
    mark_all_read,
    get_unread_count,
    delete_expired_notifications,
    InAppCreateResult,
)

from .analytics_dashboard import (
    get_delivery_stats,
    get_channel_performance,
    get_template_performance,
    get_delivery_funnel,
    get_deliverability_health,
    get_engagement_over_time,
    get_top_events_by_volume,
    get_bounce_analysis,
    get_spam_rate_trend,
    get_webhook_performance,
    get_unsubscribe_trend,
    get_ab_test_results,
    build_daily_summary,
)

from .analytics_dashboard import (
    get_notifications_dashboard_kpis,
    get_channel_status_overview,
    get_recent_delivery_activity,
    get_notifications_health_checks,
    get_deliverability_alerts,
    get_webhook_queue_status,
    get_inapp_notification_queue,
    get_template_coverage_report,
    get_suppression_stats,
    get_notifications_attention_queue,
)

__all__ = [
    # dispatch
    "send_notification", "send_notification_bulk", "queue_notification",
    "cancel_notification_job", "resolve_template", "render_template",
    "check_suppression", "check_preference", "build_dedup_key",
    "NotificationDispatchResult", "BulkDispatchResult",
    # channels
    "get_channel_for_event", "get_default_channel", "list_channels",
    "create_channel", "update_channel", "activate_channel", "deactivate_channel",
    "test_channel", "reset_channel_failures", "get_channel_health",
    "check_rate_limit", "increment_rate_counter",
    "ChannelTestResult", "ChannelHealthStatus",
    # templates
    "get_template_for_event", "create_template", "update_template",
    "create_template_version", "publish_template_version", "rollback_template_version",
    "preview_template", "duplicate_template", "validate_template_variables",
    "list_templates", "get_template_version_history",
    "TemplatePreviewResult", "TemplateValidationResult",
    # preferences
    "get_customer_preferences", "update_preference", "bulk_update_preferences",
    "unsubscribe_customer", "resubscribe_customer", "global_unsubscribe",
    "process_unsubscribe_token", "generate_unsubscribe_token",
    "add_to_blacklist", "remove_from_blacklist", "is_recipient_suppressed",
    "process_bounce", "process_spam_complaint",
    "register_device", "unregister_device", "get_customer_devices",
    "PreferenceUpdateResult",
    # webhooks
    "dispatch_webhook_event", "dispatch_webhook_bulk", "retry_failed_webhooks",
    "verify_endpoint", "create_webhook_endpoint", "update_webhook_endpoint",
    "delete_webhook_endpoint", "add_event_subscription", "remove_event_subscription",
    "rotate_signing_secret", "get_endpoint_delivery_history",
    "verify_webhook_signature", "build_webhook_payload", "WebhookDispatchResult",
    # inapp
    "create_inapp_notification", "broadcast_inapp_notification",
    "get_unread_notifications", "get_notification_feed",
    "mark_notification_read", "mark_notification_dismissed",
    "mark_notification_actioned", "mark_all_read", "get_unread_count",
    "delete_expired_notifications", "InAppCreateResult",
    # analytics
    "get_delivery_stats", "get_channel_performance", "get_template_performance",
    "get_delivery_funnel", "get_deliverability_health", "get_engagement_over_time",
    "get_top_events_by_volume", "get_bounce_analysis", "get_spam_rate_trend",
    "get_webhook_performance", "get_unsubscribe_trend", "get_ab_test_results",
    "build_daily_summary",
    # dashboard
    "get_notifications_dashboard_kpis", "get_channel_status_overview",
    "get_recent_delivery_activity", "get_notifications_health_checks",
    "get_deliverability_alerts", "get_webhook_queue_status",
    "get_inapp_notification_queue", "get_template_coverage_report",
    "get_suppression_stats", "get_notifications_attention_queue",
]
