"""
notifications/models.py  — Part 1 of 3
========================================
App 10 — Notifications Domain
Multi-tenant e-commerce platform (django-tenants, schema-based isolation)

COMPLETE MODEL INVENTORY (25 models):

  SECTION 1 — ABSTRACT BASES & SHARED ENUMS
    MixIdAndTimeModel, AppendOnlyModel

  SECTION 2 — CHANNEL CONFIGURATION  (tenant schema)
    1.  NotificationChannel       → Tenant-configured delivery channel (Email/SMS/Push/Webhook)
    2.  EmailChannelConfig        → SMTP / ESP settings per channel
    3.  SMSChannelConfig          → SMS provider settings (Twilio, Termii, etc.)
    4.  PushChannelConfig         → FCM/APNs push notification settings
    5.  SlackChannelConfig        → Slack workspace/channel webhook settings

  SECTION 3 — TEMPLATES  (tenant schema)
    6.  NotificationTemplate      → Versioned message template per event + channel
    7.  NotificationTemplateVersion → Immutable version snapshot for audit/rollback
    8.  TemplateVariable          → Declared variables in a template with validation schema
    9.  NotificationCategory      → Logical grouping of templates (Transactional, Marketing)

  SECTION 4 — CUSTOMER PREFERENCES  (tenant schema)
   10.  NotificationPreference    → Per-customer opt-in/out per category+channel
   11.  CustomerDevice            → Push notification device tokens per customer
   12.  NotificationBlacklist     → Global suppression list (bounced emails, opted-out phones)
   13.  UnsubscribeToken          → Secure one-click unsubscribe tokens

  SECTION 5 — OUTBOUND QUEUE & DELIVERY  (tenant schema)
   14.  NotificationJob           → Scheduled / queued outbound notification task
   15.  NotificationLog           → IMMUTABLE delivery record per send attempt
   16.  NotificationEvent         → Append-only event timeline on each NotificationLog
   17.  BounceRecord              → Hard/soft bounce tracking for email deliverability
   18.  SpamComplaint             → Spam/abuse complaint records

  SECTION 6 — WEBHOOKS  (tenant schema)
   19.  WebhookEndpoint           → Tenant-registered URLs for event callbacks
   20.  WebhookEventSubscription  → Which events an endpoint subscribes to
   21.  WebhookDeliveryAttempt    → Append-only log of every dispatch + response
   22.  WebhookSigningSecret      → Rotating signing keys for payload verification

  SECTION 7 — IN-APP NOTIFICATIONS  (tenant schema)
   23.  InAppNotification         → Notification shown inside the merchant dashboard / customer portal
   24.  InAppNotificationRead     → Read-state tracking per user per notification

  SECTION 8 — ANALYTICS AGGREGATES  (tenant schema)
   25.  NotificationDailySummary  → Pre-aggregated daily stats per channel + template

Architecture notes:
  - All IDs: UUID4. All monetary values: Decimal(14,2).
  - NotificationLog and WebhookDeliveryAttempt are APPEND-ONLY ledgers.
    Never UPDATE or DELETE rows — only INSERT.
  - Template rendering uses Jinja2 with a declared variable schema.
  - Sensitive credentials (SMTP passwords, API keys, signing secrets)
    are stored encrypted using Fernet symmetric encryption via a
    EncryptedTextField custom field (stub here — replace with django-fernet-fields).
  - Delivery status transitions are tracked via NotificationEvent (append-only).
  - Customer device tokens are stored per-device for accurate push targeting.
  - WebhookEndpoint uses HMAC-SHA256 payload signing via WebhookSigningSecret.
"""

import hashlib
import hmac
import json
import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import (
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
    URLValidator,
)
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from public.userauth.models import TenantUser
from dashboard.settings.models import  MixIdAndTimeModel


# ─────────────────────────────────────────────────────────────
# SHARED ENUMS (used across multiple models)
# ─────────────────────────────────────────────────────────────

class ChannelType(models.TextChoices):
    EMAIL = "email", _("Email")
    SMS = "sms", _("SMS")
    PUSH = "push", _("Push Notification")
    SLACK = "slack", _("Slack")
    WEBHOOK = "webhook", _("Webhook")
    IN_APP = "in_app", _("In-App Notification")
    WHATSAPP = "whatsapp", _("WhatsApp")


class DeliveryStatus(models.TextChoices):
    PENDING = "pending", _("Pending — Queued, not yet sent")
    PROCESSING = "processing", _("Processing — Currently being sent")
    SENT = "sent", _("Sent — Accepted by provider")
    DELIVERED = "delivered", _("Delivered — Confirmed delivery")
    OPENED = "opened", _("Opened — Recipient opened the message")
    CLICKED = "clicked", _("Clicked — Recipient clicked a link")
    BOUNCED = "bounced", _("Bounced — Delivery failed permanently")
    SOFT_BOUNCED = "soft_bounced", _(
        "Soft Bounced — Temporary delivery failure")
    FAILED = "failed", _("Failed — Send attempt failed")
    CANCELLED = "cancelled", _("Cancelled — Scheduled send cancelled")
    SUPPRESSED = "suppressed", _(
        "Suppressed — Blocked by preferences/blacklist")
    SPAM = "spam", _("Spam Complaint")
    UNSUBSCRIBED = "unsubscribed", _("Unsubscribed")


# ─────────────────────────────────────────────────────────────
# SECTION 2 — CHANNEL CONFIGURATION  (TENANT SCHEMA)
# ─────────────────────────────────────────────────────────────

class NotificationChannel(MixIdAndTimeModel):
    """
    A tenant-configured delivery channel.

    Each channel has a type (email/sms/push/etc.) and points to
    a provider-specific config table via a OneToOne relationship
    (EmailChannelConfig, SMSChannelConfig, etc.).

    A tenant can have MULTIPLE channels of the same type
    (e.g. two email channels: Transactional + Marketing)
    and route different notification categories to different channels.

    Channel status:
      ACTIVE      → Operational, actively used for sending
      INACTIVE    → Configured but paused
      TESTING     → Sandbox/test mode — sends to test addresses only
      DEGRADED    → Provider reporting issues, alert triggered
      DISABLED    → Permanently off, credentials removed

    Priority:
      When multiple channels of the same type exist, the one with
      the highest priority value is used first.
    """

    class ChannelStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        INACTIVE = "inactive", _("Inactive / Paused")
        TESTING = "testing", _("Testing / Sandbox Mode")
        DEGRADED = "degraded", _("Degraded — Provider Issues Detected")
        DISABLED = "disabled", _("Disabled")

    # ── Identity ──
    name = models.CharField(
        _("Channel Name"),
        max_length=255,
        help_text=_(
            "e.g. 'Transactional Email', 'SMS Alerts', 'Order Push Notifications'"),
    )
    channel_type = models.CharField(
        _("Channel Type"),
        max_length=15,
        choices=ChannelType.choices,
        db_index=True,
    )
    status = models.CharField(
        _("Status"),
        max_length=15,
        choices=ChannelStatus.choices,
        default=ChannelStatus.INACTIVE,
        db_index=True,
    )
    description = models.TextField(_("Description"), blank=True)

    # ── Routing ──
    is_default = models.BooleanField(
        _("Default for Type"),
        default=False,
        help_text=_(
            "Default channel used when no specific channel is specified "
            "for this channel_type. Only one default per type."
        ),
    )
    priority = models.PositiveIntegerField(
        _("Priority"),
        default=0,
        help_text=_(
            "Higher = used first when multiple channels of same type exist."),
    )
    allowed_categories = models.JSONField(
        _("Allowed Categories"),
        default=list,
        blank=True,
        help_text=_(
            "List of NotificationCategory slugs this channel handles. "
            "Empty = handles all categories."
        ),
    )

    # ── Rate limiting ──
    rate_limit_per_minute = models.PositiveIntegerField(
        _("Rate Limit (per minute)"),
        null=True,
        blank=True,
        help_text=_("Maximum sends per minute. Null = no limit."),
    )
    rate_limit_per_hour = models.PositiveIntegerField(
        _("Rate Limit (per hour)"),
        null=True,
        blank=True,
    )
    rate_limit_per_day = models.PositiveIntegerField(
        _("Rate Limit (per day)"),
        null=True,
        blank=True,
    )
    daily_send_count = models.PositiveIntegerField(
        _("Today's Send Count"),
        default=0,
        help_text=_(
            "Auto-incremented daily counter. Reset at midnight by scheduled task."),
    )
    daily_send_count_reset_at = models.DateTimeField(
        _("Daily Count Reset At"),
        null=True,
        blank=True,
    )

    # ── Health monitoring ──
    last_successful_send_at = models.DateTimeField(
        _("Last Successful Send At"),
        null=True,
        blank=True,
    )
    last_failure_at = models.DateTimeField(
        _("Last Failure At"),
        null=True,
        blank=True,
    )
    consecutive_failures = models.PositiveIntegerField(
        _("Consecutive Failures"),
        default=0,
        help_text=_(
            "Triggers DEGRADED status when this exceeds failure_threshold."),
    )
    failure_threshold = models.PositiveIntegerField(
        _("Failure Threshold"),
        default=5,
        help_text=_(
            "Consecutive failures before channel is marked DEGRADED "
            "and an alert is sent to the tenant."
        ),
    )

    # ── Metadata ──
    tags = models.JSONField(
        _("Tags"),
        default=list,
        blank=True,
        help_text=_(
            "Internal tags for channel management. e.g. ['transactional', 'high-priority']"),
    )
    internal_note = models.TextField(_("Internal Note"), blank=True)
    created_by = models.ForeignKey(
        TenantUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_notification_channels",
    )

    class Meta:
        verbose_name = _("Notification Channel")
        verbose_name_plural = _("Notification Channels")
        ordering = ["-is_default", "-priority", "name"]
        indexes = [
            models.Index(fields=["channel_type", "status"]),
            models.Index(fields=["channel_type", "is_default"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.channel_type}) [{self.status}]"

    def save(self, *args, **kwargs):
        """Enforce single default per channel type."""
        if self.is_default:
            NotificationChannel.objects.filter(
                channel_type=self.channel_type,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    @property
    def is_operational(self) -> bool:
        return self.status == self.ChannelStatus.ACTIVE

    def record_success(self):
        """Reset failure counter after a successful send."""
        self.consecutive_failures = 0
        self.last_successful_send_at = timezone.now()
        self.daily_send_count = models.F("daily_send_count") + 1
        self.save(update_fields=[
            "consecutive_failures", "last_successful_send_at",
            "daily_send_count", "updated_at",
        ])

    def record_failure(self):
        """Increment failure counter and degrade channel if threshold exceeded."""
        self.consecutive_failures = models.F("consecutive_failures") + 1
        self.last_failure_at = timezone.now()
        self.save(update_fields=[
            "consecutive_failures", "last_failure_at", "updated_at"
        ])
        self.refresh_from_db(fields=["consecutive_failures"])
        if self.consecutive_failures >= self.failure_threshold:
            NotificationChannel.objects.filter(pk=self.pk).update(
                status=self.ChannelStatus.DEGRADED
            )


class EmailChannelConfig(MixIdAndTimeModel):
    """
    SMTP or Email Service Provider (ESP) configuration for an email channel.

    Supports:
      - Direct SMTP (Gmail, SendGrid SMTP, custom server)
      - ESP API (SendGrid API, Mailgun, Postmark, AWS SES, Resend)

    All sensitive fields (passwords, API keys) should use
    django-fernet-fields or equivalent encryption in production.
    Here they use TextField with a docstring noting encryption requirement.
    """

    class EmailProvider(models.TextChoices):
        SMTP = "smtp", _("SMTP (Generic)")
        SENDGRID = "sendgrid", _("SendGrid API")
        MAILGUN = "mailgun", _("Mailgun API")
        POSTMARK = "postmark", _("Postmark API")
        AWS_SES = "aws_ses", _("Amazon SES")
        RESEND = "resend", _("Resend API")
        BREVO = "brevo", _("Brevo (Sendinblue)")
        SPARKPOST = "sparkpost", _("SparkPost")
        CUSTOM = "custom", _("Custom / Other")

    class SMTPEncryption(models.TextChoices):
        NONE = "none", _("None (Plain)")
        SSL = "ssl", _("SSL/TLS")
        STARTTLS = "starttls", _("STARTTLS")

    channel = models.OneToOneField(
        NotificationChannel,
        on_delete=models.CASCADE,
        related_name="email_config",
        verbose_name=_("Channel"),
    )
    provider = models.CharField(
        _("Email Provider"),
        max_length=15,
        choices=EmailProvider.choices,
        default=EmailProvider.SMTP,
    )

    # ── From identity ──
    from_email = models.EmailField(
        _("From Email"),
        help_text=_("Sender email address. e.g. orders@mystore.com"),
    )
    from_name = models.CharField(
        _("From Name"),
        max_length=255,
        help_text=_("Sender display name. e.g. 'My Store Orders'"),
    )
    reply_to = models.EmailField(
        _("Reply-To Email"),
        blank=True,
        help_text=_("Override reply-to address. Defaults to from_email."),
    )
    bounce_email = models.EmailField(
        _("Bounce / Return-Path Email"),
        blank=True,
        help_text=_("Address that receives bounce notifications."),
    )

    # ── SMTP settings (for SMTP provider) ──
    smtp_host = models.CharField(_("SMTP Host"), max_length=255, blank=True)
    smtp_port = models.PositiveIntegerField(
        _("SMTP Port"), null=True, blank=True, default=587)
    smtp_username = models.CharField(
        _("SMTP Username"), max_length=255, blank=True)
    smtp_password = models.TextField(
        _("SMTP Password (encrypted)"),
        blank=True,
        help_text=_(
            "ENCRYPTED. Use django-fernet-fields in production. Never store plaintext."),
    )
    smtp_encryption = models.CharField(
        _("SMTP Encryption"),
        max_length=10,
        choices=SMTPEncryption.choices,
        default=SMTPEncryption.STARTTLS,
    )
    smtp_timeout = models.PositiveIntegerField(
        _("SMTP Timeout (seconds)"),
        default=30,
    )

    # ── API settings (for ESP providers) ──
    api_key = models.TextField(
        _("API Key (encrypted)"),
        blank=True,
        help_text=_("ENCRYPTED. ESP API key. Never store plaintext."),
    )
    api_domain = models.CharField(
        _("API Domain"),
        max_length=255,
        blank=True,
        help_text=_(
            "For Mailgun: your sending domain. e.g. 'mail.mystore.com'"),
    )
    api_region = models.CharField(
        _("API Region"),
        max_length=20,
        blank=True,
        help_text=_("For region-specific APIs. e.g. 'eu' for Mailgun EU."),
    )
    aws_region = models.CharField(
        _("AWS Region"),
        max_length=30,
        blank=True,
        help_text=_("For AWS SES. e.g. 'eu-west-1'"),
    )
    aws_access_key_id = models.TextField(
        _("AWS Access Key ID (encrypted)"),
        blank=True,
    )
    aws_secret_access_key = models.TextField(
        _("AWS Secret Access Key (encrypted)"),
        blank=True,
    )

    # ── Deliverability settings ──
    ip_pool = models.CharField(
        _("IP Pool Name"),
        max_length=100,
        blank=True,
        help_text=_("For providers supporting IP pools. e.g. 'transactional'"),
    )
    enable_open_tracking = models.BooleanField(
        _("Enable Open Tracking"),
        default=True,
    )
    enable_click_tracking = models.BooleanField(
        _("Enable Click Tracking"),
        default=True,
    )
    enable_unsubscribe_header = models.BooleanField(
        _("Enable List-Unsubscribe Header"),
        default=True,
        help_text=_(
            "Adds List-Unsubscribe header for one-click Gmail unsubscribe support."),
    )
    custom_headers = models.JSONField(
        _("Custom Email Headers"),
        default=dict,
        blank=True,
        help_text=_("Additional SMTP/API headers. {header_name: value}"),
    )
    bcc_all_to = models.EmailField(
        _("BCC All Emails To"),
        blank=True,
        help_text=_(
            "BCC every outbound email to this address. For compliance/auditing."),
    )

    # ── Sending limits ──
    max_recipients_per_send = models.PositiveIntegerField(
        _("Max Recipients Per Message"),
        default=1,
        help_text=_(
            "Maximum To/CC/BCC recipients per single send call. Most ESPs limit to 1000."),
    )
    connection_pool_size = models.PositiveSmallIntegerField(
        _("SMTP Connection Pool Size"),
        default=5,
    )

    # ── Testing ──
    test_email = models.EmailField(
        _("Test Mode Redirect Address"),
        blank=True,
        help_text=_(
            "When channel is in TESTING status, all emails are sent to this "
            "address instead of the real recipient."
        ),
    )

    class Meta:
        verbose_name = _("Email Channel Configuration")
        verbose_name_plural = _("Email Channel Configurations")

    def __str__(self):
        return f"Email Config for {self.channel.name} ({self.provider})"


class SMSChannelConfig(MixIdAndTimeModel):
    """
    SMS provider configuration for an SMS channel.

    Supports major SMS gateways including African providers
    (Termii, Africa's Talking) common for Nigerian/African merchants.
    """

    class SMSProvider(models.TextChoices):
        TWILIO = "twilio", _("Twilio")
        TERMII = "termii", _("Termii (Nigeria)")
        AFRICAS_TALKING = "africas_talking", _("Africa's Talking")
        VONAGE = "vonage", _("Vonage (Nexmo)")
        AWS_SNS = "aws_sns", _("Amazon SNS")
        MESSAGEBIRD = "messagebird", _("MessageBird")
        PLIVO = "plivo", _("Plivo")
        INFOBIP = "infobip", _("Infobip")
        BULKSMS = "bulksms", _("BulkSMS")
        CUSTOM = "custom", _("Custom HTTP Gateway")

    channel = models.OneToOneField(
        NotificationChannel,
        on_delete=models.CASCADE,
        related_name="sms_config",
        verbose_name=_("Channel"),
    )
    provider = models.CharField(
        _("SMS Provider"),
        max_length=20,
        choices=SMSProvider.choices,
        default=SMSProvider.TWILIO,
    )

    # ── Sender identity ──
    sender_id = models.CharField(
        _("Sender ID / From Number"),
        max_length=50,
        help_text=_(
            "Phone number or alphanumeric sender ID. "
            "Format: E.164 for numbers (+2348012345678), text for IDs ('MyStore')."
        ),
    )

    # ── Credentials (all encrypted in production) ──
    account_sid = models.TextField(
        _("Account SID / Account ID (encrypted)"),
        blank=True,
    )
    api_key = models.TextField(
        _("API Key / Auth Token (encrypted)"),
        blank=True,
    )
    api_secret = models.TextField(
        _("API Secret (encrypted)"),
        blank=True,
    )
    api_url = models.URLField(
        _("Custom API Base URL"),
        blank=True,
        help_text=_("For CUSTOM provider: the base URL of the SMS HTTP API."),
    )
    webhook_url = models.URLField(
        _("Delivery Receipt Webhook URL"),
        blank=True,
        help_text=_(
            "URL to receive delivery status callbacks from the provider. "
            "Set this on your provider dashboard to point to your server."
        ),
    )

    # ── Regional settings ──
    default_country_code = models.CharField(
        _("Default Country Code"),
        max_length=5,
        default="+234",
        help_text=_(
            "Prepended to numbers without country code. e.g. '+234' for Nigeria."),
    )
    supported_countries = models.JSONField(
        _("Supported Countries"),
        default=list,
        blank=True,
        help_text=_(
            "ISO 3166-1 alpha-2 codes. Empty = global. e.g. ['NG', 'GH', 'KE']"),
    )

    # ── Features ──
    supports_unicode = models.BooleanField(_("Supports Unicode"), default=True)
    supports_delivery_receipts = models.BooleanField(
        _("Supports Delivery Receipts"),
        default=True,
    )
    max_message_length = models.PositiveSmallIntegerField(
        _("Max Message Length (chars)"),
        default=160,
        help_text=_(
            "Standard SMS = 160 GSM chars. Unicode = 70 chars per segment."),
    )

    # ── Testing ──
    test_phone_number = models.CharField(
        _("Test Mode Phone Number"),
        max_length=20,
        blank=True,
        help_text=_(
            "All SMS sent to this number when channel is in TESTING mode."),
    )

    class Meta:
        verbose_name = _("SMS Channel Configuration")
        verbose_name_plural = _("SMS Channel Configurations")

    def __str__(self):
        return f"SMS Config for {self.channel.name} ({self.provider})"


class PushChannelConfig(MixIdAndTimeModel):
    """
    Firebase Cloud Messaging (FCM) and/or Apple Push Notification Service (APNs)
    configuration for a push notification channel.
    """

    channel = models.OneToOneField(
        NotificationChannel,
        on_delete=models.CASCADE,
        related_name="push_config",
        verbose_name=_("Channel"),
    )

    # ── FCM (Android + Web) ──
    fcm_server_key = models.TextField(
        _("FCM Server Key (encrypted)"),
        blank=True,
        help_text=_("Firebase Cloud Messaging server key. ENCRYPTED."),
    )
    fcm_sender_id = models.CharField(
        _("FCM Sender ID"),
        max_length=100,
        blank=True,
    )
    fcm_project_id = models.CharField(
        _("Firebase Project ID"),
        max_length=100,
        blank=True,
    )
    fcm_service_account_json = models.TextField(
        _("FCM Service Account JSON (encrypted)"),
        blank=True,
        help_text=_(
            "Firebase Admin SDK service account credentials. ENCRYPTED."),
    )

    # ── APNs (iOS) ──
    apns_key_id = models.CharField(
        _("APNs Key ID"),
        max_length=50,
        blank=True,
        help_text=_("10-character key ID from Apple Developer console."),
    )
    apns_team_id = models.CharField(
        _("APNs Team ID"),
        max_length=50,
        blank=True,
        help_text=_("10-character Team ID from Apple Developer console."),
    )
    apns_bundle_id = models.CharField(
        _("APNs Bundle ID"),
        max_length=255,
        blank=True,
        help_text=_("App bundle identifier. e.g. 'com.mystore.app'"),
    )
    apns_private_key = models.TextField(
        _("APNs Private Key (.p8 content, encrypted)"),
        blank=True,
        help_text=_("Contents of the .p8 auth key file. ENCRYPTED."),
    )
    apns_use_sandbox = models.BooleanField(
        _("Use APNs Sandbox"),
        default=False,
        help_text=_("True for development builds, False for production."),
    )

    # ── Web Push (VAPID) ──
    vapid_public_key = models.TextField(
        _("VAPID Public Key"),
        blank=True,
    )
    vapid_private_key = models.TextField(
        _("VAPID Private Key (encrypted)"),
        blank=True,
    )
    vapid_subject = models.EmailField(
        _("VAPID Subject (email or URL)"),
        blank=True,
        help_text=_("Your email or URL for VAPID identification."),
    )

    # ── Defaults ──
    default_icon_url = models.URLField(
        _("Default Notification Icon URL"),
        blank=True,
        help_text=_(
            "Shown as the notification icon if no icon is specified per-send."),
    )
    default_badge_url = models.URLField(
        _("Default Badge URL"),
        blank=True,
    )
    default_sound = models.CharField(
        _("Default Sound"),
        max_length=100,
        blank=True,
        default="default",
    )
    default_click_action = models.URLField(
        _("Default Click Action URL"),
        blank=True,
        help_text=_("URL opened when user taps the notification."),
    )
    ttl_seconds = models.PositiveIntegerField(
        _("Message TTL (seconds)"),
        default=86400,
        help_text=_(
            "How long FCM/APNs stores the message if device is offline. Default: 24h."),
    )

    class Meta:
        verbose_name = _("Push Channel Configuration")
        verbose_name_plural = _("Push Channel Configurations")

    def __str__(self):
        return f"Push Config for {self.channel.name}"


class SlackChannelConfig(MixIdAndTimeModel):
    """
    Slack webhook configuration for internal staff notifications.
    Used for: new orders, low stock alerts, fraud flags, system errors.
    """

    channel = models.OneToOneField(
        NotificationChannel,
        on_delete=models.CASCADE,
        related_name="slack_config",
        verbose_name=_("Channel"),
    )

    # ── Webhook ──
    webhook_url = models.TextField(
        _("Slack Webhook URL (encrypted)"),
        help_text=_("Incoming webhook URL from Slack app settings. ENCRYPTED."),
    )
    bot_token = models.TextField(
        _("Bot Token (encrypted)"),
        blank=True,
        help_text=_(
            "Bot User OAuth Token for advanced Slack API features. ENCRYPTED."),
    )

    # ── Targeting ──
    default_channel = models.CharField(
        _("Default Slack Channel"),
        max_length=100,
        blank=True,
        help_text=_(
            "e.g. '#order-alerts', '#ops-team'. Override per template."),
    )
    default_username = models.CharField(
        _("Bot Username"),
        max_length=80,
        blank=True,
        default="Store Bot",
    )
    default_icon_emoji = models.CharField(
        _("Bot Icon Emoji"),
        max_length=50,
        blank=True,
        default=":bell:",
    )
    default_icon_url = models.URLField(_("Bot Icon URL"), blank=True)

    # ── Mentions ──
    mention_user_ids = models.JSONField(
        _("Default Mention User IDs"),
        default=list,
        blank=True,
        help_text=_(
            "Slack user IDs to @mention in messages. e.g. ['U01234ABCDE']"),
    )
    mention_channel = models.BooleanField(
        _("@channel Mention"),
        default=False,
        help_text=_("Add @channel to every message. Use sparingly."),
    )

    class Meta:
        verbose_name = _("Slack Channel Configuration")
        verbose_name_plural = _("Slack Channel Configurations")

    def __str__(self):
        return f"Slack Config for {self.channel.name}"


# ─────────────────────────────────────────────────────────────
# SECTION 3 — TEMPLATES  (TENANT SCHEMA)
# ─────────────────────────────────────────────────────────────

class NotificationCategory(MixIdAndTimeModel):
    """
    Logical grouping of notification templates.

    Categories serve two purposes:
      1. UI organisation in the template editor
      2. Customer preference management — customers opt in/out per category

    Built-in category slugs (platform-standard):
      transactional     → Order confirmations, receipts (opt-out typically not allowed)
      shipping          → Tracking updates, delivery confirmations
      account           → Password reset, login alerts, account changes
      marketing         → Promotions, newsletters, product recommendations
      abandoned_cart    → Cart recovery emails
      loyalty           → Points, rewards notifications
      reviews           → Review request emails
      inventory         → Back-in-stock, low stock (for merchants)
      fraud             → Risk alerts (staff/internal)
      system            → System events (staff/internal, error alerts)
    """

    slug = models.SlugField(
        _("Slug"),
        max_length=100,
        unique=True,
        help_text=_(
            "Machine-readable identifier. e.g. 'transactional', 'marketing'"),
    )
    name = models.CharField(_("Category Name"), max_length=255)
    description = models.TextField(_("Description"), blank=True)
    display_order = models.PositiveIntegerField(_("Display Order"), default=0)
    is_customer_visible = models.BooleanField(
        _("Visible to Customers"),
        default=True,
        help_text=_(
            "Show this category in the customer notification preferences page. "
            "Set False for internal/staff notifications."
        ),
    )
    allow_customer_opt_out = models.BooleanField(
        _("Allow Customer Opt-Out"),
        default=True,
        help_text=_(
            "If False, customers cannot unsubscribe from this category. "
            "Use for critical transactional notifications required by law/policy."
        ),
    )
    default_opt_in = models.BooleanField(
        _("Default Opt-In"),
        default=True,
        help_text=_(
            "New customers are automatically opted in to this category."),
    )
    icon = models.CharField(_("Icon"), max_length=50, blank=True)
    color = models.CharField(
        _("Color"),
        max_length=7,
        blank=True,
        validators=[RegexValidator(regex=r"^#[0-9A-Fa-f]{6}$|^$")],
    )

    class Meta:
        verbose_name = _("Notification Category")
        verbose_name_plural = _("Notification Categories")
        ordering = ["display_order", "name"]

    def __str__(self):
        return f"{self.name} ({self.slug})"


class NotificationTemplate(MixIdAndTimeModel):
    """
    A versioned, multi-channel notification template.

    Each template corresponds to ONE notification event + ONE channel type.
    If the same event needs to send on both Email and SMS,
    that requires TWO NotificationTemplate records.

    Template events are standardised strings that the application
    fires when specific things happen. Examples:
      order.placed               → Customer order confirmation
      order.shipped              → Shipment notification
      order.delivered            → Delivery confirmation
      order.cancelled            → Cancellation notice
      order.refunded             → Refund confirmation
      return.requested           → Return RMA confirmation
      payment.failed             → Payment failure alert
      password.reset             → Password reset link
      account.created            → Welcome email
      account.email_verified     → Email verification
      cart.abandoned             → Abandoned cart recovery
      product.back_in_stock      → Back-in-stock alert
      review.request             → Post-purchase review request
      loyalty.points_earned      → Loyalty points notification
      staff.order_alert          → Internal order notification (staff)
      staff.low_stock_alert      → Inventory alert (staff)
      staff.fraud_alert          → Risk flag (staff)

    Template content uses Jinja2 syntax with a declared variable schema
    (TemplateVariable records) for validation and editor UI building.

    Active version:
      A template has many versions. Only one version is ACTIVE at a time.
      The active_version FK points to the live NotificationTemplateVersion.
      Editing creates a new version; publishing activates it.
    """

    class TemplateStatus(models.TextChoices):
        DRAFT = "draft", _("Draft — In Progress")
        ACTIVE = "active", _("Active — Used for Sending")
        ARCHIVED = "archived", _("Archived — No Longer Used")
        PAUSED = "paused", _("Paused — Temporarily Disabled")

    category = models.ForeignKey(
        NotificationCategory,
        on_delete=models.PROTECT,
        related_name="templates",
        verbose_name=_("Category"),
    )
    channel = models.ForeignKey(
        NotificationChannel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="templates",
        verbose_name=_("Notification Channel"),
        help_text=_(
            "The channel this template sends through. Null = route by event at send time."),
    )

    # ── Identity ──
    name = models.CharField(
        _("Template Name"),
        max_length=255,
        help_text=_("e.g. 'Order Confirmation Email', 'Shipping SMS'"),
    )
    event_slug = models.SlugField(
        _("Trigger Event"),
        max_length=150,
        db_index=True,
        help_text=_(
            "The event that triggers this template. "
            "e.g. 'order.placed', 'cart.abandoned', 'password.reset'."
        ),
    )
    channel_type = models.CharField(
        _("Channel Type"),
        max_length=15,
        choices=ChannelType.choices,
        db_index=True,
    )
    locale = models.CharField(
        _("Locale"),
        max_length=10,
        default="en",
        db_index=True,
        help_text=_(
            "Language/locale for this template. e.g. 'en', 'fr', 'yo' (Yoruba)."),
    )

    # ── Status ──
    status = models.CharField(
        _("Status"),
        max_length=10,
        choices=TemplateStatus.choices,
        default=TemplateStatus.DRAFT,
        db_index=True,
    )

    # ── Active version pointer ──
    active_version = models.ForeignKey(
        "NotificationTemplateVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="active_for_templates",
        verbose_name=_("Active Version"),
        help_text=_("The currently live version of this template."),
    )

    # ── Sending settings ──
    is_enabled = models.BooleanField(
        _("Enabled"),
        default=True,
        help_text=_("Disabled templates are skipped when their event fires."),
    )
    send_delay_seconds = models.PositiveIntegerField(
        _("Send Delay (seconds)"),
        default=0,
        help_text=_(
            "Delay after the triggering event before sending. "
            "Useful for abandoned cart recovery (wait 1h before sending)."
        ),
    )
    max_send_attempts = models.PositiveSmallIntegerField(
        _("Max Send Attempts"),
        default=3,
        help_text=_("Retry failed sends up to this many times."),
    )
    retry_delay_seconds = models.PositiveIntegerField(
        _("Retry Delay (seconds)"),
        default=300,
        help_text=_("Wait this long between retry attempts."),
    )

    # ── Deduplication ──
    dedup_window_seconds = models.PositiveIntegerField(
        _("Deduplication Window (seconds)"),
        default=0,
        help_text=_(
            "Prevent duplicate sends within this window. "
            "e.g. 3600 = don't send the same event to the same recipient within 1 hour."
        ),
    )

    # ── AB Testing ──
    ab_test_enabled = models.BooleanField(
        _("A/B Test Enabled"),
        default=False,
        help_text=_(
            "Route a percentage of sends to the B variant for testing."),
    )
    ab_test_percentage = models.PositiveSmallIntegerField(
        _("A/B Test Split (% to B variant)"),
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(99)],
    )
    ab_test_variant_b = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ab_test_variants_for",
        verbose_name=_("A/B Test Variant B Template"),
    )

    # ── Metadata ──
    description = models.TextField(_("Internal Description"), blank=True)
    tags = models.JSONField(_("Tags"), default=list, blank=True)
    created_by = models.ForeignKey(
        TenantUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_notification_templates",
    )
    last_modified_by = models.ForeignKey(
        TenantUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="modified_notification_templates",
    )

    class Meta:
        verbose_name = _("Notification Template")
        verbose_name_plural = _("Notification Templates")
        unique_together = [("event_slug", "channel_type", "locale")]
        ordering = ["event_slug", "channel_type"]
        indexes = [
            models.Index(fields=["event_slug", "channel_type", "is_enabled"]),
            models.Index(fields=["status", "is_enabled"]),
            models.Index(fields=["category", "status"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.event_slug} / {self.channel_type} / {self.locale})"


class NotificationTemplateVersion(MixIdAndTimeModel):
    """
    An immutable version snapshot of a NotificationTemplate's content.

    Every time a template is edited, a new version is created.
    Only the version pointed to by NotificationTemplate.active_version is used for sends.

    Versions enable:
      - Full edit history in the template editor
      - Rollback to any prior version
      - A/B testing with two different versions
      - Staged deployment (edit in draft, publish when ready)

    Content fields vary by channel_type:
      EMAIL:   subject, preheader, html_body, text_body
      SMS:     body (plain text only)
      PUSH:    title, body, data_payload (JSON)
      SLACK:   body (Slack Block Kit JSON or Markdown)
      WEBHOOK: body (JSON payload template)
      IN_APP:  title, body, action_url, action_label
    """

    template = models.ForeignKey(
        NotificationTemplate,
        on_delete=models.CASCADE,
        related_name="versions",
        verbose_name=_("Template"),
    )
    version_number = models.PositiveIntegerField(
        _("Version Number"),
        help_text=_("Auto-incremented. Version 1 = initial creation."),
    )
    version_label = models.CharField(
        _("Version Label"),
        max_length=100,
        blank=True,
        help_text=_(
            "Optional human-readable label. e.g. 'Black Friday 2024', 'New Brand Voice'"),
    )

    # ── Email fields ──
    subject = models.TextField(
        _("Subject"),
        blank=True,
        help_text=_(
            "For EMAIL channel. Jinja2 template. e.g. 'Your order #{{ order.number }} is confirmed!'"),
    )
    preheader = models.CharField(
        _("Email Preheader"),
        max_length=255,
        blank=True,
        help_text=_(
            "Preview text shown in inbox list view after subject. "
            "Keep under 90 chars. Jinja2 supported."
        ),
    )
    html_body = models.TextField(
        _("HTML Body"),
        blank=True,
        help_text=_("For EMAIL: full HTML email body. Jinja2 template."),
    )
    text_body = models.TextField(
        _("Plain Text Body"),
        blank=True,
        help_text=_(
            "For EMAIL: plain text fallback. "
            "Auto-generated from html_body if blank (strip HTML). "
            "For SMS: the message body."
        ),
    )

    # ── Push / In-App fields ──
    title = models.CharField(
        _("Title"),
        max_length=255,
        blank=True,
        help_text=_(
            "For PUSH and IN_APP: notification title. Jinja2 supported."),
    )
    body = models.TextField(
        _("Body"),
        blank=True,
        help_text=_(
            "For PUSH, IN_APP, SMS, SLACK: the notification body. "
            "For WEBHOOK: the JSON payload template."
        ),
    )
    action_url = models.CharField(
        _("Action URL"),
        max_length=500,
        blank=True,
        help_text=_(
            "For PUSH/IN_APP: deep link or URL opened on notification tap/click."),
    )
    action_label = models.CharField(
        _("Action Label"),
        max_length=100,
        blank=True,
        help_text=_("For IN_APP: button label for the primary action."),
    )

    # ── Structured / JSON payloads ──
    data_payload = models.JSONField(
        _("Data Payload"),
        default=dict,
        blank=True,
        help_text=_(
            "For PUSH: custom key-value data sent with the notification (not shown to user). "
            "For WEBHOOK: the complete JSON payload structure with Jinja2 placeholders. "
            "For SLACK: Slack Block Kit JSON."
        ),
    )
    email_template_id = models.CharField(
        _("ESP Template ID"),
        max_length=255,
        blank=True,
        help_text=_(
            "External template ID from your ESP (SendGrid, Mailgun, etc.). "
            "When set, the ESP's stored template is used instead of html_body."
        ),
    )

    # ── Media ──
    image_url = models.URLField(
        _("Image URL"),
        blank=True,
        help_text=_("For PUSH/IN_APP: large image shown in the notification."),
    )
    icon_url = models.URLField(
        _("Icon URL"),
        blank=True,
        help_text=_(
            "For PUSH: small icon override for this specific template."),
    )

    # ── Audit ──
    created_by = models.ForeignKey(
        TenantUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_template_versions",
    )
    change_notes = models.TextField(
        _("Change Notes"),
        blank=True,
        help_text=_("What changed in this version."),
    )
    content_hash = models.CharField(
        _("Content Hash (SHA256)"),
        max_length=64,
        blank=True,
        help_text=_(
            "SHA-256 of all content fields combined. Used to detect identical versions."),
    )

    class Meta:
        verbose_name = _("Template Version")
        verbose_name_plural = _("Template Versions")
        unique_together = [("template", "version_number")]
        ordering = ["template", "-version_number"]
        indexes = [
            models.Index(fields=["template", "-version_number"]),
        ]

    def __str__(self):
        label = f" ({self.version_label})" if self.version_label else ""
        return f"{self.template.name} v{self.version_number}{label}"

    def save(self, *args, **kwargs):
        # Auto-generate version number on create
        if not self.pk and not self.version_number:
            last_version = NotificationTemplateVersion.objects.filter(
                template=self.template
            ).order_by("-version_number").values("version_number").first()
            self.version_number = (
                last_version["version_number"] + 1) if last_version else 1

        # Generate content hash
        content_str = "".join([
            self.subject, self.html_body, self.text_body,
            self.title, self.body, str(self.data_payload),
        ])
        self.content_hash = hashlib.sha256(content_str.encode()).hexdigest()
        super().save(*args, **kwargs)

    def activate(self, actor=None):
        """Set this version as the active version for its template."""
        self.template.active_version = self
        self.template.status = NotificationTemplate.TemplateStatus.ACTIVE
        self.template.last_modified_by = actor
        self.template.save(update_fields=[
            "active_version", "status", "last_modified_by", "updated_at"
        ])


class TemplateVariable(MixIdAndTimeModel):
    """
    Declares a variable available in a NotificationTemplate's Jinja2 content.

    Serves three purposes:
      1. Documentation — describes what context variables are available
      2. Editor UI — drives the variable picker in the template editor
      3. Validation — validates that required variables are provided at send time

    Variable types:
      STRING  → Plain text value
      NUMBER  → Numeric value (int or float)
      BOOLEAN → True/False
      URL     → URL string (validated)
      DATE    → datetime object (formatted by filter in template)
      OBJECT  → Nested dict (sub-keys documented in sub_variables JSON)
      LIST    → List of items

    Variable path notation:
      Simple:   order_number       → {{ order_number }}
      Nested:   order.number       → {{ order.number }}
      Filter:   order.placed_at    → {{ order.placed_at | format_date }}
    """

    class VariableType(models.TextChoices):
        STRING = "string", _("String")
        NUMBER = "number", _("Number")
        BOOLEAN = "boolean", _("Boolean")
        URL = "url", _("URL")
        DATE = "date", _("Date / DateTime")
        OBJECT = "object", _("Object (nested dict)")
        LIST = "list", _("List")

    template = models.ForeignKey(
        NotificationTemplate,
        on_delete=models.CASCADE,
        related_name="variables",
        verbose_name=_("Template"),
    )

    # ── Identity ──
    key = models.CharField(
        _("Variable Key"),
        max_length=100,
        help_text=_(
            "Dot-notation path. e.g. 'order.number', 'customer.first_name'"),
    )
    label = models.CharField(
        _("Display Label"),
        max_length=255,
        help_text=_("Human-readable name shown in the template editor."),
    )
    description = models.TextField(
        _("Description"),
        blank=True,
        help_text=_("What this variable contains and when it's available."),
    )
    variable_type = models.CharField(
        _("Type"),
        max_length=10,
        choices=VariableType.choices,
        default=VariableType.STRING,
    )

    # ── Validation ──
    is_required = models.BooleanField(
        _("Required"),
        default=False,
        help_text=_(
            "Send will fail if this variable is missing from the context."),
    )
    default_value = models.TextField(
        _("Default Value"),
        blank=True,
        help_text=_("Fallback value if variable is not provided in context."),
    )
    example_value = models.TextField(
        _("Example Value"),
        blank=True,
        help_text=_("Example value shown in the template editor preview."),
    )

    # ── Object sub-keys documentation ──
    sub_variables = models.JSONField(
        _("Sub-Variables"),
        default=list,
        blank=True,
        help_text=_(
            "For OBJECT type: list of {key, label, type, description} for nested keys. "
            'e.g. [{"key": "order.number", "label": "Order Number", "type": "string"}]'
        ),
    )

    # ── Source ──
    source_app = models.CharField(
        _("Source App"),
        max_length=50,
        blank=True,
        help_text=_(
            "Django app that provides this variable. "
            "e.g. 'orders', 'accounts', 'catalog'"
        ),
    )

    class Meta:
        verbose_name = _("Template Variable")
        verbose_name_plural = _("Template Variables")
        unique_together = [("template", "key")]
        ordering = ["template", "key"]

    def __str__(self):
        req = " *" if self.is_required else ""
        return f"{self.template.name} — {{ {self.key} }}{req} ({self.variable_type})"
