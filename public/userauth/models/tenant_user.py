"""
public/userauth/models/tenant_user.py
======================================
Tenant-Level Authentication — TENANT SCHEMA (per-shop isolation)

This module defines TenantUser: the user model that lives inside each
tenant's isolated schema. Every tenant has its own completely independent
user table — the same email address can exist in multiple tenants without
any collision.

Architecture:
─────────────
  TENANT SCHEMA (shop1)          TENANT SCHEMA (shop2)
  ┌──────────────────────┐       ┌──────────────────────┐
  │ TenantUser           │       │ TenantUser           │
  │ email: a@b.com ✓     │       │ email: a@b.com ✓     │  ← same email, different people
  │ platform_user_id: 42 │       │ platform_user_id: null│  ← shop owner bridge (no FK)
  └──────────────────────┘       └──────────────────────┘

Key design decisions:
  1. AbstractBaseUser — full control, no username field
  2. Email unique WITHIN tenant only (enforced by DB unique constraint in tenant schema)
  3. platform_user_id (int, nullable, NO FK constraint) — links to PlatformUser
     when a shop owner logs into their own store. No cross-schema FK.
  4. user_type distinguishes CUSTOMER vs STAFF within the same model
  5. No references to public schema models — complete isolation

Models in this file:
  1. TenantUserManager
  2. TenantUser
  3. TenantEmailVerificationToken
  4. TenantPasswordResetToken
  5. TenantLoginAuditLog
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

class TenantUserManager(BaseUserManager):
    """
    Custom manager for TenantUser.
    Email is the unique identifier within the tenant schema.
    """

    def _create_user(self, email: str, password: str, **extra_fields):
        if not email:
            raise ValueError(_("A tenant user must have an email address."))
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault(
            "account_status", TenantUser.AccountStatus.PENDING)
        extra_fields.setdefault("user_type", TenantUser.UserType.CUSTOMER)
        return self._create_user(email, password, **extra_fields)

    def create_staff(self, email: str, password: str = None, **extra_fields):
        """Create a staff member (store employee)."""
        extra_fields.setdefault("user_type", TenantUser.UserType.STAFF)
        extra_fields.setdefault(
            "account_status", TenantUser.AccountStatus.ACTIVE)
        return self.create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str, **extra_fields):
        """Create a tenant superuser (store owner via tenant dashboard)."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("user_type", TenantUser.UserType.STAFF)
        extra_fields.setdefault(
            "account_status", TenantUser.AccountStatus.ACTIVE)
        extra_fields.setdefault("is_verified", True)

        if not extra_fields.get("is_staff"):
            raise ValueError(_("Superuser must have is_staff=True."))
        if not extra_fields.get("is_superuser"):
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self._create_user(email, password, **extra_fields)

    def customers(self):
        """Return only customer-type users."""
        return self.filter(user_type=TenantUser.UserType.CUSTOMER)

    def staff_members(self):
        """Return only staff-type users."""
        return self.filter(user_type=TenantUser.UserType.STAFF)

    def active(self):
        """Return only active, non-deleted users."""
        return self.filter(
            account_status=TenantUser.AccountStatus.ACTIVE,
            is_active=True,
        )


# ─────────────────────────────────────────────────────────────
# SECTION 2 — TENANT USER MODEL
# ─────────────────────────────────────────────────────────────

class TenantUser(AbstractBaseUser, PermissionsMixin):
    """
    Tenant-scoped user — lives exclusively in the TENANT schema.

    This model is completely isolated per tenant. The same email address
    can exist in multiple tenants without any collision — they are treated
    as entirely different identities.

    Two types of users share this model:
      CUSTOMER — shoppers who buy from the store
      STAFF    — employees who manage the store

    The platform_user_id field (nullable integer, NO FK constraint) is used
    to bridge a PlatformUser (shop owner) into the tenant dashboard. When a
    shop owner logs into their own store, a TenantUser record is created or
    found with their platform_user_id set. This avoids any cross-schema FK.

    IMPORTANT: This model is NOT AUTH_USER_MODEL.
    AUTH_USER_MODEL = "account.PlatformUser" (public schema)
    TenantUser is authenticated via TenantAuthBackend.
    """

    class AccountStatus(models.TextChoices):
        ACTIVE = "ACTIVE",    _("Active")
        INACTIVE = "INACTIVE",  _("Inactive — login disabled")
        SUSPENDED = "SUSPENDED", _("Suspended — store action")
        PENDING = "PENDING",   _("Pending — email not verified")
        DELETED = "DELETED",   _("Soft-deleted — GDPR anonymised")

    class UserType(models.TextChoices):
        CUSTOMER = "CUSTOMER", _("Customer — shopper")
        STAFF = "STAFF",    _("Staff — store employee")

    class Gender(models.TextChoices):
        MALE = "M", _("Male")
        FEMALE = "F", _("Female")
        OTHER = "O", _("Other")
        PREFER_NOT_SAY = "N", _("Prefer not to say")

    # ── Primary key ───────────────────────────────────────────
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # ── Core identity ─────────────────────────────────────────
    email = models.EmailField(
        _("email address"),
        unique=True,
        db_index=True,
        help_text=_(
            "Login identifier. Unique within this tenant only. "
            "The same email can exist in other tenant stores independently."
        ),
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
    date_of_birth = models.DateField(_("date of birth"), null=True, blank=True)
    gender = models.CharField(
        _("gender"), max_length=1, choices=Gender.choices, blank=True
    )

    # ── User type ─────────────────────────────────────────────
    user_type = models.CharField(
        _("user type"),
        max_length=10,
        choices=UserType.choices,
        default=UserType.CUSTOMER,
        db_index=True,
    )

    # ── Platform bridge (NO FK CONSTRAINT — cross-schema safe) ─
    # When a PlatformUser (shop owner) logs into their own tenant dashboard,
    # their PlatformUser.id (UUID stored as text) is recorded here.
    # This is NOT a foreign key — it's a plain field with no DB constraint.
    # This avoids any cross-schema referential integrity issues.
    platform_user_id = models.CharField(
        _("platform user ID"),
        max_length=36,  # UUID string length
        blank=True,
        db_index=True,
        help_text=_(
            "UUID of the PlatformUser who owns this store. "
            "Set when a shop owner logs into their own tenant dashboard. "
            "NOT a foreign key — no cross-schema constraint."
        ),
    )

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
    verified_at = models.DateTimeField(_("verified at"), null=True, blank=True)

    # ── Django flags ──────────────────────────────────────────
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
            "Designates whether the user can log into the tenant admin."),
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

    # ── Preferences ───────────────────────────────────────────
    locale = models.CharField(
        _("locale"),
        max_length=10,
        default="en",
        help_text=_("Preferred language/locale code, e.g. en, fr, ar."),
    )
    timezone = models.CharField(_("timezone"), max_length=50, default="UTC")
    preferred_currency = models.CharField(
        _("preferred currency"), max_length=3, default="USD"
    )

    # ── Marketing consent ─────────────────────────────────────
    email_marketing_consent = models.BooleanField(
        _("email marketing consent"),
        default=False,
        help_text=_("Consent to receive marketing emails from this store."),
    )
    marketing_consent_ip = models.GenericIPAddressField(
        _("consent IP"), null=True, blank=True
    )
    marketing_consent_at = models.DateTimeField(
        _("consent given at"), null=True, blank=True
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

    groups = models.ManyToManyField(
        'auth.Group',
        blank=True,
        related_name='tenant_users',
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        blank=True,
        related_name='tenant_users',
        verbose_name='user permissions',
    )

    objects = TenantUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        app_label = "userauth"
        db_table = "tenant_users"
        verbose_name = _("Tenant User")
        verbose_name_plural = _("Tenant Users")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"],
                         name="tenant_user_email_idx"),
            models.Index(fields=["account_status"],
                         name="tenant_user_status_idx"),
            models.Index(fields=["user_type"],
                         name="tenant_user_type_idx"),
            models.Index(fields=["platform_user_id"],
                         name="tenant_user_platform_idx"),
            models.Index(fields=["created_at"],
                         name="tenant_user_created_idx"),
        ]

    # ── String representation ─────────────────────────────────

    def __str__(self) -> str:
        return f"{self.get_full_name()} <{self.email}> [{self.user_type}]"

    def get_full_name(self) -> str:
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.email

    def get_short_name(self) -> str:
        return self.first_name or self.email.split("@")[0]

    def get_initials(self) -> str:
        if self.first_name and self.last_name:
            return f"{self.first_name[0]}{self.last_name[0]}".upper()
        return self.email[:2].upper()

    # ── Type helpers ──────────────────────────────────────────

    @property
    def is_customer(self) -> bool:
        return self.user_type == self.UserType.CUSTOMER

    @property
    def is_store_staff(self) -> bool:
        return self.user_type == self.UserType.STAFF

    @property
    def is_shop_owner(self) -> bool:
        """True if this TenantUser was created for a PlatformUser (shop owner)."""
        return bool(self.platform_user_id)

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
        if self.account_status not in (self.AccountStatus.ACTIVE,):
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
        """
        self.email = f"deleted_{self.id}@deleted.invalid"
        self.first_name = "Deleted"
        self.last_name = "User"
        self.phone = ""
        self.avatar_url = ""
        self.totp_secret = ""
        self.backup_codes_enc = ""
        self.platform_user_id = ""
        self.account_status = self.AccountStatus.DELETED
        self.is_active = False
        self.deleted_at = timezone.now()
        self.save()

    def set_marketing_consent(self, consent: bool, ip_address: str = None) -> None:
        """Record marketing consent with timestamp and IP."""
        self.email_marketing_consent = consent
        self.marketing_consent_ip = ip_address
        self.marketing_consent_at = timezone.now()
        self.save(update_fields=[
            "email_marketing_consent",
            "marketing_consent_ip",
            "marketing_consent_at",
        ])


# ─────────────────────────────────────────────────────────────
# SECTION 3 — EMAIL VERIFICATION TOKEN
# ─────────────────────────────────────────────────────────────

class TenantEmailVerificationToken(models.Model):
    """
    Secure time-limited token for tenant user email verification.

    Lives in the tenant schema — completely isolated per store.
    One active token per user per purpose.
    """

    class TokenPurpose(models.TextChoices):
        VERIFY_EMAIL = "VERIFY_EMAIL", _("Initial email verification")
        CHANGE_EMAIL = "CHANGE_EMAIL", _("Verify new email after change")
        REACTIVATE = "REACTIVATE",   _("Reactivate a suspended account")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        TenantUser,
        on_delete=models.CASCADE,
        related_name="email_verification_tokens",
    )
    token = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
    )
    purpose = models.CharField(
        max_length=20,
        choices=TokenPurpose.choices,
        default=TokenPurpose.VERIFY_EMAIL,
    )
    new_email = models.EmailField(blank=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "userauth"
        db_table = "tenant_email_verification_tokens"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"],  name="tenant_evt_token_idx"),
            models.Index(fields=["user", "purpose", "is_used"],
                         name="tenant_evt_user_purpose_idx"),
        ]

    def __str__(self) -> str:
        return f"TenantEmailVerification({self.user.email}, {self.purpose})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired

    @classmethod
    def create_for_user(
        cls,
        user: TenantUser,
        purpose: str = "VERIFY_EMAIL",
        new_email: str = "",
        ttl_hours: int = 24,
    ) -> "TenantEmailVerificationToken":
        """Create a new token, invalidating any existing active tokens."""
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
        """Mark token as used. Returns True if successfully consumed."""
        if not self.is_valid:
            return False
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at"])
        return True


# ─────────────────────────────────────────────────────────────
# SECTION 4 — PASSWORD RESET TOKEN
# ─────────────────────────────────────────────────────────────

class TenantPasswordResetToken(models.Model):
    """
    Secure time-limited token for tenant user password resets.

    Lives in the tenant schema — completely isolated per store.
    TTL: 1 hour. One active token per user.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        TenantUser,
        on_delete=models.CASCADE,
        related_name="password_reset_tokens",
    )
    token = models.CharField(max_length=128, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)
    request_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "userauth"
        db_table = "tenant_password_reset_tokens"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"],  name="tenant_prt_token_idx"),
            models.Index(fields=["user", "is_used"],
                         name="tenant_prt_user_idx"),
        ]

    def __str__(self) -> str:
        return f"TenantPasswordReset({self.user.email})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_used and not self.is_expired

    @classmethod
    def create_for_user(
        cls,
        user: TenantUser,
        request_ip: str = None,
        ttl_hours: int = 1,
    ) -> "TenantPasswordResetToken":
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
# SECTION 5 — LOGIN AUDIT LOG
# ─────────────────────────────────────────────────────────────

class TenantLoginAuditLog(models.Model):
    """
    Immutable audit log of every tenant-level login attempt.

    Lives in the tenant schema — completely isolated per store.
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
        PLATFORM_OWNER = "PLATFORM_OWNER", _(
            "Shop owner login via platform bridge")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        TenantUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="login_audit_logs",
    )
    attempted_email = models.EmailField()
    result = models.CharField(max_length=20, choices=LoginResult.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    is_suspicious = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "userauth"
        db_table = "tenant_login_audit_logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"],
                         name="tenant_audit_user_idx"),
            models.Index(fields=["ip_address"],
                         name="tenant_audit_ip_idx"),
            models.Index(fields=["is_suspicious"],
                         name="tenant_audit_suspicious_idx"),
        ]

    def __str__(self) -> str:
        return f"TenantAudit({self.attempted_email}, {self.result}, {self.created_at})"

    def save(self, *args, **kwargs):
        """Enforce immutability — audit logs cannot be updated."""
        if self.pk and TenantLoginAuditLog.objects.filter(pk=self.pk).exists():
            raise ValueError("TenantLoginAuditLog records are immutable.")
        super().save(*args, **kwargs)
