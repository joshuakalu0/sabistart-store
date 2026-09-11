"""
system/core/platform_settings.py
=================================
Singleton DB models for platform-wide infrastructure settings.

All three models live in the PUBLIC schema (they are SHARED_APPS models).
Each uses a well-known pk=1 singleton pattern with a classmethod `load()`
that creates the row if it doesn't exist yet.

Models
------
PlatformSmtpSetting    — outgoing email (SMTP) configuration
PlatformStorageSetting — file / media storage backend configuration
PlatformMessagingSetting — SMS / WhatsApp provider configuration
"""
from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


# ─────────────────────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────────────────────

class _SingletonModel(models.Model):
    """Abstract base: only one row (pk=1) is ever created."""

    class Meta:
        abstract = True

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # prevent accidental deletion


# ─────────────────────────────────────────────────────────────────────────────
# SMTP
# ─────────────────────────────────────────────────────────────────────────────

class PlatformSmtpSetting(_SingletonModel):
    """
    Platform-wide outgoing SMTP configuration.
    When populated, the platform uses these credentials for system emails
    instead of the default Django EMAIL_* settings.
    """

    SECURITY_TLS = "tls"
    SECURITY_SSL = "ssl"
    SECURITY_NONE = "none"
    SECURITY_CHOICES = [
        (SECURITY_TLS, "STARTTLS (port 587)"),
        (SECURITY_SSL, "SSL/TLS (port 465)"),
        (SECURITY_NONE, "None (port 25)"),
    ]

    host = models.CharField(max_length=253, blank=True, help_text="SMTP server hostname, e.g. smtp.sendgrid.net")
    port = models.PositiveIntegerField(default=587)
    security = models.CharField(max_length=10, choices=SECURITY_CHOICES, default=SECURITY_TLS)
    username = models.CharField(max_length=254, blank=True)
    password = models.CharField(max_length=512, blank=True, help_text="Stored in plain text — use an app password or API key.")
    default_from_email = models.EmailField(blank=True, help_text="e.g. no-reply@yourplatform.com")
    default_from_name = models.CharField(max_length=100, blank=True, help_text="e.g. SABIStart Platform")
    is_active = models.BooleanField(default=False, help_text="Override Django EMAIL_* settings with these values.")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "Platform SMTP Setting"
        verbose_name_plural = "Platform SMTP Settings"

    def __str__(self):
        return f"SMTP → {self.host}:{self.port}" if self.host else "SMTP (not configured)"

    @property
    def is_configured(self):
        return bool(self.host and self.username)


# ─────────────────────────────────────────────────────────────────────────────
# Storage
# ─────────────────────────────────────────────────────────────────────────────

class PlatformStorageSetting(_SingletonModel):
    """
    Platform-wide media / file-storage backend configuration.
    Supports local disk, AWS S3-compatible, and Vercel Blob.
    """

    BACKEND_LOCAL = "local"
    BACKEND_S3 = "s3"
    BACKEND_VERCEL = "vercel"
    BACKEND_CHOICES = [
        (BACKEND_LOCAL, "Local Disk (default)"),
        (BACKEND_S3, "AWS S3 / S3-Compatible"),
        (BACKEND_VERCEL, "Vercel Blob"),
    ]

    backend = models.CharField(max_length=20, choices=BACKEND_CHOICES, default=BACKEND_LOCAL)

    # S3-compatible
    s3_access_key_id = models.CharField(max_length=128, blank=True)
    s3_secret_access_key = models.CharField(max_length=512, blank=True)
    s3_bucket_name = models.CharField(max_length=63, blank=True)
    s3_region = models.CharField(max_length=30, blank=True, default="us-east-1")
    s3_endpoint_url = models.CharField(
        max_length=500, blank=True,
        help_text="Leave blank for AWS. For DigitalOcean Spaces use https://nyc3.digitaloceanspaces.com"
    )
    s3_custom_domain = models.CharField(
        max_length=253, blank=True,
        help_text="Optional CDN/public domain, e.g. cdn.yourplatform.com"
    )

    # Vercel Blob
    vercel_blob_read_write_token = models.CharField(max_length=512, blank=True)

    is_active = models.BooleanField(default=False, help_text="Use these settings instead of settings.py STORAGES.")
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "Platform Storage Setting"
        verbose_name_plural = "Platform Storage Settings"

    def __str__(self):
        return f"Storage → {self.get_backend_display()}"

    @property
    def is_configured(self):
        if self.backend == self.BACKEND_S3:
            return bool(self.s3_access_key_id and self.s3_bucket_name)
        if self.backend == self.BACKEND_VERCEL:
            return bool(self.vercel_blob_read_write_token)
        return True  # local is always "configured"


# ─────────────────────────────────────────────────────────────────────────────
# Messaging (SMS / WhatsApp)
# ─────────────────────────────────────────────────────────────────────────────

class PlatformMessagingSetting(_SingletonModel):
    """
    Platform-wide SMS / WhatsApp provider configuration.
    """

    PROVIDER_NONE = "none"
    PROVIDER_TWILIO = "twilio"
    PROVIDER_VONAGE = "vonage"
    PROVIDER_TERMII = "termii"
    PROVIDER_CHOICES = [
        (PROVIDER_NONE, "Not configured"),
        (PROVIDER_TWILIO, "Twilio"),
        (PROVIDER_VONAGE, "Vonage (Nexmo)"),
        (PROVIDER_TERMII, "Termii"),
    ]

    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default=PROVIDER_NONE)

    # Twilio
    twilio_account_sid = models.CharField(max_length=64, blank=True)
    twilio_auth_token = models.CharField(max_length=64, blank=True)
    twilio_from_number = models.CharField(max_length=20, blank=True, help_text="E.164 format: +15005550006")
    twilio_whatsapp_from = models.CharField(
        max_length=30, blank=True,
        help_text="WhatsApp sandbox/approved sender, e.g. whatsapp:+14155238886"
    )

    # Vonage
    vonage_api_key = models.CharField(max_length=32, blank=True)
    vonage_api_secret = models.CharField(max_length=64, blank=True)
    vonage_from_name = models.CharField(max_length=11, blank=True, help_text="Sender ID (max 11 chars)")

    # Termii
    termii_api_key = models.CharField(max_length=128, blank=True)
    termii_sender_id = models.CharField(max_length=11, blank=True, help_text="Registered sender ID")

    # Webhook
    webhook_secret = models.CharField(
        max_length=64, blank=True,
        help_text="HMAC secret used to verify inbound provider webhooks."
    )

    is_active = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        verbose_name = "Platform Messaging Setting"
        verbose_name_plural = "Platform Messaging Settings"

    def __str__(self):
        return f"Messaging → {self.get_provider_display()}"

    @property
    def is_configured(self):
        if self.provider == self.PROVIDER_TWILIO:
            return bool(self.twilio_account_sid and self.twilio_auth_token)
        if self.provider == self.PROVIDER_VONAGE:
            return bool(self.vonage_api_key and self.vonage_api_secret)
        if self.provider == self.PROVIDER_TERMII:
            return bool(self.termii_api_key)
        return False

    def rotate_webhook_secret(self) -> str:
        """Generate and save a new webhook signing secret. Returns the new secret."""
        new_secret = secrets.token_hex(32)
        self.webhook_secret = new_secret
        self.save(update_fields=["webhook_secret", "updated_at"])
        return new_secret
