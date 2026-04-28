"""
notifications/models_part3.py  — Part 3 of 3
==============================================
SECTION 7 — IN-APP NOTIFICATIONS
SECTION 8 — ANALYTICS AGGREGATES
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from public.userauth.models import TenantUser
from .models_part1 import (
    MixIdAndTimeModel,
    ChannelType,
    DeliveryStatus,
    NotificationTemplate,
    NotificationChannel,
)


# ─────────────────────────────────────────────────────────────
# SECTION 7 — IN-APP NOTIFICATIONS (TENANT SCHEMA)
# ─────────────────────────────────────────────────────────────

class InAppNotification(MixIdAndTimeModel):
    """
    A notification displayed inside the merchant dashboard or customer account portal.

    Unlike email/SMS/push which leave the platform, in-app notifications
    are stored in the database and fetched by the frontend via a polling
    API or WebSocket connection.

    Target audience:
      - MERCHANT: shown in the admin/staff dashboard
        (order alerts, low stock, fraud flags, system messages)
      - CUSTOMER: shown in the customer's account portal
        (order status, points earned, return updates)

    Notification types:
      INFO     → Neutral informational message
      SUCCESS  → Positive action completed
      WARNING  → Requires attention
      ERROR    → Action failed, requires intervention
      PROMO    → Marketing/promotional message

    Persistence:
      - Notifications are SOFT-DELETED (expires_at or is_dismissed)
      - They appear in the notification bell/drawer until dismissed or expired
      - Critical notifications (is_pinned=True) cannot be dismissed until actioned
    """

    class AudienceType(models.TextChoices):
        MERCHANT = "merchant", _("Merchant / Staff Dashboard")
        CUSTOMER = "customer", _("Customer Account Portal")

    class NotificationType(models.TextChoices):
        INFO = "info", _("Info")
        SUCCESS = "success", _("Success")
        WARNING = "warning", _("Warning")
        ERROR = "error", _("Error")
        PROMO = "promo", _("Promotional")
        SYSTEM = "system", _("System")

    class DeliveryScope(models.TextChoices):
        INDIVIDUAL = "individual", _("Individual User")
        ROLE = "role", _("All Users with Role")
        ALL_STAFF = "all_staff", _("All Staff Members")
        ALL_CUSTOMERS = "all_customers", _("All Customers")
        BROADCAST = "broadcast", _("Broadcast (Everyone)")

    # ── Content ──
    title = models.CharField(
        _("Title"),
        max_length=255,
        help_text=_("Short notification title shown in the bell dropdown."),
    )
    body = models.TextField(
        _("Body"),
        blank=True,
        help_text=_(
            "Full notification message. Shown when notification is expanded."),
    )
    icon = models.CharField(
        _("Icon"),
        max_length=100,
        blank=True,
        help_text=_(
            "Icon identifier or emoji. e.g. '🛒', 'shopping-cart', 'alert-triangle'"),
    )
    image_url = models.URLField(
        _("Image URL"),
        blank=True,
        help_text=_("Optional image or thumbnail shown with the notification."),
    )

    # ── Type & priority ──
    notification_type = models.CharField(
        _("Notification Type"),
        max_length=10,
        choices=NotificationType.choices,
        default=NotificationType.INFO,
        db_index=True,
    )
    audience = models.CharField(
        _("Target Audience"),
        max_length=10,
        choices=AudienceType.choices,
        default=AudienceType.MERCHANT,
        db_index=True,
    )
    delivery_scope = models.CharField(
        _("Delivery Scope"),
        max_length=15,
        choices=DeliveryScope.choices,
        default=DeliveryScope.INDIVIDUAL,
    )
    target_role = models.CharField(
        _("Target Role"),
        max_length=100,
        blank=True,
        help_text=_(
            "For ROLE scope: the staff role that receives this notification."),
    )

    # ── Action ──
    action_url = models.CharField(
        _("Action URL"),
        max_length=500,
        blank=True,
        help_text=_("URL navigated to when the notification is clicked."),
    )
    action_label = models.CharField(
        _("Action Label"),
        max_length=100,
        blank=True,
        help_text=_(
            "Button/link text for the primary action. e.g. 'View Order', 'Dismiss'"),
    )
    secondary_action_url = models.CharField(
        _("Secondary Action URL"), max_length=500, blank=True)
    secondary_action_label = models.CharField(
        _("Secondary Action Label"), max_length=100, blank=True)

    # ── Source context ──
    source_event = models.SlugField(
        _("Source Event"),
        max_length=150,
        blank=True,
        db_index=True,
        help_text=_("The application event that triggered this notification."),
    )
    source_object_type = models.CharField(
        _("Source Object Type"),
        max_length=100,
        blank=True,
        help_text=_(
            "The model type of the triggering object. e.g. 'Order', 'Product'"),
    )
    source_object_id = models.UUIDField(
        _("Source Object ID"),
        null=True,
        blank=True,
        db_index=True,
    )
    metadata = models.JSONField(
        _("Metadata"),
        default=dict,
        blank=True,
        help_text=_("Additional structured data for the notification."),
    )

    # ── Timing ──
    is_active = models.BooleanField(_("Active"), default=True, db_index=True)
    expires_at = models.DateTimeField(
        _("Expires At"),
        null=True,
        blank=True,
        db_index=True,
        help_text=_("Auto-hide after this time. Null = never expires."),
    )
    is_pinned = models.BooleanField(
        _("Pinned"),
        default=False,
        help_text=_(
            "Pinned notifications are shown at the top and "
            "cannot be dismissed until explicitly actioned."
        ),
    )
    send_push = models.BooleanField(
        _("Also Send Push"),
        default=False,
        help_text=_(
            "If True, also fire a push notification to the user's registered devices "
            "in addition to the in-app notification."
        ),
    )
    send_email = models.BooleanField(
        _("Also Send Email"),
        default=False,
        help_text=_(
            "If True, also send an email version of this notification."),
    )

    # ── Style ──
    color = models.CharField(
        _("Accent Color"),
        max_length=7,
        blank=True,
        help_text=_(
            "CSS hex color for the notification accent. e.g. '#FF5733'"),
    )
    badge_count = models.PositiveSmallIntegerField(
        _("Badge Count Increment"),
        default=1,
        help_text=_("How much to increment the notification bell badge count."),
    )

    # ── Created by ──
    created_by = models.ForeignKey(
        TenantUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_inapp_notifications",
        verbose_name=_("Created By"),
        help_text=_("Null = system-generated."),
    )

    class Meta:
        verbose_name = _("In-App Notification")
        verbose_name_plural = _("In-App Notifications")
        ordering = ["-is_pinned", "-created_at"]
        indexes = [
            models.Index(fields=["audience", "is_active"]),
            models.Index(fields=["is_active", "expires_at"]),
            models.Index(fields=["source_event", "-created_at"]),
            models.Index(fields=["source_object_type", "source_object_id"]),
            models.Index(fields=["notification_type", "audience"]),
        ]

    def __str__(self):
        return f"[{self.notification_type}] {self.title[:60]} ({self.audience})"

    @property
    def is_currently_active(self) -> bool:
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < timezone.now():
            return False
        return True


class InAppNotificationRead(MixIdAndTimeModel):
    """
    Tracks the read and dismissed state of an InAppNotification for a specific user.

    One record per (notification × user) pair.
    Created on first view; updated when dismissed or actioned.

    States:
      UNREAD     → Notification exists, no read record (implied)
      READ       → User has seen the notification (notification_read_at set)
      DISMISSED  → User has explicitly dismissed it (dismissed_at set)
      ACTIONED   → User clicked the primary action (actioned_at set)
    """

    notification = models.ForeignKey(
        InAppNotification,
        on_delete=models.CASCADE,
        related_name="read_states",
        verbose_name=_("Notification"),
    )
    user = models.ForeignKey(
        TenantUser,
        on_delete=models.CASCADE,
        related_name="notification_read_states",
        verbose_name=_("User"),
    )

    # ── Read state ──
    read_at = models.DateTimeField(
        _("Read At"),
        null=True,
        blank=True,
        help_text=_("When the user first viewed this notification."),
    )
    dismissed_at = models.DateTimeField(
        _("Dismissed At"),
        null=True,
        blank=True,
        help_text=_("When the user explicitly dismissed this notification."),
    )
    actioned_at = models.DateTimeField(
        _("Actioned At"),
        null=True,
        blank=True,
        help_text=_("When the user clicked the primary action button."),
    )
    actioned_url = models.CharField(
        _("Actioned URL"),
        max_length=500,
        blank=True,
    )

    # ── Device context ──
    read_ip = models.GenericIPAddressField(
        _("Read From IP"), null=True, blank=True)

    class Meta:
        verbose_name = _("In-App Notification Read State")
        verbose_name_plural = _("In-App Notification Read States")
        unique_together = [("notification", "user")]
        indexes = [
            models.Index(fields=["user", "notification"]),
            models.Index(fields=["user", "dismissed_at"]),
        ]

    def __str__(self):
        state = (
            "actioned" if self.actioned_at else
            "dismissed" if self.dismissed_at else
            "read" if self.read_at else
            "unread"
        )
        return f"{self.user} — {self.notification.title[:40]} [{state}]"

    def mark_read(self, ip_address: str = ""):
        if not self.read_at:
            self.read_at = timezone.now()
            self.read_ip = ip_address or None
            self.save(update_fields=["read_at", "read_ip", "updated_at"])

    def mark_dismissed(self):
        self.dismissed_at = timezone.now()
        if not self.read_at:
            self.read_at = self.dismissed_at
        self.save(update_fields=["dismissed_at", "read_at", "updated_at"])

    def mark_actioned(self, url: str = ""):
        self.actioned_at = timezone.now()
        self.actioned_url = url
        if not self.read_at:
            self.read_at = self.actioned_at
        self.save(update_fields=["actioned_at",
                  "actioned_url", "read_at", "updated_at"])


# ─────────────────────────────────────────────────────────────
# SECTION 8 — ANALYTICS AGGREGATES (TENANT SCHEMA)
# ─────────────────────────────────────────────────────────────

class NotificationDailySummary(MixIdAndTimeModel):
    """
    Pre-aggregated daily performance statistics per channel + template combination.

    Built by a nightly Celery task that aggregates NotificationLog records.
    Enables fast dashboard queries without scanning the full log table.

    One record per (date × channel_type × template × event_slug).

    Metrics:
      sent        → Total send attempts (excluding SUPPRESSED)
      delivered   → Confirmed deliveries
      opened      → Unique opens (email open tracking pixel)
      clicked     → Unique clicks
      bounced     → Hard bounces
      soft_bounced→ Soft bounces
      failed      → Failed sends (after all retries)
      suppressed  → Blocked by preferences/blacklist
      unsubscribed→ Unsubscribes triggered by this day's sends
      spam        → Spam complaints received

    Rates (computed, stored for fast retrieval):
      delivery_rate   = delivered / sent
      open_rate       = opened / delivered
      click_rate      = clicked / opened
      bounce_rate     = bounced / sent
      spam_rate       = spam / sent
    """

    # ── Dimensions ──
    date = models.DateField(
        _("Date"),
        db_index=True,
        help_text=_("The day these metrics cover (UTC)."),
    )
    channel_type = models.CharField(
        _("Channel Type"),
        max_length=15,
        choices=ChannelType.choices,
        db_index=True,
    )
    template = models.ForeignKey(
        NotificationTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daily_summaries",
        verbose_name=_("Template"),
    )
    event_slug = models.SlugField(
        _("Event Slug"),
        max_length=150,
        blank=True,
        db_index=True,
    )
    channel = models.ForeignKey(
        NotificationChannel,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="daily_summaries",
        verbose_name=_("Channel"),
    )

    # ── Volume counters ──
    sent_count = models.PositiveIntegerField(
        _("Sent"),
        default=0,
        help_text=_("Messages accepted by the delivery provider."),
    )
    delivered_count = models.PositiveIntegerField(
        _("Delivered"),
        default=0,
    )
    opened_count = models.PositiveIntegerField(
        _("Opened (Unique)"),
        default=0,
    )
    clicked_count = models.PositiveIntegerField(
        _("Clicked (Unique)"),
        default=0,
    )
    bounced_count = models.PositiveIntegerField(
        _("Hard Bounced"),
        default=0,
    )
    soft_bounced_count = models.PositiveIntegerField(
        _("Soft Bounced"),
        default=0,
    )
    failed_count = models.PositiveIntegerField(
        _("Failed"),
        default=0,
    )
    suppressed_count = models.PositiveIntegerField(
        _("Suppressed"),
        default=0,
    )
    unsubscribed_count = models.PositiveIntegerField(
        _("Unsubscribed"),
        default=0,
    )
    spam_count = models.PositiveIntegerField(
        _("Spam Complaints"),
        default=0,
    )
    total_jobs = models.PositiveIntegerField(
        _("Total Jobs Created"),
        default=0,
    )
    cancelled_count = models.PositiveIntegerField(
        _("Cancelled"),
        default=0,
    )

    # ── Rate metrics (stored as Decimal 0.0000 – 1.0000) ──
    delivery_rate = models.DecimalField(
        _("Delivery Rate"),
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
        validators=[MinValueValidator(
            Decimal("0")), MaxValueValidator(Decimal("1"))],
    )
    open_rate = models.DecimalField(
        _("Open Rate"),
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    click_rate = models.DecimalField(
        _("Click-Through Rate"),
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    click_to_open_rate = models.DecimalField(
        _("Click-to-Open Rate"),
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
        help_text=_("clicked / opened — measures link relevance given opens."),
    )
    bounce_rate = models.DecimalField(
        _("Hard Bounce Rate"),
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    unsubscribe_rate = models.DecimalField(
        _("Unsubscribe Rate"),
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
    )
    spam_rate = models.DecimalField(
        _("Spam Rate"),
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
    )

    # ── Performance ──
    avg_delivery_time_ms = models.PositiveIntegerField(
        _("Avg Delivery Time (ms)"),
        null=True,
        blank=True,
        help_text=_("Average time from job creation to provider acceptance."),
    )
    avg_open_time_seconds = models.PositiveIntegerField(
        _("Avg Time to Open (seconds)"),
        null=True,
        blank=True,
        help_text=_("Average time from delivery to first open."),
    )

    # ── Webhook-specific ──
    webhook_success_count = models.PositiveIntegerField(
        _("Webhook Successes"),
        default=0,
    )
    webhook_failure_count = models.PositiveIntegerField(
        _("Webhook Failures"),
        default=0,
    )
    webhook_avg_response_ms = models.PositiveIntegerField(
        _("Webhook Avg Response Time (ms)"),
        null=True,
        blank=True,
    )

    # ── Build metadata ──
    built_at = models.DateTimeField(
        _("Built At"),
        null=True,
        blank=True,
        help_text=_(
            "When this summary was last (re)built by the aggregation task."),
    )
    is_partial = models.BooleanField(
        _("Partial"),
        default=False,
        help_text=_(
            "True if this is an intra-day partial summary "
            "(not yet the final daily aggregate)."
        ),
    )

    class Meta:
        verbose_name = _("Notification Daily Summary")
        verbose_name_plural = _("Notification Daily Summaries")
        unique_together = [("date", "channel_type", "template", "event_slug")]
        ordering = ["-date", "channel_type"]
        indexes = [
            models.Index(fields=["date", "channel_type"]),
            models.Index(fields=["date", "template"]),
            models.Index(fields=["event_slug", "date"]),
            models.Index(fields=["-date", "open_rate"]),
        ]

    def __str__(self):
        template_name = self.template.name if self.template else self.event_slug
        return (
            f"{self.date} — {template_name} / {self.channel_type}: "
            f"{self.sent_count} sent, {float(self.open_rate*100):.1f}% open rate"
        )

    def compute_rates(self) -> None:
        """Recompute all rate metrics from raw counts and save."""
        def safe_rate(numerator: int, denominator: int) -> Decimal:
            if denominator <= 0:
                return Decimal("0.0000")
            return Decimal(str(round(numerator / denominator, 4)))

        self.delivery_rate = safe_rate(self.delivered_count, self.sent_count)
        self.open_rate = safe_rate(self.opened_count, self.delivered_count)
        self.click_rate = safe_rate(self.clicked_count, self.sent_count)
        self.click_to_open_rate = safe_rate(
            self.clicked_count, self.opened_count)
        self.bounce_rate = safe_rate(self.bounced_count, self.sent_count)
        self.unsubscribe_rate = safe_rate(
            self.unsubscribed_count, self.sent_count)
        self.spam_rate = safe_rate(self.spam_count, self.sent_count)
        self.built_at = timezone.now()
        self.save(update_fields=[
            "delivery_rate", "open_rate", "click_rate", "click_to_open_rate",
            "bounce_rate", "unsubscribe_rate", "spam_rate", "built_at", "updated_at",
        ])

    @property
    def open_rate_pct(self) -> float:
        return float(self.open_rate * 100)

    @property
    def click_rate_pct(self) -> float:
        return float(self.click_rate * 100)

    @property
    def health_grade(self) -> str:
        """Simple health grade based on bounce + spam rates."""
        if self.bounce_rate > Decimal("0.05") or self.spam_rate > Decimal("0.001"):
            return "F"
        if self.bounce_rate > Decimal("0.02") or self.spam_rate > Decimal("0.0005"):
            return "C"
        if self.bounce_rate > Decimal("0.01"):
            return "B"
        return "A"
