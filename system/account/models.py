"""
system/account/models.py
========================
Platform-Level Authentication — PUBLIC SCHEMA ONLY

This module defines the PlatformUser: the top-level user who creates and
manages tenant stores (shops). These users live exclusively in the public
schema and are completely separate from tenant-level users.

Architecture:
─────────────
  PUBLIC SCHEMA
  ┌──────────────────────────────────────────────────────────┐
  │  PlatformUser  ←  AbstractBaseUser + PermissionsMixin    │
  │  - Email-based login (no username)                       │
  │  - Owns one or more Shop (tenant) instances              │
  │  - Can access their own tenant dashboards via            │
  │    platform_user_id bridge (no cross-schema FK)          │
  │  - 2FA, OAuth, API keys, audit trail                     │
  └──────────────────────────────────────────────────────────┘

  TENANT SCHEMA (per shop — completely isolated)
  ┌──────────────────────────────────────────────────────────┐
  │  TenantUser  ←  AbstractBaseUser + PermissionsMixin      │
  │  - Email unique WITHIN this tenant only                  │
  │  - platform_user_id (int, nullable, NO FK constraint)    │
  │    └── set when a PlatformUser logs into their own shop  │
  └──────────────────────────────────────────────────────────┘

Models in this file:
  1. PlatformUserManager
  2. PlatformUser
  3. PlatformEmailVerificationToken
  4. PlatformPasswordResetToken
  5. PlatformAPIKey
  6. PlatformLoginAuditLog
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ─────────────────────────────────────────────────────────────
# SECTION 1 — MANAGER
# ─────────────────────────────────────────────────────────────

class PlatformUserManager(BaseUserManager):
    """
    Custom manager for PlatformUser.
    Email is the unique identifier — no username field.
    """

    def _create_user(self, email: str, password: str, **extra_fields):
        if not email:
            raise ValueError(_("A platform user must have an email address."))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault(
            "account_status", PlatformUser.AccountStatus.PENDING)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_platform_admin", True)
        extra_fields.setdefault(
            "account_status", PlatformUser.AccountStatus.ACTIVE)
        extra_fields.setdefault("is_verified", True)

        if not extra_fields.get("is_staff"):
            raise ValueError(_("Superuser must have is_staff=True."))
        if not extra_fields.get("is_superuser"):
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self._create_user(email, password, **extra_fields)

    def active(self):
        """Return only active, non-deleted platform users."""
        return self.filter(
            account_status=PlatformUser.AccountStatus.ACTIVE,
            is_active=True,
        )


# ─────────────────────────────────────────────────────────────
# SECTION 2 — PLATFORM USER MODEL
# ─────────────────────────────────────────────────────────────

class PlatformUser(AbstractBaseUser, PermissionsMixin):
    """
    Top-level platform user — lives exclusively in the PUBLIC schema.

    These are the shop owners / tenant creators. They authenticate against
    the public schema and can:
      - Create and manage tenant shops
      - Access their own tenant dashboards (via platform_user_id bridge)
      - Manage platform-level billing and subscriptions

    They are COMPLETELY SEPARATE from TenantUser (tenant schema).
    The same email address can exist as both a PlatformUser and a TenantUser
    in any tenant — they are treated as different identities.

    AUTH_USER_MODEL = "account.PlatformUser"
    """

    class AccountStatus(models.TextChoices):
        ACTIVE = "ACTIVE",    _("Active")
        INACTIVE = "INACTIVE",  _("Inactive — login disabled")
        SUSPENDED = "SUSPENDED", _("Suspended — platform action")
        PENDING = "PENDING",   _("Pending — email not verified")
        DELETED = "DELETED",   _("Soft-deleted — GDPR anonymised")

    # ── Primary key ───────────────────────────────────────────
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text=_("Stable UUID — safe to expose in URLs."),
    )

    # ── Core identity ─────────────────────────────────────────
    email = models.EmailField(
        _("email address"),
        unique=True,
        db_index=True,
        help_text=_(
            "Primary login identifier. Must be unique across the platform."),
    )
    first_name = models.CharField(_("first name"), max_length=100, blank=True)
    last_name = models.CharField(_("last name"),  max_length=100, blank=True)
    phone = models.CharField(
        _("phone number"),
        max_length=30,
        blank=True,
        validators=[RegexValidator(
            r"^\+?1?\d{9,15}$",
            _("Enter a valid international phone number (e.g. +2348012345678).")
        )],
    )
    avatar_url = models.URLField(_("avatar URL"), blank=True)

    # ── Account status & verification ─────────────────────────
    account_status = models.CharField(
        _("account status"),
        max_length=12,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING,
        db_index=True,
    )
    is_verified = models.BooleanField(
        _("email verified"),
        default=False,
        help_text=_("Email address has been verified via token."),
    )
    verified_at = models.DateTimeField(
        _("verified at"),
        null=True,
        blank=True,
    )

    groups = models.ManyToManyField(
        'auth.Group',
        blank=True,
        related_name='platform_users',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        blank=True,
        related_name='platform_users',
        verbose_name='user permissions',
    )

    # ── Django admin access flags ──────────────────────────────
    # is_active: controls whether this user can log in at all
    # is_staff: controls access to Django admin interface
    # is_platform_admin: custom flag for full platform-level access
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_(
            "Designates whether the user can log into the Django admin site."),
    )
    is_platform_admin = models.BooleanField(
        _("platform admin"),
        default=False,
        help_text=_(
            "Full platform administrator — can act on any tenant for support purposes."
        ),
    )

    # ── Two-Factor Authentication ──────────────────────────────
    totp_secret = models.CharField(
        _("TOTP secret"),
        max_length=64,
        blank=True,
        help_text=_("Base32-encoded TOTP secret. Encrypted at rest."),
    )
    totp_enabled = models.BooleanField(_("TOTP enabled"), default=False)
    totp_confirmed_at = models.DateTimeField(
        _("TOTP confirmed at"), null=True, blank=True
    )
    backup_codes_enc = models.TextField(
        _("backup codes"),
        blank=True,
        help_text=_("Encrypted JSON list of hashed one-time backup codes."),
    )

    # ── OAuth / Social connections ─────────────────────────────
    google_id = models.CharField(max_length=200, blank=True, db_index=True)
    facebook_id = models.CharField(max_length=200, blank=True, db_index=True)
    github_id = models.CharField(max_length=200, blank=True, db_index=True)

    # ── Preferences ───────────────────────────────────────────
    locale = models.CharField(
        _("locale"),
        max_length=10,
        default="en",
        help_text=_("Preferred language/locale code, e.g. en, fr, ar."),
    )
    timezone = models.CharField(_("timezone"), max_length=50, default="UTC")
    email_marketing = models.BooleanField(
        _("email marketing consent"),
        default=True,
        help_text=_("Consent to receive platform marketing emails."),
    )

    # ── Security / lockout ────────────────────────────────────
    last_login_ip = models.GenericIPAddressField(
        _("last login IP"), null=True, blank=True
    )
    last_login_at = models.DateTimeField(
        _("last login at"), null=True, blank=True
    )
    failed_login_count = models.PositiveSmallIntegerField(
        _("failed login count"), default=0
    )
    locked_until = models.DateTimeField(
        _("locked until"),
        null=True,
        blank=True,
        help_text=_("Account locked after too many failed login attempts."),
    )
    force_password_reset = models.BooleanField(
        _("force password reset"),
        default=False,
        help_text=_("User must change password on next login."),
    )
    password_changed_at = models.DateTimeField(
        _("password changed at"), null=True, blank=True
    )

    # ── Timestamps ────────────────────────────────────────────
    created_at = models.DateTimeField(
        _("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    deleted_at = models.DateTimeField(_("deleted at"), null=True, blank=True)

    # ── Metadata ──────────────────────────────────────────────
    metadata = models.JSONField(
        _("metadata"),
        default=dict,
        blank=True,
        help_text=_(
            "Arbitrary extra data for integrations, feature flags, etc."),
    )

    objects = PlatformUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        app_label = "account"
        db_table = "platform_users"
        verbose_name = _("Platform User")
        verbose_name_plural = _("Platform Users")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"],
                         name="platform_user_email_idx"),
            models.Index(fields=["account_status"],
                         name="platform_user_status_idx"),
            models.Index(fields=["created_at"],
                         name="platform_user_created_idx"),
            models.Index(fields=["google_id"],
                         name="platform_user_google_idx"),
            models.Index(fields=["facebook_id"],
                         name="platform_user_fb_idx"),
        ]

    # ── String representation ─────────────────────────────────

    def __str__(self) -> str:
        return f"{self.get_full_name()} <{self.email}>"

    def get_full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.email

    def get_short_name(self) -> str:
        return self.first_name or self.email.split("@")[0]

    def get_initials(self) -> str:
        if self.first_name and self.last_name:
            return f"{self.first_name[0]}{self.last_name[0]}".upper()
        return self.email[:2].upper()

    # ── Status helpers ────────────────────────────────────────

    @property
    def is_locked(self) -> bool:
        """True if account is currently locked due to failed login attempts."""
        return bool(self.locked_until and timezone.now() < self.locked_until)

    @property
    def is_soft_deleted(self) -> bool:
        return self.account_status == self.AccountStatus.DELETED

    @property
    def can_login(self) -> bool:
        """True if the user is allowed to authenticate."""
        if self.account_status not in (
            self.AccountStatus.ACTIVE,
        ):
            return False
        if self.is_locked:
            return False
        return True

    # ── Security methods ──────────────────────────────────────

    def record_login(self, ip_address: str = None) -> None:
        """Record a successful login attempt."""
        self.last_login_at = timezone.now()
        self.last_login_ip = ip_address
        self.failed_login_count = 0
        self.locked_until = None
        self.save(update_fields=[
            "last_login_at", "last_login_ip",
            "failed_login_count", "locked_until",
        ])

    def record_failed_login(self, max_attempts: int = 5, lockout_minutes: int = 30) -> None:
        """
        Record a failed login attempt.
        Locks the account after max_attempts consecutive failures.
        """
        self.failed_login_count += 1
        if self.failed_login_count >= max_attempts:
            self.locked_until = timezone.now() + timedelta(minutes=lockout_minutes)
        self.save(update_fields=["failed_login_count", "locked_until"])

    def unlock(self) -> None:
        """Manually unlock the account and reset failed login counter."""
        self.failed_login_count = 0
        self.locked_until = None
        self.save(update_fields=["failed_login_count", "locked_until"])

    def soft_delete(self) -> None:
        """
        GDPR-compliant soft delete.
        Anonymises PII and marks account as deleted.
        The record is retained for audit/billing history.
        """
        self.email = f"deleted_{self.id}@deleted.invalid"
        self.first_name = "Deleted"
        self.last_name = "User"
        self.phone = ""
        self.avatar_url = ""
        self.google_id = ""
        self.facebook_id = ""
        self.github_id = ""
        self.totp_secret = ""
        self.backup_codes_enc = ""
        self.account_status = self.AccountStatus.DELETED
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save()


# ─────────────────────────────────────────────────────────────
# SECTION 3 — EMAIL VERIFICATION TOKEN
# ─────────────────────────────────────────────────────────────

class PlatformEmailVerificationToken(models.Model):
    """
    Secure time-limited token for platform user email verification.

    One active token per user per purpose — creating a new one
    automatically invalidates the previous.

    Purposes:
      VERIFY_EMAIL  — initial registration verification
      CHANGE_EMAIL  — verify new email after change request
      REACTIVATE    — reactivate a suspended account
    """

    class TokenPurpose(models.TextChoices):
        VERIFY_EMAIL = "VERIFY_EMAIL", _("Initial email verification")
        CHANGE_EMAIL = "CHANGE_EMAIL", _("Verify new email after change")
        REACTIVATE = "REACTIVATE",   _("Reactivate a suspended account")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        PlatformUser,
        on_delete=models.CASCADE,
        related_name="email_verification_tokens",
    )
    token = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text=_("URL-safe 64-byte random token."),
    )
    purpose = models.CharField(
        max_length=20,
        choices=TokenPurpose.choices,
        default=TokenPurpose.VERIFY_EMAIL,
    )
    new_email = models.EmailField(
        blank=True,
        help_text=_("For CHANGE_EMAIL — the new email being verified."),
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "account"
        db_table = "platform_email_verification_tokens"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"],   name="platform_evt_token_idx"),
            models.Index(fields=["user", "purpose", "is_used"],
                         name="platform_evt_user_purpose_idx"),
        ]

    def __str__(self) -> str:
        return f"PlatformEmailVerification({self.user.email}, {self.purpose})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired

    @classmethod
    def create_for_user(
        cls,
        user: PlatformUser,
        purpose: str = "VERIFY_EMAIL",
        new_email: str = "",
        ttl_hours: int = 24,
    ) -> "PlatformEmailVerificationToken":
        """
        Create a new token, invalidating any existing active tokens
        for the same user and purpose.
        """
        cls.objects.filter(
            user=user, purpose=purpose, is_used=False
        ).update(is_used=True)

        token = secrets.token_urlsafe(64)
        return cls.objects.create(
            user=user,
            token=token,
            purpose=purpose,
            new_email=new_email,
            expires_at=timezone.now() + timedelta(hours=ttl_hours),
        )

    def consume(self) -> bool:
        """
        Mark token as used. Returns True if successfully consumed,
        False if already used or expired.
        """
        if not self.is_valid:
            return False
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at"])
        return True


# ─────────────────────────────────────────────────────────────
# SECTION 4 — PASSWORD RESET TOKEN
# ─────────────────────────────────────────────────────────────

class PlatformPasswordResetToken(models.Model):
    """
    Secure time-limited token for platform user password resets.

    One active token per user — creating a new one invalidates the previous.
    TTL: 1 hour. IP address recorded for audit purposes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        PlatformUser,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
    )
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)
    request_ip = models.GenericIPAddressField(
        null=True, blank=True,
        help_text=_("IP address that requested the reset."),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "account"
        db_table = "platform_password_reset_tokens"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"],  name="platform_prt_token_idx"),
            models.Index(fields=["user", "is_used"],
                         name="platform_prt_user_idx"),
        ]

    def __str__(self) -> str:
        return f"PlatformPasswordReset({self.user.email})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired

    @classmethod
    def create_for_user(
        cls,
        user: PlatformUser,
        request_ip: str = None,
        ttl_hours: int = 1,
    ) -> "PlatformPasswordResetToken":
        """Create a new reset token, invalidating any existing active tokens."""
        cls.objects.filter(user=user, is_used=False).update(is_used=True)
        token = secrets.token_urlsafe(64)
        return cls.objects.create(
            user=user,
            token=token,
            request_ip=request_ip,
            expires_at=timezone.now() + timedelta(hours=ttl_hours),
        )

    def consume(self) -> bool:
        """Mark token as used. Returns True if successfully consumed."""
        if not self.is_valid:
            return False
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at"])
        return True


# ─────────────────────────────────────────────────────────────
# SECTION 5 — API KEY
# ─────────────────────────────────────────────────────────────

class PlatformAPIKey(models.Model):
    """
    Programmatic API keys for platform-level access.

    The raw key is shown ONCE at creation time.
    Only a SHA-256 hash is stored — the raw key cannot be recovered.

    Key types:
      PUBLIC  — safe to embed in client-side code (read-only)
      SECRET  — server-side only (full access per scopes)
      WEBHOOK — for verifying incoming webhook payloads
    """

    class KeyType(models.TextChoices):
        PUBLIC = "PUBLIC",  _("Public key — client-side safe")
        SECRET = "SECRET",  _("Secret key — server-side only")
        WEBHOOK = "WEBHOOK", _("Webhook signing secret")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        PlatformUser,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    name = models.CharField(
        max_length=100,
        help_text=_("Human-readable label, e.g. 'Production Server Key'."),
    )
    key_type = models.CharField(
        max_length=10, choices=KeyType.choices, default=KeyType.SECRET)
    key_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text=_("SHA-256 hash of the raw key. Never store the raw key."),
    )
    key_prefix = models.CharField(
        max_length=12,
        help_text=_("First 8 chars of the raw key for display/identification."),
    )
    scopes = models.JSONField(
        default=list,
        help_text=_(
            "List of permission scopes, e.g. ['shops:read', 'billing:write']."),
    )
    ip_allowlist = models.JSONField(
        default=list,
        blank=True,
        help_text=_(
            "Optional list of allowed IP addresses/CIDRs. Empty = allow all."),
    )
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.GenericIPAddressField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "account"
        db_table = "platform_api_keys"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["key_hash"],
                         name="platform_apikey_hash_idx"),
            models.Index(fields=["user", "is_active"],
                         name="platform_apikey_user_idx"),
        ]

    def __str__(self) -> str:
        return f"APIKey({self.name}, {self.key_prefix}...)"

    @classmethod
    def generate(cls, user: PlatformUser, name: str, key_type: str = "SECRET",
                 scopes: list = None, ip_allowlist: list = None,
                 expires_at=None) -> tuple["PlatformAPIKey", str]:
        """
        Generate a new API key.

        Returns (PlatformAPIKey instance, raw_key_string).
        The raw_key_string is shown ONCE — it cannot be recovered later.
        """
        raw_key = f"pk_{secrets.token_urlsafe(40)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:12]

        instance = cls.objects.create(
            user=user,
            name=name,
            key_type=key_type,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes or [],
            ip_allowlist=ip_allowlist or [],
            expires_at=expires_at,
        )
        return instance, raw_key

    @classmethod
    def authenticate(cls, raw_key: str) -> "PlatformAPIKey | None":
        """
        Look up an API key by its raw value.
        Returns the PlatformAPIKey instance if valid, None otherwise.
        """
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        try:
            api_key = cls.objects.select_related("user").get(
                key_hash=key_hash,
                is_active=True,
            )
        except cls.DoesNotExist:
            return None

        # Check expiry
        if api_key.expires_at and timezone.now() > api_key.expires_at:
            return None

        # Update last used
        api_key.last_used_at = timezone.now()
        api_key.save(update_fields=["last_used_at"])
        return api_key

    def revoke(self) -> None:
        """Revoke this API key."""
        self.is_active = False
        self.revoked_at = timezone.now()
        self.save(update_fields=["is_active", "revoked_at"])


# ─────────────────────────────────────────────────────────────
# SECTION 6 — LOGIN AUDIT LOG
# ─────────────────────────────────────────────────────────────

class PlatformLoginAuditLog(models.Model):
    """
    Immutable audit log of every platform-level login attempt.

    Records both successful and failed attempts.
    Never updated after creation — append-only.
    """

    class LoginResult(models.TextChoices):
        SUCCESS = "SUCCESS",        _("Successful login")
        FAILED_CREDS = "FAILED_CREDS",   _("Wrong email or password")
        FAILED_2FA = "FAILED_2FA",     _("2FA verification failed")
        LOCKED = "LOCKED",         _("Account locked")
        SUSPENDED = "SUSPENDED",      _("Account suspended")
        OAUTH_SUCCESS = "OAUTH_SUCCESS",  _("OAuth login successful")
        OAUTH_FAILED = "OAUTH_FAILED",   _("OAuth login failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # user may be null if the email doesn't exist (failed attempt with unknown email)
    user = models.ForeignKey(
        PlatformUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_audit_logs",
    )
    attempted_email = models.EmailField(
        help_text=_("Email address used in the login attempt."),
    )
    result = models.CharField(max_length=20, choices=LoginResult.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    country = models.CharField(max_length=2, blank=True)
    is_suspicious = models.BooleanField(
        default=False,
        help_text=_(
            "Flagged by risk engine (new country, impossible travel, etc.)."),
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "account"
        db_table = "platform_login_audit_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"],
                         name="platform_audit_user_idx"),
            models.Index(fields=["ip_address"],
                         name="platform_audit_ip_idx"),
            models.Index(fields=["is_suspicious"],
                         name="platform_audit_suspicious_idx"),
        ]

    def __str__(self) -> str:
        return f"PlatformAudit({self.attempted_email}, {self.result}, {self.created_at})"

    def save(self, *args, **kwargs):
        """Enforce immutability — audit logs cannot be updated."""
        if self.pk and PlatformLoginAuditLog.objects.filter(pk=self.pk).exists():
            raise ValueError("PlatformLoginAuditLog records are immutable.")
        super().save(*args, **kwargs)


class OnboardingSession(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", _("Draft")
        READY = "ready", _("Ready")
        COMPLETED = "completed", _("Completed")
        CANCELLED = "cancelled", _("Cancelled")

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        SKIPPED = "skipped", _("Skipped")
        PAID = "paid", _("Paid")
        FAILED = "failed", _("Failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_token = models.CharField(max_length=64, unique=True, db_index=True)
    email = models.EmailField(blank=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    business_name = models.CharField(max_length=120, blank=True)
    desired_subdomain = models.SlugField(max_length=63, blank=True)
    selected_bundle_slug = models.SlugField(max_length=100, blank=True)
    selected_feature_codes = models.JSONField(default=list, blank=True)
    selected_theme_slug = models.SlugField(max_length=100, blank=True)
    currency = models.CharField(max_length=3, default="NGN")
    estimated_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "account"
        db_table = "platform_onboarding_sessions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session_token"], name="platform_onboarding_token_idx"),
            models.Index(fields=["status", "payment_status"], name="platform_onboarding_status_idx"),
        ]

    def __str__(self) -> str:
        return f"OnboardingSession({self.email or self.session_token})"
