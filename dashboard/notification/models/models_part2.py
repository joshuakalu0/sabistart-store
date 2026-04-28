"""
notifications/models_part2.py  — Part 2 of 3
==============================================
SECTION 4 — CUSTOMER PREFERENCES
SECTION 5 — OUTBOUND QUEUE & DELIVERY
SECTION 6 — WEBHOOKS
"""

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import timedelta

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
from public.userauth.models import Customer, TenantUser
from .models_part1 import (
    MixIdAndTimeModel,
    ChannelType,
    DeliveryStatus,
    NotificationCategory,
    NotificationTemplate,
    NotificationTemplateVersion,
    NotificationChannel,
)


# ─────────────────────────────────────────────────────────────
# SECTION 4 — CUSTOMER PREFERENCES (TENANT SCHEMA)
# ─────────────────────────────────────────────────────────────

class NotificationPreference(MixIdAndTimeModel):
    """
    Per-customer opt-in/opt-out settings per notification category and channel.

    One record per (customer × category × channel_type) combination.
    If no record exists for a combination, the category's default_opt_in
    value applies.

    Lifecycle:
      - Created with is_subscribed=True when a customer places their first order
        or explicitly subscribes (e.g. newsletter checkbox at checkout).
      - Set to is_subscribed=False when customer opts out
        (via unsubscribe link, account settings, or we receive a bounce).
      - opt_out_method tracks HOW the customer unsubscribed for compliance.
    """

    class OptOutMethod(models.TextChoices):
        CUSTOMER_REQUEST = "customer_request", _(
            "Customer Request (Settings Page)")
        UNSUBSCRIBE_LINK = "unsubscribe_link", _(
            "Unsubscribe Link (Email Footer)")
        ONE_CLICK_UNSUBSCRIBE = "one_click", _(
            "One-Click Unsubscribe (Gmail/Yahoo)")
        BOUNCE = "bounce", _("Hard Bounce — Address Invalid")
        SPAM_COMPLAINT = "spam_complaint", _("Spam / Abuse Complaint")
        ADMIN = "admin", _("Admin Action")
        IMPORT = "import", _("Bulk Import")
        API = "api", _("API")

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
        verbose_name=_("Customer"),
    )
    category = models.ForeignKey(
        NotificationCategory,
        on_delete=models.CASCADE,
        related_name="customer_preferences",
        verbose_name=_("Category"),
    )
    channel_type = models.CharField(
        _("Channel Type"),
        max_length=15,
        choices=ChannelType.choices,
        db_index=True,
    )

    # ── Subscription state ──
    is_subscribed = models.BooleanField(
        _("Subscribed"),
        default=True,
        db_index=True,
    )
    opted_in_at = models.DateTimeField(
        _("Opted In At"),
        null=True,
        blank=True,
    )
    opted_out_at = models.DateTimeField(
        _("Opted Out At"),
        null=True,
        blank=True,
    )
    opt_out_method = models.CharField(
        _("Opt-Out Method"),
        max_length=20,
        choices=OptOutMethod.choices,
        blank=True,
    )

    # ── Frequency controls ──
    max_per_day = models.PositiveSmallIntegerField(
        _("Max Notifications Per Day"),
        null=True,
        blank=True,
        help_text=_(
            "Customer-set limit on daily notifications in this category."),
    )
    quiet_hours_start = models.TimeField(
        _("Quiet Hours Start"),
        null=True,
        blank=True,
        help_text=_(
            "Don't send between quiet_hours_start and quiet_hours_end."),
    )
    quiet_hours_end = models.TimeField(
        _("Quiet Hours End"),
        null=True,
        blank=True,
    )
    preferred_timezone = models.CharField(
        _("Preferred Timezone"),
        max_length=50,
        blank=True,
        help_text=_("For scheduling quiet hours. e.g. 'Africa/Lagos'"),
    )

    # ── Source of initial consent ──
    consent_source = models.CharField(
        _("Consent Source"),
        max_length=100,
        blank=True,
        help_text=_(
            "Where the customer gave consent. "
            "e.g. 'checkout_checkbox', 'account_registration', 'import'"
        ),
    )
    consent_ip = models.GenericIPAddressField(
        _("Consent IP Address"),
        null=True,
        blank=True,
    )
    consent_user_agent = models.TextField(_("Consent User Agent"), blank=True)

    class Meta:
        verbose_name = _("Notification Preference")
        verbose_name_plural = _("Notification Preferences")
        unique_together = [("customer", "category", "channel_type")]
        ordering = ["customer", "category"]
        indexes = [
            models.Index(fields=["customer", "is_subscribed"]),
            models.Index(fields=["category", "channel_type", "is_subscribed"]),
        ]

    def __str__(self):
        status = "✓" if self.is_subscribed else "✗"
        return f"{status} {self.customer} — {self.category.name} via {self.channel_type}"

    def unsubscribe(self, method: str = "customer_request"):
        self.is_subscribed = False
        self.opted_out_at = timezone.now()
        self.opt_out_method = method
        self.save(update_fields=["is_subscribed",
                  "opted_out_at", "opt_out_method", "updated_at"])

    def resubscribe(self, source: str = "customer_request"):
        self.is_subscribed = True
        self.opted_in_at = timezone.now()
        self.opt_out_method = ""
        self.opted_out_at = None
        self.consent_source = source
        self.save(update_fields=[
            "is_subscribed", "opted_in_at", "opt_out_method",
            "opted_out_at", "consent_source", "updated_at",
        ])


class CustomerDevice(MixIdAndTimeModel):
    """
    A push notification device token registered by a customer.

    A single customer can have multiple devices:
      - iPhone (APNs token)
      - Android phone (FCM token)
      - Web browser on laptop (Web Push subscription)

    Tokens are rotated by FCM/APNs periodically. When a new token
    is registered for the same device fingerprint, the old one is
    updated rather than creating a duplicate.

    Token validity:
      Sending to an invalid token returns an error from FCM/APNs.
      The delivery system automatically marks tokens as INVALID
      on receipt of specific error codes (NotRegistered, InvalidRegistration).
    """

    class DevicePlatform(models.TextChoices):
        IOS = "ios", _("iOS (APNs)")
        ANDROID = "android", _("Android (FCM)")
        WEB = "web", _("Web Browser (Web Push)")
        WINDOWS = "windows", _("Windows (WNS)")
        MACOS = "macos", _("macOS Desktop")

    class TokenStatus(models.TextChoices):
        ACTIVE = "active", _("Active — Valid Token")
        INVALID = "invalid", _("Invalid — Token Rejected by Provider")
        EXPIRED = "expired", _("Expired — TTL Exceeded")
        UNREGISTERED = "unregistered", _("Unregistered — App Uninstalled")
        REPLACED = "replaced", _("Replaced — Newer Token Available")

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="devices",
        verbose_name=_("Customer"),
    )

    # ── Token ──
    push_token = models.TextField(
        _("Push Token"),
        db_index=True,
        help_text=_(
            "FCM registration token, APNs device token, or Web Push subscription JSON."),
    )
    push_token_hash = models.CharField(
        _("Token Hash (SHA256)"),
        max_length=64,
        db_index=True,
        help_text=_(
            "SHA-256 of the push_token. Used for fast deduplication lookups."),
    )
    platform = models.CharField(
        _("Platform"),
        max_length=10,
        choices=DevicePlatform.choices,
        db_index=True,
    )
    status = models.CharField(
        _("Token Status"),
        max_length=15,
        choices=TokenStatus.choices,
        default=TokenStatus.ACTIVE,
        db_index=True,
    )

    # ── Device metadata ──
    device_name = models.CharField(
        _("Device Name"),
        max_length=255,
        blank=True,
        help_text=_("User-friendly device name. e.g. 'Jane's iPhone 15 Pro'"),
    )
    device_model = models.CharField(
        _("Device Model"),
        max_length=100,
        blank=True,
        help_text=_(
            "Device model. e.g. 'iPhone 15 Pro', 'Pixel 8', 'Chrome on Windows'"),
    )
    os_version = models.CharField(_("OS Version"), max_length=50, blank=True)
    app_version = models.CharField(_("App Version"), max_length=20, blank=True)
    device_fingerprint = models.CharField(
        _("Device Fingerprint"),
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_(
            "Stable identifier for this physical device. "
            "Used to update token when it rotates without creating duplicates."
        ),
    )

    # ── Notification settings ──
    is_notification_enabled = models.BooleanField(
        _("Notifications Enabled"),
        default=True,
        help_text=_(
            "False if user has revoked push notification permission on the device."),
    )
    badge_count = models.PositiveIntegerField(
        _("Current Badge Count"),
        default=0,
    )

    # ── Registration ──
    registered_at = models.DateTimeField(
        _("Registered At"), default=timezone.now)
    last_seen_at = models.DateTimeField(
        _("Last Seen At"),
        null=True,
        blank=True,
        help_text=_("Last time the app reported activity from this device."),
    )
    invalidated_at = models.DateTimeField(
        _("Invalidated At"), null=True, blank=True)
    invalidation_reason = models.CharField(
        _("Invalidation Reason"),
        max_length=100,
        blank=True,
        help_text=_("Provider error code that caused invalidation."),
    )

    class Meta:
        verbose_name = _("Customer Device")
        verbose_name_plural = _("Customer Devices")
        ordering = ["-registered_at"]
        indexes = [
            models.Index(fields=["customer", "platform", "status"]),
            models.Index(fields=["push_token_hash"]),
            models.Index(fields=["device_fingerprint"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.customer} — {self.platform} ({self.device_model or 'Unknown device'})"

    def save(self, *args, **kwargs):
        if self.push_token and not self.push_token_hash:
            self.push_token_hash = hashlib.sha256(
                self.push_token.encode()
            ).hexdigest()
        super().save(*args, **kwargs)

    def invalidate(self, reason: str = ""):
        self.status = self.TokenStatus.INVALID
        self.invalidated_at = timezone.now()
        self.invalidation_reason = reason
        self.save(update_fields=["status", "invalidated_at",
                  "invalidation_reason", "updated_at"])


class NotificationBlacklist(MixIdAndTimeModel):
    """
    Global suppression list — addresses/numbers that must NEVER receive messages.

    Records are created when:
      - Hard bounce is received (email address doesn't exist)
      - Spam complaint is received
      - Customer unsubscribes globally (all channels)
      - Admin manually adds an address

    The delivery pipeline checks this list before every send and
    skips suppressed recipients, logging a SUPPRESSED status.

    entry_type covers all channel types:
      EMAIL   → email@address.com
      SMS     → +2348012345678 (E.164 format)
      PUSH    → device_token_hash (SHA-256 of the push token)
    """

    class EntryType(models.TextChoices):
        EMAIL = "email", _("Email Address")
        SMS = "sms", _("Phone Number (E.164)")
        PUSH = "push", _("Push Token Hash")

    class SuppressReason(models.TextChoices):
        HARD_BOUNCE = "hard_bounce", _("Hard Bounce")
        SOFT_BOUNCE_REPEATED = "soft_bounce_repeated", _(
            "Repeated Soft Bounces")
        SPAM_COMPLAINT = "spam_complaint", _("Spam / Abuse Complaint")
        GLOBAL_UNSUBSCRIBE = "global_unsubscribe", _("Global Unsubscribe")
        INVALID_FORMAT = "invalid_format", _("Invalid Format")
        ADMIN = "admin", _("Added by Admin")
        LEGAL = "legal", _("Legal / GDPR Request")
        FRAUD = "fraud", _("Fraud / Abuse")

    entry_type = models.CharField(
        _("Entry Type"),
        max_length=10,
        choices=EntryType.choices,
        db_index=True,
    )
    value = models.CharField(
        _("Suppressed Value"),
        max_length=500,
        db_index=True,
        help_text=_(
            "The email address, phone number, or token hash to suppress."),
    )
    value_hash = models.CharField(
        _("Value Hash (SHA256)"),
        max_length=64,
        db_index=True,
        help_text=_("Hashed version for privacy-preserving lookups."),
    )
    reason = models.CharField(
        _("Suppression Reason"),
        max_length=25,
        choices=SuppressReason.choices,
    )
    source_log_id = models.UUIDField(
        _("Source Notification Log ID"),
        null=True,
        blank=True,
        help_text=_(
            "FK-less ref to the NotificationLog that triggered this suppression."),
    )
    added_by = models.ForeignKey(
        TenantUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="added_blacklist_entries",
    )
    note = models.TextField(_("Note"), blank=True)
    expires_at = models.DateTimeField(
        _("Expires At"),
        null=True,
        blank=True,
        help_text=_("Auto-remove entry at this time. Null = permanent."),
    )

    class Meta:
        verbose_name = _("Notification Blacklist Entry")
        verbose_name_plural = _("Notification Blacklist")
        unique_together = [("entry_type", "value_hash")]
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["entry_type", "value_hash"]),
            models.Index(fields=["reason"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"[{self.entry_type}] {self.value[:30]}... — {self.reason}"

    def save(self, *args, **kwargs):
        if self.value and not self.value_hash:
            self.value_hash = hashlib.sha256(
                self.value.lower().strip().encode()
            ).hexdigest()
        super().save(*args, **kwargs)

    @classmethod
    def is_suppressed(cls, entry_type: str, value: str) -> bool:
        """Fast blacklist check using the hashed value."""
        value_hash = hashlib.sha256(value.lower().strip().encode()).hexdigest()
        return cls.objects.filter(
            entry_type=entry_type,
            value_hash=value_hash,
        ).filter(
            models.Q(expires_at__isnull=True) | models.Q(
                expires_at__gt=timezone.now())
        ).exists()


def get_default_expiry():
    """Provides a named reference for Django migrations."""
    return timezone.now() + timedelta(days=30)


class UnsubscribeToken(MixIdAndTimeModel):
    """
    A secure, time-limited, single-use token for one-click email unsubscribe.

    Each unsubscribe link in an email footer contains a URL with this token.
    When clicked:
      1. Token is looked up and validated (not expired, not used)
      2. Customer's NotificationPreference for the category+channel is updated
      3. Token is marked used
      4. Customer is redirected to a confirmation page

    Supports:
      - Category-specific unsubscribe ("unsubscribe from order emails")
      - Global unsubscribe ("unsubscribe from all emails")
      - RFC 8058 List-Unsubscribe-Post for Gmail/Yahoo one-click unsubscribe
    """

    token = models.CharField(
        _("Token"),
        max_length=128,
        unique=True,
        db_index=True,
        default=secrets.token_urlsafe,
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="unsubscribe_tokens",
        verbose_name=_("Customer"),
    )
    category = models.ForeignKey(
        NotificationCategory,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="unsubscribe_tokens",
        verbose_name=_("Category"),
        help_text=_("Null = global unsubscribe (all categories)."),
    )
    channel_type = models.CharField(
        _("Channel Type"),
        max_length=15,
        choices=ChannelType.choices,
        db_index=True,
    )
    notification_log_id = models.UUIDField(
        _("Notification Log ID"),
        null=True,
        blank=True,
        help_text=_(
            "FK-less ref to the NotificationLog this token was generated for."),
    )

    # ── State ──
    is_used = models.BooleanField(_("Used"), default=False)
    used_at = models.DateTimeField(_("Used At"), null=True, blank=True)
    used_ip = models.GenericIPAddressField(
        _("Used From IP"), null=True, blank=True)
    expires_at = models.DateTimeField(
        _("Expires At"),
        default=get_default_expiry,  # Note: Reference the function name, don't call it!
        db_index=True,
    )
    is_global = models.BooleanField(
        _("Global Unsubscribe"),
        default=False,
        help_text=_(
            "If True, unsubscribes from ALL categories on this channel."),
    )

    class Meta:
        verbose_name = _("Unsubscribe Token")
        verbose_name_plural = _("Unsubscribe Tokens")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["customer", "channel_type"]),
        ]

    def __str__(self):
        scope = "ALL" if self.is_global else (
            self.category.name if self.category else "Unknown")
        return f"Unsub token for {self.customer} / {scope} / {self.channel_type}"

    @property
    def is_valid(self) -> bool:
        return not self.is_used and self.expires_at > timezone.now()

    def consume(self, ip_address: str = "") -> bool:
        """Mark token as used. Returns False if already used/expired."""
        if not self.is_valid:
            return False
        self.is_used = True
        self.used_at = timezone.now()
        self.used_ip = ip_address or None
        self.save(update_fields=["is_used",
                  "used_at", "used_ip", "updated_at"])
        return True


# ─────────────────────────────────────────────────────────────
# SECTION 5 — OUTBOUND QUEUE & DELIVERY (TENANT SCHEMA)
# ─────────────────────────────────────────────────────────────

class NotificationJob(MixIdAndTimeModel):
    """
    A scheduled or queued outbound notification task.

    A NotificationJob is created when an event fires and needs to
    trigger a notification. It is SEPARATE from NotificationLog:
      - NotificationJob = the task to be executed (mutable, stateful)
      - NotificationLog = the immutable record of what was sent

    Job lifecycle:
      QUEUED       → Created, waiting for worker to pick up
      SCHEDULED    → Waiting for a future send_at time
      PROCESSING   → Worker is currently building and sending
      COMPLETED    → All sends completed (check child NotificationLogs for status)
      FAILED       → All retry attempts exhausted
      CANCELLED    → Explicitly cancelled before sending
      PAUSED       → Temporarily held (e.g. during blackout window)

    One job can produce MULTIPLE NotificationLog records:
      - A broadcast campaign job → one log per recipient
      - A bulk notification → one log per send channel (email + SMS)
    """

    class JobStatus(models.TextChoices):
        QUEUED = "queued", _("Queued — Waiting for Worker")
        SCHEDULED = "scheduled", _("Scheduled — Waiting for send_at Time")
        PROCESSING = "processing", _("Processing — Being Sent")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed — All Retries Exhausted")
        CANCELLED = "cancelled", _("Cancelled")
        PAUSED = "paused", _("Paused")

    class JobPriority(models.IntegerChoices):
        CRITICAL = 0, _("Critical (immediate, e.g. fraud alert)")
        HIGH = 1, _("High (e.g. order confirmation)")
        NORMAL = 5, _("Normal (e.g. shipping update)")
        LOW = 10, _("Low (e.g. marketing)")

    # ── Template & channel ──
    template = models.ForeignKey(
        NotificationTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jobs",
        verbose_name=_("Template"),
    )
    template_version = models.ForeignKey(
        NotificationTemplateVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jobs",
        verbose_name=_("Template Version"),
        help_text=_(
            "Pinned version at job creation time. Ensures template changes don't affect queued jobs."),
    )
    channel = models.ForeignKey(
        NotificationChannel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jobs",
        verbose_name=_("Channel"),
    )
    channel_type = models.CharField(
        _("Channel Type"),
        max_length=15,
        choices=ChannelType.choices,
        db_index=True,
    )

    # ── Recipient ──
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notification_jobs",
        verbose_name=_("Customer"),
    )
    recipient_email = models.EmailField(_("Recipient Email"), blank=True)
    recipient_phone = models.CharField(
        _("Recipient Phone"), max_length=30, blank=True)
    recipient_device_id = models.UUIDField(
        _("Recipient Device ID"),
        null=True,
        blank=True,
        help_text=_("FK-less ref to CustomerDevice for push notifications."),
    )
    recipient_name = models.CharField(
        _("Recipient Name"), max_length=255, blank=True)

    # ── Event context ──
    event_slug = models.SlugField(
        _("Trigger Event"),
        max_length=150,
        db_index=True,
    )
    event_object_type = models.CharField(
        _("Event Object Type"),
        max_length=100,
        blank=True,
        help_text=_(
            "The model name of the triggering object. e.g. 'Order', 'Cart', 'Customer'"),
    )
    event_object_id = models.UUIDField(
        _("Event Object ID"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("UUID of the object that triggered this notification."),
    )
    context_data = models.JSONField(
        _("Context Data"),
        default=dict,
        help_text=_(
            "The full Jinja2 template rendering context. "
            "Captured at job creation time so template renders correctly even "
            "if the underlying data changes before the job is processed."
        ),
    )

    # ── Scheduling ──
    priority = models.IntegerField(
        _("Priority"),
        choices=JobPriority.choices,
        default=JobPriority.NORMAL,
        db_index=True,
    )
    send_at = models.DateTimeField(
        _("Send At"),
        default=timezone.now,
        db_index=True,
        help_text=_("The job will not be processed before this time."),
    )
    expires_at = models.DateTimeField(
        _("Expires At"),
        null=True,
        blank=True,
        help_text=_("If not sent by this time, mark as FAILED and discard."),
    )

    # ── Status ──
    status = models.CharField(
        _("Status"),
        max_length=15,
        choices=JobStatus.choices,
        default=JobStatus.QUEUED,
        db_index=True,
    )

    # ── Retry tracking ──
    attempt_count = models.PositiveSmallIntegerField(
        _("Attempt Count"),
        default=0,
    )
    max_attempts = models.PositiveSmallIntegerField(
        _("Max Attempts"),
        default=3,
    )
    next_attempt_at = models.DateTimeField(
        _("Next Attempt At"),
        null=True,
        blank=True,
        db_index=True,
    )
    last_attempt_at = models.DateTimeField(
        _("Last Attempt At"),
        null=True,
        blank=True,
    )
    last_error = models.TextField(
        _("Last Error"),
        blank=True,
        help_text=_("Error message from the most recent failed attempt."),
    )

    # ── Deduplication ──
    dedup_key = models.CharField(
        _("Deduplication Key"),
        max_length=255,
        blank=True,
        db_index=True,
        help_text=_(
            "Unique key for this event+recipient combination within the dedup window. "
            "Format: {event_slug}:{recipient_email}:{object_id}. "
            "Prevents duplicate sends."
        ),
    )

    # ── Worker tracking ──
    worker_id = models.CharField(
        _("Worker ID"),
        max_length=100,
        blank=True,
        help_text=_("ID of the Celery worker currently processing this job."),
    )
    celery_task_id = models.CharField(
        _("Celery Task ID"),
        max_length=255,
        blank=True,
    )

    # ── Completion ──
    completed_at = models.DateTimeField(
        _("Completed At"), null=True, blank=True)
    cancelled_at = models.DateTimeField(
        _("Cancelled At"), null=True, blank=True)
    cancelled_reason = models.CharField(
        _("Cancellation Reason"), max_length=500, blank=True)

    class Meta:
        verbose_name = _("Notification Job")
        verbose_name_plural = _("Notification Jobs")
        ordering = ["priority", "send_at"]
        indexes = [
            models.Index(fields=["status", "priority", "send_at"]),
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["event_slug", "status"]),
            models.Index(fields=["dedup_key"]),
            models.Index(fields=["event_object_type", "event_object_id"]),
            models.Index(fields=["customer", "status"]),
        ]

    def __str__(self):
        return (
            f"Job {self.id} — {self.event_slug} via {self.channel_type} "
            f"to {self.recipient_email or self.recipient_phone} [{self.status}]"
        )

    def schedule_retry(self, error: str = "", delay_seconds: int = 300):
        """Schedule a retry attempt after the given delay."""
        self.attempt_count += 1
        self.last_error = error
        self.last_attempt_at = timezone.now()

        if self.attempt_count >= self.max_attempts:
            self.status = self.JobStatus.FAILED
            self.next_attempt_at = None
        else:
            self.status = self.JobStatus.QUEUED
            self.next_attempt_at = timezone.now() + timedelta(seconds=delay_seconds)

        self.save(update_fields=[
            "attempt_count", "last_error", "last_attempt_at",
            "status", "next_attempt_at", "updated_at",
        ])

    def mark_completed(self):
        self.status = self.JobStatus.COMPLETED
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "completed_at", "updated_at"])

    def cancel(self, reason: str = ""):
        self.status = self.JobStatus.CANCELLED
        self.cancelled_at = timezone.now()
        self.cancelled_reason = reason
        self.save(update_fields=["status", "cancelled_at",
                  "cancelled_reason", "updated_at"])


class NotificationLog(MixIdAndTimeModel):
    """
    IMMUTABLE append-only delivery record for every send attempt.
    Never UPDATE or DELETE — only INSERT.

    One NotificationLog per individual send attempt.
    A single NotificationJob may produce multiple logs if it retries.

    The full delivery lifecycle is tracked via NotificationEvent records
    (also append-only) which form the event timeline.

    Status transitions:
      PENDING → PROCESSING → SENT → DELIVERED → OPENED → CLICKED
      PENDING → PROCESSING → FAILED → (new log for retry)
      PENDING → SUPPRESSED (no send attempted — blacklist/preference check failed)
    """

    # ── Job reference ──
    job = models.ForeignKey(
        NotificationJob,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logs",
        verbose_name=_("Notification Job"),
    )

    # ── Template snapshot ──
    template = models.ForeignKey(
        NotificationTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logs",
        verbose_name=_("Template"),
    )
    template_version_number = models.PositiveIntegerField(
        _("Template Version Number"),
        null=True,
        blank=True,
        help_text=_(
            "Snapshot of the version used. Preserved even if version is deleted."),
    )

    # ── Channel ──
    channel = models.ForeignKey(
        NotificationChannel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logs",
        verbose_name=_("Channel"),
    )
    channel_type = models.CharField(
        _("Channel Type"),
        max_length=15,
        choices=ChannelType.choices,
        db_index=True,
    )

    # ── Recipient ──
    customer = models.ForeignKey(
        Customer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notification_logs",
        verbose_name=_("Customer"),
    )
    recipient_address = models.CharField(
        _("Recipient Address"),
        max_length=500,
        db_index=True,
        help_text=_(
            "The exact address delivered to. "
            "Email: 'user@email.com'. SMS: '+2348012345678'. "
            "Push: device token hash (not the raw token)."
        ),
    )
    recipient_name = models.CharField(
        _("Recipient Name"), max_length=255, blank=True)

    # ── Delivery status ──
    status = models.CharField(
        _("Delivery Status"),
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
        db_index=True,
    )
    status_updated_at = models.DateTimeField(
        _("Status Updated At"),
        null=True,
        blank=True,
        help_text=_("Timestamp of the most recent status change."),
    )

    # ── Provider response ──
    provider_message_id = models.CharField(
        _("Provider Message ID"),
        max_length=500,
        blank=True,
        db_index=True,
        help_text=_(
            "Message ID returned by the delivery provider. "
            "e.g. SendGrid message ID, Twilio SID, FCM message ID."
        ),
    )
    provider_response_code = models.CharField(
        _("Provider Response Code"),
        max_length=20,
        blank=True,
        help_text=_(
            "HTTP status code or provider-specific status code returned on send."),
    )
    provider_response_body = models.TextField(
        _("Provider Response Body"),
        blank=True,
        help_text=_(
            "Raw response body from the provider. Truncated to 5000 chars."),
    )
    error_code = models.CharField(
        _("Error Code"),
        max_length=100,
        blank=True,
        help_text=_(
            "Standardised internal error code. e.g. 'INVALID_TOKEN', 'RATE_LIMITED'"),
    )
    error_message = models.TextField(_("Error Message"), blank=True)

    # ── Content snapshot ──
    rendered_subject = models.TextField(
        _("Rendered Subject"),
        blank=True,
        help_text=_("The fully rendered subject line sent to the recipient."),
    )
    rendered_body_preview = models.TextField(
        _("Rendered Body Preview"),
        blank=True,
        help_text=_(
            "First 500 chars of the rendered body for debugging. "
            "Does NOT store the full body (PII concern)."
        ),
    )

    # ── Event context ──
    event_slug = models.SlugField(
        _("Trigger Event"),
        max_length=150,
        db_index=True,
    )
    event_object_type = models.CharField(
        _("Event Object Type"), max_length=100, blank=True)
    event_object_id = models.UUIDField(
        _("Event Object ID"),
        null=True,
        blank=True,
        db_index=True,
    )

    # ── Engagement tracking ──
    opened_at = models.DateTimeField(_("Opened At"), null=True, blank=True)
    clicked_at = models.DateTimeField(_("Clicked At"), null=True, blank=True)
    clicked_url = models.URLField(_("First Clicked URL"), blank=True)
    open_count = models.PositiveIntegerField(_("Open Count"), default=0)
    click_count = models.PositiveIntegerField(_("Click Count"), default=0)
    unsubscribed_at = models.DateTimeField(
        _("Unsubscribed At"), null=True, blank=True)

    # ── Timing ──
    sent_at = models.DateTimeField(_("Sent At"), null=True, blank=True)
    delivered_at = models.DateTimeField(
        _("Delivered At"), null=True, blank=True)
    duration_ms = models.PositiveIntegerField(
        _("Send Duration (ms)"),
        null=True,
        blank=True,
        help_text=_(
            "Time taken from job pickup to provider acceptance, in milliseconds."),
    )

    # ── A/B Test ──
    ab_variant = models.CharField(
        _("A/B Test Variant"),
        max_length=5,
        blank=True,
        help_text=_("'A' or 'B' if this send was part of an A/B test."),
    )

    # ── Suppression detail ──
    suppression_reason = models.CharField(
        _("Suppression Reason"),
        max_length=50,
        blank=True,
        help_text=_("If status=SUPPRESSED: why this send was blocked."),
    )

    class Meta:
        verbose_name = _("Notification Log")
        verbose_name_plural = _("Notification Logs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["channel_type", "-created_at"]),
            models.Index(fields=["event_slug", "-created_at"]),
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["recipient_address", "-created_at"]),
            models.Index(fields=["provider_message_id"]),
            models.Index(fields=["event_object_type", "event_object_id"]),
            models.Index(fields=["template", "status"]),
        ]

    def __str__(self):
        return (
            f"Log {self.id} — {self.event_slug} to {self.recipient_address[:30]} "
            f"[{self.status}] at {self.created_at.strftime('%Y-%m-%d %H:%M')}"
        )


class NotificationEvent(MixIdAndTimeModel):
    """
    IMMUTABLE event timeline for a NotificationLog.
    One record per status transition or notable event.
    Never UPDATE or DELETE — only INSERT.

    Event types:
      QUEUED          → Job created and queued
      SEND_ATTEMPTED  → Delivery attempted to provider
      SENT            → Provider accepted the message
      DELIVERED       → Provider confirmed delivery
      OPENED          → Recipient opened the message
      CLICKED         → Recipient clicked a link
      BOUNCED         → Hard bounce received
      SOFT_BOUNCED    → Soft bounce received
      FAILED          → Send attempt failed
      RETRY_SCHEDULED → Failed, retry queued
      CANCELLED       → Job cancelled before send
      SUPPRESSED      → Skipped due to preferences/blacklist
      UNSUBSCRIBED    → Recipient unsubscribed
      SPAM_REPORTED   → Spam complaint received
      PROVIDER_UPDATE → Webhook update from provider
    """

    class EventType(models.TextChoices):
        QUEUED = "queued", _("Queued")
        SEND_ATTEMPTED = "send_attempted", _("Send Attempted")
        SENT = "sent", _("Sent")
        DELIVERED = "delivered", _("Delivered")
        OPENED = "opened", _("Opened")
        CLICKED = "clicked", _("Clicked")
        BOUNCED = "bounced", _("Bounced")
        SOFT_BOUNCED = "soft_bounced", _("Soft Bounced")
        FAILED = "failed", _("Failed")
        RETRY_SCHEDULED = "retry_scheduled", _("Retry Scheduled")
        CANCELLED = "cancelled", _("Cancelled")
        SUPPRESSED = "suppressed", _("Suppressed")
        UNSUBSCRIBED = "unsubscribed", _("Unsubscribed")
        SPAM_REPORTED = "spam_reported", _("Spam Reported")
        PROVIDER_UPDATE = "provider_update", _("Provider Webhook Update")

    notification_log = models.ForeignKey(
        NotificationLog,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name=_("Notification Log"),
    )
    event_type = models.CharField(
        _("Event Type"),
        max_length=20,
        choices=EventType.choices,
        db_index=True,
    )
    detail = models.TextField(
        _("Detail"),
        blank=True,
        help_text=_("Human-readable description of this event."),
    )
    metadata = models.JSONField(
        _("Metadata"),
        default=dict,
        blank=True,
        help_text=_(
            "Structured data for this event. "
            "For CLICKED: {url: '...'}. For BOUNCED: {bounce_type, diagnostic_code}. "
            "For PROVIDER_UPDATE: raw webhook payload."
        ),
    )
    source = models.CharField(
        _("Source"),
        max_length=50,
        blank=True,
        help_text=_(
            "e.g. 'provider_webhook', 'worker', 'pixel_tracker', 'click_tracker'"),
    )
    ip_address = models.GenericIPAddressField(
        _("IP Address"), null=True, blank=True)
    user_agent = models.TextField(_("User Agent"), blank=True)

    class Meta:
        verbose_name = _("Notification Event")
        verbose_name_plural = _("Notification Events")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["notification_log", "event_type"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]

    def __str__(self):
        return f"[{self.event_type}] on Log {self.notification_log_id} at {self.created_at}"


class BounceRecord(MixIdAndTimeModel):
    """
    Hard or soft bounce records for email deliverability management.
    APPEND-ONLY — never update or delete.

    Hard bounces (permanent failure — address doesn't exist):
      → Automatically added to NotificationBlacklist
      → Customer email marked as invalid

    Soft bounces (temporary failure — mailbox full, server down):
      → Tracked for pattern detection
      → After N soft bounces, treated as hard bounce

    Populated from provider webhooks (SendGrid Event Webhook,
    Mailgun Webhook, Postmark Bounce webhook, etc.).
    """

    class BounceType(models.TextChoices):
        HARD = "hard", _("Hard Bounce — Permanent Failure")
        SOFT = "soft", _("Soft Bounce — Temporary Failure")
        BLOCK = "block", _("Block — IP/Domain Blocked by Recipient Server")
        SPAM = "spam", _("Spam Block — Content Filtered")
        TECHNICAL = "technical", _("Technical — DNS/MX Record Issue")

    notification_log = models.ForeignKey(
        NotificationLog,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bounces",
        verbose_name=_("Notification Log"),
    )
    email_address = models.EmailField(
        _("Bounced Email Address"),
        db_index=True,
    )
    bounce_type = models.CharField(
        _("Bounce Type"),
        max_length=15,
        choices=BounceType.choices,
        db_index=True,
    )
    diagnostic_code = models.CharField(
        _("Diagnostic Code"),
        max_length=255,
        blank=True,
        help_text=_(
            "SMTP diagnostic code from recipient server. e.g. '550 5.1.1 User unknown'"),
    )
    smtp_status_code = models.CharField(
        _("SMTP Status Code"),
        max_length=10,
        blank=True,
    )
    provider_event_id = models.CharField(
        _("Provider Event ID"),
        max_length=255,
        blank=True,
        help_text=_(
            "Unique ID from the provider webhook event for deduplication."),
    )
    raw_webhook_payload = models.JSONField(
        _("Raw Webhook Payload"),
        default=dict,
        blank=True,
        help_text=_(
            "Full raw payload from the provider webhook for debugging."),
    )
    auto_blacklisted = models.BooleanField(
        _("Auto-Blacklisted"),
        default=False,
        help_text=_(
            "True if this bounce automatically added the address to NotificationBlacklist."),
    )

    class Meta:
        verbose_name = _("Bounce Record")
        verbose_name_plural = _("Bounce Records")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email_address", "bounce_type"]),
            models.Index(fields=["bounce_type", "-created_at"]),
        ]

    def __str__(self):
        return f"[{self.bounce_type}] {self.email_address} at {self.created_at}"


class SpamComplaint(MixIdAndTimeModel):
    """
    Spam / abuse complaint records from email providers' feedback loops.
    APPEND-ONLY.

    Received when a recipient marks an email as spam in their email client.
    Major ISPs (Gmail, Yahoo, Outlook) report these via:
      - Yahoo FBL (Feedback Loop)
      - Microsoft JMRP
      - Gmail Postmaster FBL

    On receipt:
      → Email added to NotificationBlacklist with reason SPAM_COMPLAINT
      → Customer's marketing preferences set to is_subscribed=False
      → Alert sent to tenant (high spam rate can cause deliverability issues)
    """

    notification_log = models.ForeignKey(
        NotificationLog,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="spam_complaints",
        verbose_name=_("Notification Log"),
    )
    email_address = models.EmailField(
        _("Complaining Email Address"),
        db_index=True,
    )
    provider = models.CharField(
        _("ISP / Provider"),
        max_length=100,
        blank=True,
        help_text=_("e.g. 'Gmail', 'Yahoo', 'Hotmail', 'AOL'"),
    )
    feedback_type = models.CharField(
        _("Feedback Type"),
        max_length=50,
        blank=True,
        help_text=_(
            "ARF feedback-type header value. e.g. 'abuse', 'fraud', 'virus', 'other'"),
    )
    provider_event_id = models.CharField(
        _("Provider Event ID"),
        max_length=255,
        blank=True,
    )
    raw_complaint_payload = models.JSONField(
        _("Raw Complaint Payload"),
        default=dict,
        blank=True,
    )
    auto_blacklisted = models.BooleanField(
        _("Auto-Blacklisted"),
        default=False,
    )

    class Meta:
        verbose_name = _("Spam Complaint")
        verbose_name_plural = _("Spam Complaints")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email_address"]),
            models.Index(fields=["provider", "-created_at"]),
        ]

    def __str__(self):
        return f"Spam complaint from {self.email_address} ({self.provider}) at {self.created_at}"


# ─────────────────────────────────────────────────────────────
# SECTION 6 — WEBHOOKS (TENANT SCHEMA)
# ─────────────────────────────────────────────────────────────

class WebhookEndpoint(MixIdAndTimeModel):
    """
    A tenant-registered URL endpoint that receives event payloads
    when specific platform events occur.

    Use cases:
      - ERP integration (receive order.created events)
      - Accounting software sync
      - Custom inventory system
      - Third-party fulfillment service
      - Analytics platform
      - Customer data platform (CDP)

    Endpoint security:
      - Every delivery is signed with HMAC-SHA256 (WebhookSigningSecret)
      - Signature is in the X-Webhook-Signature-256 header
      - Recipients verify using the signing secret

    Retry policy:
      - Failed deliveries are retried with exponential backoff
      - Default: retry at 1m, 5m, 30m, 2h, 10h (5 total attempts)
      - Endpoints that fail consistently are SUSPENDED and tenant is notified

    Format:
      JSON payload with envelope:
        {
          "id": "uuid",
          "event": "order.placed",
          "created_at": "ISO 8601",
          "tenant_id": "...",
          "data": { ... event-specific payload ... }
        }
    """

    class EndpointStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        INACTIVE = "inactive", _("Inactive / Paused")
        SUSPENDED = "suspended", _("Suspended — Too Many Failures")
        TESTING = "testing", _("Testing / Pending Verification")

    class PayloadFormat(models.TextChoices):
        JSON = "json", _("JSON")
        FORM_URLENCODED = "form", _("application/x-www-form-urlencoded")
        XML = "xml", _("XML")

    # ── Identity ──
    name = models.CharField(
        _("Endpoint Name"),
        max_length=255,
        help_text=_(
            "Internal label. e.g. 'Shopify Product Sync', 'QuickBooks Orders'"),
    )
    url = models.URLField(
        _("Endpoint URL"),
        max_length=2000,
        help_text=_("The HTTPS URL that will receive webhook POST requests."),
        validators=[URLValidator(schemes=["https"])],
    )
    description = models.TextField(_("Description"), blank=True)

    # ── Status ──
    status = models.CharField(
        _("Status"),
        max_length=15,
        choices=EndpointStatus.choices,
        default=EndpointStatus.TESTING,
        db_index=True,
    )

    # ── Configuration ──
    payload_format = models.CharField(
        _("Payload Format"),
        max_length=10,
        choices=PayloadFormat.choices,
        default=PayloadFormat.JSON,
    )
    api_version = models.CharField(
        _("API Version"),
        max_length=20,
        default="2024-01",
        help_text=_(
            "Payload schema version. Increment when breaking changes are made."),
    )
    custom_headers = models.JSONField(
        _("Custom Headers"),
        default=dict,
        blank=True,
        help_text=_(
            "Additional HTTP headers sent with every delivery. "
            "{header_name: value}. Use for API keys or auth tokens expected by the receiver."
        ),
    )
    secret_token = models.TextField(
        _("Verification Secret Token"),
        blank=True,
        help_text=_(
            "Tenant-provided secret included in the X-Webhook-Token header. "
            "Allows the receiver to verify the request is from us. ENCRYPTED."
        ),
    )

    # ── Retry policy ──
    max_retry_attempts = models.PositiveSmallIntegerField(
        _("Max Retry Attempts"),
        default=5,
    )
    retry_delay_seconds = models.PositiveIntegerField(
        _("Initial Retry Delay (seconds)"),
        default=60,
    )
    use_exponential_backoff = models.BooleanField(
        _("Use Exponential Backoff"),
        default=True,
        help_text=_(
            "Multiply retry delay by 2 on each attempt: 60s, 120s, 240s..."),
    )
    timeout_seconds = models.PositiveSmallIntegerField(
        _("HTTP Timeout (seconds)"),
        default=30,
    )

    # ── Health tracking ──
    consecutive_failures = models.PositiveIntegerField(
        _("Consecutive Failures"),
        default=0,
    )
    failure_threshold = models.PositiveIntegerField(
        _("Failure Threshold"),
        default=20,
        help_text=_("Consecutive failures before endpoint is SUSPENDED."),
    )
    last_successful_delivery_at = models.DateTimeField(
        _("Last Successful Delivery At"),
        null=True,
        blank=True,
    )
    last_failure_at = models.DateTimeField(
        _("Last Failure At"), null=True, blank=True)
    total_deliveries = models.PositiveIntegerField(
        _("Total Deliveries"), default=0)
    total_failures = models.PositiveIntegerField(
        _("Total Failures"), default=0)

    # ── Verification ──
    is_verified = models.BooleanField(
        _("Endpoint Verified"),
        default=False,
        help_text=_(
            "True after the endpoint has successfully responded to a verification ping."),
    )
    verified_at = models.DateTimeField(_("Verified At"), null=True, blank=True)

    # ── Metadata ──
    created_by = models.ForeignKey(
        TenantUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_webhook_endpoints",
    )

    class Meta:
        verbose_name = _("Webhook Endpoint")
        verbose_name_plural = _("Webhook Endpoints")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.name} — {self.url[:60]} [{self.status}]"

    @property
    def success_rate(self) -> float:
        if self.total_deliveries == 0:
            return 100.0
        return round((self.total_deliveries - self.total_failures) / self.total_deliveries * 100, 2)

    def record_success(self):
        self.consecutive_failures = 0
        self.last_successful_delivery_at = timezone.now()
        self.total_deliveries = models.F("total_deliveries") + 1
        self.save(update_fields=[
            "consecutive_failures", "last_successful_delivery_at",
            "total_deliveries", "updated_at",
        ])

    def record_failure(self):
        self.consecutive_failures = models.F("consecutive_failures") + 1
        self.total_deliveries = models.F("total_deliveries") + 1
        self.total_failures = models.F("total_failures") + 1
        self.last_failure_at = timezone.now()
        self.save(update_fields=[
            "consecutive_failures", "total_deliveries",
            "total_failures", "last_failure_at", "updated_at",
        ])
        self.refresh_from_db(fields=["consecutive_failures"])
        if self.consecutive_failures >= self.failure_threshold:
            WebhookEndpoint.objects.filter(pk=self.pk).update(
                status=self.EndpointStatus.SUSPENDED
            )


class WebhookEventSubscription(MixIdAndTimeModel):
    """
    Maps a WebhookEndpoint to the specific event types it subscribes to.

    An endpoint receives a payload only for events it is subscribed to.
    Events use dot-notation format matching the application event system:
      order.placed, order.cancelled, order.refunded
      customer.created, customer.updated
      product.created, product.updated, product.deleted
      inventory.low_stock, inventory.out_of_stock
      review.created
      return.requested, return.approved, return.refunded
      payment.captured, payment.failed, payment.refunded

    The `filter_conditions` JSON allows fine-grained filtering:
      {"order_total_gte": 500, "currency": "NGN"}
    Endpoints only receive events where ALL filter conditions match.
    """

    endpoint = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name="subscriptions",
        verbose_name=_("Endpoint"),
    )
    event_slug = models.SlugField(
        _("Event"),
        max_length=150,
        db_index=True,
        help_text=_(
            "Event to subscribe to. Use '*' for all events, "
            "'order.*' for all order events."
        ),
    )
    is_active = models.BooleanField(_("Active"), default=True)
    filter_conditions = models.JSONField(
        _("Filter Conditions"),
        default=dict,
        blank=True,
        help_text=_(
            "Optional filters to narrow which events trigger delivery. "
            'e.g. {"order_total_gte": 500} — only orders over 500.'
        ),
    )
    include_fields = models.JSONField(
        _("Include Fields"),
        default=list,
        blank=True,
        help_text=_(
            "Whitelist of payload fields to include. "
            "Empty = include all fields."
        ),
    )
    exclude_fields = models.JSONField(
        _("Exclude Fields"),
        default=list,
        blank=True,
        help_text=_(
            "Fields to strip from the payload before delivery (e.g. PII fields)."),
    )

    class Meta:
        verbose_name = _("Webhook Event Subscription")
        verbose_name_plural = _("Webhook Event Subscriptions")
        unique_together = [("endpoint", "event_slug")]
        ordering = ["endpoint", "event_slug"]
        indexes = [
            models.Index(fields=["event_slug", "is_active"]),
        ]

    def __str__(self):
        return f"{self.endpoint.name} ← {self.event_slug}"


class WebhookDeliveryAttempt(MixIdAndTimeModel):
    """
    IMMUTABLE log of every individual webhook delivery attempt.
    Never UPDATE or DELETE — only INSERT.

    One record per HTTP request sent to a WebhookEndpoint.
    Multiple records exist for the same event if retries occur.
    """

    endpoint = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name="delivery_attempts",
        verbose_name=_("Endpoint"),
    )
    subscription = models.ForeignKey(
        WebhookEventSubscription,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="delivery_attempts",
        verbose_name=_("Subscription"),
    )

    # ── Event ──
    event_slug = models.SlugField(
        _("Event"),
        max_length=150,
        db_index=True,
    )
    event_id = models.UUIDField(
        _("Event ID"),
        db_index=True,
        help_text=_("Unique ID of the platform event being delivered."),
    )
    event_object_type = models.CharField(
        _("Event Object Type"), max_length=100, blank=True)
    event_object_id = models.UUIDField(
        _("Event Object ID"), null=True, blank=True)

    # ── Delivery ──
    attempt_number = models.PositiveSmallIntegerField(
        _("Attempt Number"),
        default=1,
        help_text=_("1 = first attempt, 2+ = retry attempts."),
    )
    payload = models.JSONField(
        _("Request Payload"),
        help_text=_("The JSON payload sent in the HTTP POST body."),
    )
    payload_size_bytes = models.PositiveIntegerField(
        _("Payload Size (bytes)"),
        null=True,
        blank=True,
    )
    request_headers = models.JSONField(
        _("Request Headers"),
        default=dict,
        help_text=_(
            "HTTP headers sent with the request (excluding sensitive auth headers)."),
    )

    # ── Response ──
    http_status_code = models.PositiveSmallIntegerField(
        _("HTTP Status Code"),
        null=True,
        blank=True,
        db_index=True,
    )
    response_body = models.TextField(
        _("Response Body"),
        blank=True,
        help_text=_("First 2000 chars of the response body."),
    )
    response_time_ms = models.PositiveIntegerField(
        _("Response Time (ms)"),
        null=True,
        blank=True,
    )

    # ── Status ──
    is_successful = models.BooleanField(
        _("Successful"),
        default=False,
        db_index=True,
        help_text=_("True if HTTP status was 2xx."),
    )
    error_type = models.CharField(
        _("Error Type"),
        max_length=50,
        blank=True,
        help_text=_(
            "e.g. 'connection_timeout', 'connection_refused', "
            "'http_error', 'ssl_error', 'dns_error'"
        ),
    )
    error_message = models.TextField(_("Error Message"), blank=True)

    # ── Retry state ──
    next_retry_at = models.DateTimeField(
        _("Next Retry At"),
        null=True,
        blank=True,
        db_index=True,
    )
    is_final_attempt = models.BooleanField(
        _("Final Attempt"),
        default=False,
        help_text=_("True if no more retries will be attempted."),
    )

    # ── Security ──
    signature = models.CharField(
        _("HMAC Signature"),
        max_length=128,
        blank=True,
        help_text=_(
            "The HMAC-SHA256 signature sent in X-Webhook-Signature-256 header."),
    )

    class Meta:
        verbose_name = _("Webhook Delivery Attempt")
        verbose_name_plural = _("Webhook Delivery Attempts")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["endpoint", "-created_at"]),
            models.Index(fields=["event_id", "attempt_number"]),
            models.Index(fields=["is_successful", "-created_at"]),
            models.Index(fields=["next_retry_at"]),
            models.Index(fields=["event_slug", "-created_at"]),
        ]

    def __str__(self):
        success = "✓" if self.is_successful else "✗"
        return (
            f"{success} {self.endpoint.name} ← {self.event_slug} "
            f"(attempt {self.attempt_number}) [{self.http_status_code}]"
        )


class WebhookSigningSecret(MixIdAndTimeModel):
    """
    Rotating HMAC signing secrets for webhook payload verification.

    Supports key rotation:
      - A new secret can be generated while the old one is still ACTIVE
      - Both are valid during the rotation window (grace period)
      - After the grace period, the old secret is RETIRED

    The signing algorithm:
      1. Concatenate timestamp + '.' + raw_payload_body
      2. Compute HMAC-SHA256 using the secret
      3. Encode as hex
      4. Send in X-Webhook-Signature-256 header:
         "t=<timestamp>,v1=<hex_signature>"
    """

    class SecretStatus(models.TextChoices):
        ACTIVE = "active", _("Active — Used for signing")
        ROTATING = "rotating", _(
            "Rotating — Old secret, still valid for grace period")
        RETIRED = "retired", _("Retired — No longer valid")

    endpoint = models.ForeignKey(
        WebhookEndpoint,
        on_delete=models.CASCADE,
        related_name="signing_secrets",
        verbose_name=_("Endpoint"),
    )
    secret = models.TextField(
        _("Secret (encrypted)"),
        help_text=_(
            "The HMAC secret used for signing. ENCRYPTED in production."),
    )
    status = models.CharField(
        _("Status"),
        max_length=10,
        choices=SecretStatus.choices,
        default=SecretStatus.ACTIVE,
        db_index=True,
    )
    rotated_at = models.DateTimeField(_("Rotated At"), null=True, blank=True)
    grace_period_ends_at = models.DateTimeField(
        _("Grace Period Ends At"),
        null=True,
        blank=True,
        help_text=_(
            "During rotation, the old secret is valid until this time "
            "to allow receivers to accept both old and new signatures."
        ),
    )
    created_by = models.ForeignKey(
        TenantUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_signing_secrets",
    )

    class Meta:
        verbose_name = _("Webhook Signing Secret")
        verbose_name_plural = _("Webhook Signing Secrets")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["endpoint", "status"]),
        ]

    def __str__(self):
        return f"Signing secret for {self.endpoint.name} [{self.status}]"

    @classmethod
    def generate(cls, endpoint, created_by=None) -> "WebhookSigningSecret":
        """Generate a new signing secret for an endpoint."""
        secret_value = f"whsec_{secrets.token_urlsafe(32)}"
        return cls.objects.create(
            endpoint=endpoint,
            secret=secret_value,  # Encrypt before storage in production
            status=cls.SecretStatus.ACTIVE,
            created_by=created_by,
        )

    def compute_signature(self, timestamp: str, payload_body: str) -> str:
        """
        Compute HMAC-SHA256 signature for a webhook payload.

        Args:
            timestamp: Unix timestamp string.
            payload_body: Raw JSON string of the payload body.

        Returns:
            str: Hex-encoded HMAC signature.
        """
        signed_payload = f"{timestamp}.{payload_body}"
        return hmac.new(
            self.secret.encode("utf-8"),
            signed_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
