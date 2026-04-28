"""
accounts/models_part1.py
=========================
APP 2 — Accounts Domain | Multi-Tenant E-Commerce Platform
django-tenants schema-based isolation

PART 1 of 3  — Authentication & Identity (PUBLIC schema)
  Section 1  — Abstract bases
  Section 2  — Custom User model
  Section 3  — Email verification tokens
  Section 4  — Password reset tokens
  Section 5  — OAuth / social auth connections
  Section 6  — Two-factor authentication
  Section 7  — Login audit log
  Section 8  — API Keys (platform-wide)

Architecture note
─────────────────
User lives in the PUBLIC schema — one User can be staff on
multiple tenant stores simultaneously via StoreStaff (tenant schema).
Customers are tenant-scoped — a Customer record exists per tenant.
"""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import timedelta
from django.db.models import Q
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from dashboard.settings.models import AuditModel, MixIdAndTimeModel, IduuidModel
from django.contrib.auth.models import User as AuthUser
from django.core.validators import RegexValidator

# ─────────────────────────────────────────────────────────────
# SECTION 1 — USER
# ─────────────────────────────────────────────────────────────


class User(AuditModel):
    """
    Central platform profile — lives in the PUBLIC schema.

    Wraps Django's AuthUser (which owns email/password/is_active).
    Holds identity details, security state, locale preferences, and
    verification flags that are shared across ALL tenant stores.

    NOT the right place for:
      • Commerce stats  → Customer
      • Store roles     → StoreStaff
      • Store consent   → Customer
    """

    class UserType(models.TextChoices):
        STAFF = "staff",    _("Staff Member")
        CUSTOMER = "customer", _("Customer")
        # VENDOR    = "vendor",    _("Vendor")
        # AFFILIATE = "affiliate", _("Affiliate")

    class Gender(models.TextChoices):
        MALE = "M", _("Male")
        FEMALE = "F", _("Female")
        OTHER = "O", _("Other")
        PREFER_NOT_SAY = "N", _("Prefer not to say")

    # ── Identity ──────────────────────────────────────────────────────
    auth_user = models.OneToOneField(
        AuthUser,
        on_delete=models.CASCADE,
        related_name="profile",
        help_text=_(
            "Underlying Django auth user (owns email, password, is_active)."),
    )
    user_type = models.CharField(
        max_length=10,
        choices=UserType.choices,
        default=UserType.CUSTOMER,
        db_index=True,
    )

    # ── Personal details ──────────────────────────────────────────────
    phone = models.CharField(
        max_length=20,
        blank=True,
        validators=[RegexValidator(
            r"^\+?1?\d{9,15}$", _("Enter a valid phone number."))],
        db_index=True,
    )
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)

    # ── Locale / preferences ──────────────────────────────────────────
    # Store-level locale overrides live on Customer.
    preferred_language = models.CharField(max_length=10, default="en")
    preferred_currency = models.CharField(max_length=3,  default="USD")
    timezone = models.CharField(max_length=50, default="UTC")

    # ── Verification ──────────────────────────────────────────────────
    email_verified = models.BooleanField(default=False, db_index=True)
    phone_verified = models.BooleanField(default=False, db_index=True)

    # ── Security ──────────────────────────────────────────────────────
    # two_factor_enabled is the platform-level flag; StoreStaff.require_2fa
    # is a per-store enforcement rule (can be True even if this is False,
    # forcing the user to enable 2FA before accessing that store).
    # two_factor_enabled    = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)

    # ── Activity ──────────────────────────────────────────────────────
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_ip = models.GenericIPAddressField(null=True, blank=True)
    login_count = models.PositiveIntegerField(default=0)

    # ── Metadata ──────────────────────────────────────────────────────
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            "Arbitrary extra data (integrations, feature flags, etc.)."),
    )

    class Meta:
        db_table = 'tenant_users'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_type',]),
        ]


    def __str__(self):
        return f"{self.user.get_full_name()} ({self.user.email})"


    # def get_full_name(self):
    #     """Return the full name of the user."""
    #     return f"{self.first_name} {self.last_name}".strip()

    # def get_short_name(self):
    #     """Return the short name for the user."""
    #     return self.first_name

    def has_permission(self, permission_codename):
        """Check if user has a specific permission."""
        # Check custom permissions
        if self.custom_permissions.filter(codename=permission_codename, is_active=True).exists():
            return True

        # Check role permissions
        for role in self.roles.filter(is_active=True):
            if permission_codename in [p.codename for p in role.get_all_permissions()]:
                return True

        return False

    def get_all_permissions(self):
        """Get all permissions for this user."""
        permissions = set(self.custom_permissions.filter(is_active=True))
        for role in self.roles.filter(is_active=True):
            permissions.update(role.get_all_permissions())
        return permissions

    def is_staff_member(self):
        """Check if user is a staff member."""
        return self.user_type == 'staff'

    def is_customer(self):
        """Check if user is a customer."""
        return self.user_type == 'customer'

    # def update_customer_metrics(self):
    #     """Update customer business metrics."""
    #     if self.user_type == 'customer':
    #         from public.order.models import Order  # Avoid circular import
    #         orders = Order.objects.filter(customer=self, status='completed')
    #         self.total_orders = orders.count()
    #         self.total_spent = sum(order.total_amount for order in orders)
    #         self.average_order_value = self.total_spent / \
    #             self.total_orders if self.total_orders > 0 else Decimal('0.00')
    #         self.save(update_fields=['total_orders',
    #                   'total_spent', 'average_order_value'])

    def can_login(self):
        """Check if user can login."""
        if self.status not in ['active']:
            return False
        if self.account_locked_until and self.account_locked_until > timezone.now():
            return False
        return True

    def lock_account(self, duration_minutes=30):
        """Lock user account for specified duration."""
        self.account_locked_until = timezone.now(
        ) + timezone.timedelta(minutes=duration_minutes)
        self.save(update_fields=['account_locked_until'])

    def unlock_account(self):
        """Unlock user account."""
        self.account_locked_until = None
        self.failed_login_attempts = 0
        self.save(update_fields=[
                  'account_locked_until', 'failed_login_attempts'])


# ─────────────────────────────────────────────────────────────
# SECTION 3 — EMAIL VERIFICATION TOKENS  (public schema)
# ─────────────────────────────────────────────────────────────

class EmailVerificationToken(MixIdAndTimeModel):
    """
    Secure time-limited token sent to a user's email for verification.
    One active token per user — creating a new one invalidates the previous.
    """

    class TokenPurpose(models.TextChoices):
        VERIFY_EMAIL = "VERIFY_EMAIL",    _("Initial email verification")
        CHANGE_EMAIL = "CHANGE_EMAIL",    _("Verify new email after change")
        REACTIVATE = "REACTIVATE",      _("Reactivate a suspended account")

    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name="email_verification_tokens")
    token = models.CharField(max_length=128, unique=True, db_index=True)
    purpose = models.CharField(max_length=20, choices=TokenPurpose.choices,
                               default=TokenPurpose.VERIFY_EMAIL)
    new_email = models.EmailField(blank=True,
                                  help_text="For CHANGE_EMAIL — the new email being verified")
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        app_label = "userauth"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"EmailVerification({self.user.email}, {self.purpose})"

    @classmethod
    def create_for_user(cls, user: User, purpose: str = "VERIFY_EMAIL",
                        new_email: str = "", ttl_hours: int = 24) -> "EmailVerificationToken":
        # Invalidate existing tokens of same purpose
        cls.objects.filter(user=user, purpose=purpose,
                           is_used=False).update(is_used=True)
        token = secrets.token_urlsafe(64)
        return cls.objects.create(
            user=user,
            token=token,
            purpose=purpose,
            new_email=new_email,
            expires_at=timezone.now() + timedelta(hours=ttl_hours),
        )

    @property
    def is_valid(self) -> bool:
        return not self.is_used and timezone.now() < self.expires_at

    def consume(self) -> bool:
        """Mark token as used. Returns True if it was valid."""
        if not self.is_valid:
            return False
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at"])
        return True


# ─────────────────────────────────────────────────────────────
# SECTION 4 — PASSWORD RESET TOKENS  (public schema)
# ─────────────────────────────────────────────────────────────

class PasswordResetToken(MixIdAndTimeModel):
    """
    Secure short-lived token for password reset flow.
    Expires in 1 hour. One active token per user.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name="password_reset_tokens")
    token = models.CharField(max_length=128, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        app_label = "userauth"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"PasswordReset({self.user.email})"

    @classmethod
    def create_for_user(cls, user: User, ip_address: str = "") -> "PasswordResetToken":
        cls.objects.filter(user=user, is_used=False).update(is_used=True)
        return cls.objects.create(
            user=user,
            token=secrets.token_urlsafe(64),
            expires_at=timezone.now() + timedelta(hours=1),
            ip_address=ip_address or None,
        )

    @property
    def is_valid(self) -> bool:
        return not self.is_used and timezone.now() < self.expires_at

    def consume(self) -> bool:
        if not self.is_valid:
            return False
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=["is_used", "used_at"])
        return True


# ─────────────────────────────────────────────────────────────
# SECTION 5 — OAUTH / SOCIAL AUTH  (public schema)
# ─────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────
# SECTION 7 — LOGIN AUDIT LOG  (public schema)
# ─────────────────────────────────────────────────────────────

class LoginAuditLog(MixIdAndTimeModel):
    """
    Immutable record of every login attempt — successful and failed.
    Append-only. Never update or delete.
    Powers security alerts and anomaly detection.
    """

    class LoginResult(models.TextChoices):
        SUCCESS = "SUCCESS",          _("Successful login")
        FAILED_PASSWORD = "FAILED_PASSWORD",  _("Wrong password")
        FAILED_2FA = "FAILED_2FA",       _("Valid password but wrong 2FA code")
        FAILED_LOCKED = "FAILED_LOCKED",    _("Account locked")
        FAILED_INACTIVE = "FAILED_INACTIVE",  _("Account not active")
        FAILED_UNVERIFIED = "FAILED_UNVERIFIED", _("Email not verified")
        OAUTH_SUCCESS = "OAUTH_SUCCESS",    _("Successful OAuth login")
        OAUTH_FAILED = "OAUTH_FAILED",     _("OAuth login failed")
        LOGOUT = "LOGOUT",           _("User logged out")
        SESSION_EXPIRED = "SESSION_EXPIRED",  _("Session timed out")

    user = models.ForeignKey(User, on_delete=models.SET_NULL,
                             null=True, blank=True, related_name="login_audit_logs",
                             help_text="Null if user not found (unrecognised email attempt)")
    email = models.EmailField(db_index=True,
                              help_text="Email from login form — even if user not found")
    result = models.CharField(
        max_length=20, choices=LoginResult.choices, db_index=True)

    # Request metadata
    ip_address = models.GenericIPAddressField(db_index=True)
    user_agent = models.TextField(blank=True)
    device_type = models.CharField(max_length=20, blank=True,
                                   help_text="mobile, tablet, desktop")
    browser = models.CharField(max_length=50, blank=True)
    os = models.CharField(max_length=50, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    city = models.CharField(max_length=100, blank=True)

    # Tenant context (if login was for a specific store)
    tenant_schema = models.CharField(max_length=63, blank=True, db_index=True)

    # Risk
    is_suspicious = models.BooleanField(default=False,
                                        help_text="Flagged by anomaly detection")
    risk_reason = models.TextField(blank=True)

    class Meta:
        app_label = "userauth"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["ip_address", "created_at"]),
            models.Index(fields=["result", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.email} → {self.result} @ {self.created_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        """Immutable — block updates."""
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValueError("LoginAuditLog is immutable.")
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────
# SECTION 8 — API KEYS  (public schema — tenant-scoped by schema_name)
# ─────────────────────────────────────────────────────────────

class APIKey(MixIdAndTimeModel):
    """
    Programmatic API keys for storefront and third-party integrations.
    Keys are hashed before storage — shown in full only once at creation.
    Supports scoped permissions (read-only, full access, webhook-only).
    """

    class KeyType(models.TextChoices):
        PUBLIC = "PUBLIC",     _("Public — storefront JS, safe to expose")
        SECRET = "SECRET",     _("Secret — server-side only")
        WEBHOOK = "WEBHOOK",    _("Webhook — signing key only")

    class KeyStatus(models.TextChoices):
        ACTIVE = "ACTIVE",   _("Active")
        REVOKED = "REVOKED",  _("Revoked")
        EXPIRED = "EXPIRED",  _("Expired")

    # Scoped to a tenant but not FK'd (cross-schema)
    tenant_schema_name = models.CharField(max_length=63, db_index=True)
    # Owner (the staff member who created it)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="api_keys")

    name = models.CharField(max_length=100,
                            help_text="Human label e.g. 'Mobile App Key'")
    key_type = models.CharField(max_length=10, choices=KeyType.choices)
    status = models.CharField(max_length=10, choices=KeyStatus.choices,
                              default=KeyStatus.ACTIVE)

    # The key prefix is shown in the UI (e.g. "pk_live_abc123...")
    # Full key is only shown once — we store the hash.
    key_prefix = models.CharField(max_length=16, db_index=True,
                                  help_text="First 16 chars — shown in UI for identification")
    key_hash = models.CharField(max_length=128,
                                help_text="SHA-256 hash of the full key — used for lookup")

    # Permissions
    scopes = models.JSONField(default=list,
                              help_text="List of permission scopes e.g. ['orders.read','products.write']")

    # Validity
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    last_used_ip = models.GenericIPAddressField(null=True, blank=True)
    request_count = models.PositiveBigIntegerField(default=0)

    # Metadata
    description = models.TextField(blank=True)
    ip_allowlist = models.JSONField(default=list, blank=True,
                                    help_text="Optional list of allowed IPs. Empty = all allowed.")

    class Meta:
        app_label = "userauth"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["key_hash"]),
            models.Index(fields=["tenant_schema_name", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.key_prefix}...)"

    @classmethod
    def generate(cls, tenant_schema_name: str, name: str, key_type: str,
                 scopes: list = None, created_by: User = None,
                 expires_in_days: int = None) -> tuple["APIKey", str]:
        """
        Generate a new API key. Returns (APIKey instance, plaintext_key).
        The plaintext key is NEVER stored — show it once to the user.
        """
        import hashlib

        prefix_map = {
            "PUBLIC":  "pk_live_",
            "SECRET":  "sk_live_",
            "WEBHOOK": "wh_live_",
        }

        random_part = secrets.token_urlsafe(32)
        full_key = f"{prefix_map.get(key_type, 'key_')}{random_part}"
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()
        key_prefix = full_key[:16]

        expires_at = (
            timezone.now() + timedelta(days=expires_in_days)
            if expires_in_days else None
        )

        instance = cls.objects.create(
            tenant_schema_name=tenant_schema_name,
            created_by=created_by,
            name=name,
            key_type=key_type,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=scopes or [],
            expires_at=expires_at,
        )

        return instance, full_key

    @classmethod
    def authenticate(cls, raw_key: str) -> "APIKey | None":
        """Look up and validate a raw API key. Returns None if invalid."""
        import hashlib
        if not raw_key:
            return None
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        try:
            key = cls.objects.get(
                key_hash=key_hash, status=cls.KeyStatus.ACTIVE)
        except cls.DoesNotExist:
            return None
        if key.expires_at and timezone.now() > key.expires_at:
            key.status = cls.KeyStatus.EXPIRED
            key.save(update_fields=["status"])
            return None
        return key

    def revoke(self) -> None:
        self.status = self.KeyStatus.REVOKED
        self.save(update_fields=["status", "updated_at"])



