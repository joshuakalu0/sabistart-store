"""
notifications/models.py  (combined entry point)
=================================================
App 10 — Notifications Domain
Django app: notifications

COMPLETE MODEL INVENTORY (25 models + 2 abstract bases):

  ABSTRACT BASES:
    TimestampedModel, AppendOnlyModel

  SHARED ENUMS (not models):
    ChannelType, DeliveryStatus

  SECTION 2 — CHANNEL CONFIGURATION (tenant schema):
    NotificationChannel, EmailChannelConfig, SMSChannelConfig,
    PushChannelConfig, SlackChannelConfig

  SECTION 3 — TEMPLATES (tenant schema):
    NotificationCategory, NotificationTemplate,
    NotificationTemplateVersion, TemplateVariable

  SECTION 4 — CUSTOMER PREFERENCES (tenant schema):
    NotificationPreference, CustomerDevice,
    NotificationBlacklist, UnsubscribeToken

  SECTION 5 — QUEUE & DELIVERY (tenant schema):
    NotificationJob, NotificationLog, NotificationEvent,
    BounceRecord, SpamComplaint

  SECTION 6 — WEBHOOKS (tenant schema):
    WebhookEndpoint, WebhookEventSubscription,
    WebhookDeliveryAttempt, WebhookSigningSecret

  SECTION 7 — IN-APP (tenant schema):
    InAppNotification, InAppNotificationRead

  SECTION 8 — ANALYTICS (tenant schema):
    NotificationDailySummary
"""

# ── Abstract bases & enums ──
from .models_part1 import (
    ChannelType,
    DeliveryStatus,
)

# ── Section 2: Channel config ──
from .models_part1 import (
    NotificationChannel,
    EmailChannelConfig,
    SMSChannelConfig,
    PushChannelConfig,
    SlackChannelConfig,
)

# ── Section 3: Templates ──
from .models_part1 import (
    NotificationCategory,
    NotificationTemplate,
    NotificationTemplateVersion,
    TemplateVariable,
)

# ── Section 4: Preferences ──
from .models_part2 import (
    NotificationPreference,
    CustomerDevice,
    NotificationBlacklist,
    UnsubscribeToken,
)

# ── Section 5: Queue & Delivery ──
from .models_part2 import (
    NotificationJob,
    NotificationLog,
    NotificationEvent,
    BounceRecord,
    SpamComplaint,
)

# ── Section 6: Webhooks ──
from .models_part2 import (
    WebhookEndpoint,
    WebhookEventSubscription,
    WebhookDeliveryAttempt,
    WebhookSigningSecret,
)

# ── Section 7: In-App ──
from .models_part3 import (
    InAppNotification,
    InAppNotificationRead,
)

# ── Section 8: Analytics ──
from .models_part3 import (
    NotificationDailySummary,
)

__all__ = [
    # Abstracts & enums
    "ChannelType", "DeliveryStatus",
    # Section 2
    "NotificationChannel", "EmailChannelConfig", "SMSChannelConfig",
    "PushChannelConfig", "SlackChannelConfig",
    # Section 3
    "NotificationCategory", "NotificationTemplate",
    "NotificationTemplateVersion", "TemplateVariable",
    # Section 4
    "NotificationPreference", "CustomerDevice",
    "NotificationBlacklist", "UnsubscribeToken",
    # Section 5
    "NotificationJob", "NotificationLog", "NotificationEvent",
    "BounceRecord", "SpamComplaint",
    # Section 6
    "WebhookEndpoint", "WebhookEventSubscription",
    "WebhookDeliveryAttempt", "WebhookSigningSecret",
    # Section 7
    "InAppNotification", "InAppNotificationRead",
    # Section 8
    "NotificationDailySummary",
]
