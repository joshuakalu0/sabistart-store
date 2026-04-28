"""
accounts/utils/auth_service.py
================================
Authentication service layer — all auth flows in one place.
Views call these functions; they never import from views.

Public API:
    register_user(...)              → RegisterResult
    login_user(request, ...)        → LoginResult
    logout_user(request)            → None
    verify_email(token)             → VerifyResult
    resend_verification(email)      → bool
    request_password_reset(email)   → bool
    reset_password(token, password) → ResetResult
    change_password(user, ...)      → ChangePasswordResult
    change_email(user, new_email)   → bool
    enable_2fa(user)                → TwoFASetupResult
    confirm_2fa(user, code)         → bool
    verify_2fa_code(user, code)     → bool
    disable_2fa(user, code)         → bool
    authenticate_social(...)        → LoginResult
    get_login_history(user, limit)  → QuerySet
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from django.contrib.auth import login, logout
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("accounts.auth_service")


# ─────────────────────────────────────────────────────────────
# RESULT DATACLASSES
# ─────────────────────────────────────────────────────────────

@dataclass
class RegisterResult:
    success: bool
    user_id: Optional[str] = None
    email: str = ""
    requires_verification: bool = True
    error: str = ""
    error_code: str = ""
    field_errors: dict = field(default_factory=dict)


@dataclass
class LoginResult:
    success: bool
    user_id: Optional[str] = None
    email: str = ""
    requires_2fa: bool = False
    requires_verification: bool = False
    is_new_user: bool = False          # OAuth only
    redirect_url: str = ""
    error: str = ""
    error_code: str = ""


@dataclass
class VerifyResult:
    success: bool
    email: str = ""
    error: str = ""
    error_code: str = ""


@dataclass
class ResetResult:
    success: bool
    error: str = ""
    error_code: str = ""
    field_errors: dict = field(default_factory=dict)


@dataclass
class ChangePasswordResult:
    success: bool
    error: str = ""
    field_errors: dict = field(default_factory=dict)


@dataclass
class TwoFASetupResult:
    success: bool
    secret: str = ""
    qr_code_uri: str = ""
    backup_codes: list = field(default_factory=list)
    error: str = ""


# ─────────────────────────────────────────────────────────────
# REGISTRATION
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def register_user(
    email: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
    phone: str = "",
    email_marketing: bool = False,
    ip_address: str = "",
    tenant_schema: str = "",
) -> RegisterResult:
    """
    Register a new platform User and optionally create a Customer
    record in the current tenant schema.

    Steps:
      1. Validate inputs
      2. Check email uniqueness
      3. Create User (status=PENDING)
      4. Send verification email
      5. Create Customer record in tenant schema (if schema provided)
    """
    from accounts.models import User, EmailVerificationToken

    email = email.strip().lower()

    # ── Validation ────────────────────────────────────────────
    field_errors = {}

    if not email:
        field_errors["email"] = "Email address is required."
    elif User.objects.filter(email=email).exists():
        field_errors["email"] = "An account with this email already exists."

    if not password:
        field_errors["password"] = "Password is required."
    elif len(password) < 8:
        field_errors["password"] = "Password must be at least 8 characters."

    if field_errors:
        return RegisterResult(
            success=False,
            error="Please fix the errors below.",
            error_code="VALIDATION_ERROR",
            field_errors=field_errors,
        )

    # ── Create user ───────────────────────────────────────────
    user = User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        phone=phone.strip(),
        email_marketing=email_marketing,
        account_status=User.AccountStatus.PENDING,
        is_verified=False,
    )

    # ── Send verification email ────────────────────────────────
    token = EmailVerificationToken.create_for_user(user)
    _send_verification_email(user, token.token)

    # ── Create tenant Customer record ──────────────────────────
    if tenant_schema:
        _create_customer_for_user(user, ip_address)

    logger.info("New user registered: %s (id=%s)", email, user.id)

    return RegisterResult(
        success=True,
        user_id=str(user.id),
        email=email,
        requires_verification=True,
    )


def _create_customer_for_user(user, ip_address: str = "") -> None:
    """Create a Customer record in the current tenant schema for a new user."""
    from accounts.models import Customer, CustomerGroup
    try:
        customer, created = Customer.objects.get_or_create(
            email=user.email,
            defaults={
                "user_id":         user.id,
                "first_name":      user.first_name,
                "last_name":       user.last_name,
                "phone":           user.phone,
                "acquisition_source": Customer.AcquisitionSource.ORGANIC,
                "last_seen_ip":    ip_address or None,
            }
        )
        if created:
            # Add to "All Customers" system group if it exists
            all_group = CustomerGroup.objects.filter(is_system=True).first()
            if all_group:
                customer.groups.add(all_group)
    except Exception as exc:
        logger.warning("Could not create Customer for user %s: %s", user.email, exc)


# ─────────────────────────────────────────────────────────────
# LOGIN / LOGOUT
# ─────────────────────────────────────────────────────────────

def login_user(
    request,
    email: str,
    password: str,
    remember_me: bool = False,
    tenant_schema: str = "",
) -> LoginResult:
    """
    Authenticate a user by email and password.

    Returns LoginResult with requires_2fa=True if the user has TOTP enabled.
    In that case the view should redirect to the 2FA verification step
    without creating a full session yet.
    """
    from accounts.models import User, LoginAuditLog
    from django.contrib.auth import authenticate

    email = email.strip().lower()
    ip    = _get_ip(request)

    def _log(result: str, user=None, suspicious=False, reason=""):
        try:
            LoginAuditLog.objects.create(
                user=user,
                email=email,
                result=result,
                ip_address=ip or "127.0.0.1",
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                tenant_schema=tenant_schema,
                is_suspicious=suspicious,
                risk_reason=reason,
            )
        except Exception:
            pass  # Never fail login flow due to audit log error

    # ── Find user ─────────────────────────────────────────────
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        _log(LoginAuditLog.LoginResult.FAILED_PASSWORD)
        return LoginResult(
            success=False,
            error="Invalid email or password.",
            error_code="INVALID_CREDENTIALS",
        )

    # ── Account state checks ──────────────────────────────────
    if user.is_soft_deleted:
        _log(LoginAuditLog.LoginResult.FAILED_INACTIVE, user)
        return LoginResult(success=False, error="Account not found.", error_code="INVALID_CREDENTIALS")

    if user.is_locked:
        from django.utils.timesince import timeuntil
        _log(LoginAuditLog.LoginResult.FAILED_LOCKED, user)
        return LoginResult(
            success=False,
            error=f"Account temporarily locked. Try again later.",
            error_code="ACCOUNT_LOCKED",
        )

    if user.account_status == User.AccountStatus.SUSPENDED:
        _log(LoginAuditLog.LoginResult.FAILED_INACTIVE, user)
        return LoginResult(
            success=False,
            error="Your account has been suspended. Contact support.",
            error_code="ACCOUNT_SUSPENDED",
        )

    # ── Password check ────────────────────────────────────────
    if not user.check_password(password):
        user.record_failed_login()
        _log(LoginAuditLog.LoginResult.FAILED_PASSWORD, user)
        remaining = max(0, 10 - user.failed_login_count)
        error_msg = "Invalid email or password."
        if user.failed_login_count >= 7:
            error_msg += f" {remaining} attempt(s) before lockout."
        return LoginResult(success=False, error=error_msg, error_code="INVALID_CREDENTIALS")

    # ── Email verification check ──────────────────────────────
    if not user.is_verified:
        _log(LoginAuditLog.LoginResult.FAILED_UNVERIFIED, user)
        return LoginResult(
            success=False,
            requires_verification=True,
            email=email,
            error="Please verify your email address before logging in.",
            error_code="EMAIL_NOT_VERIFIED",
        )

    # ── 2FA check ─────────────────────────────────────────────
    if user.totp_enabled:
        # Don't create session yet — store user_id in session for 2FA step
        request.session["2fa_user_id"]    = str(user.id)
        request.session["2fa_remember_me"] = remember_me
        return LoginResult(
            success=True,
            user_id=str(user.id),
            email=email,
            requires_2fa=True,
        )

    # ── Complete login ────────────────────────────────────────
    _complete_login(request, user, remember_me, ip)
    _log(LoginAuditLog.LoginResult.SUCCESS, user)
    logger.info("User logged in: %s", email)

    return LoginResult(
        success=True,
        user_id=str(user.id),
        email=email,
    )


def _complete_login(request, user, remember_me: bool, ip: str) -> None:
    """Finish the login flow — create session, update user fields."""
    login(request, user)
    if not remember_me:
        request.session.set_expiry(0)  # Session expires when browser closes
    else:
        request.session.set_expiry(60 * 60 * 24 * 30)  # 30 days
    user.record_login(ip)

    if user.force_password_reset:
        request.session["force_password_reset"] = True


def logout_user(request) -> None:
    """Log out the current user and clear session."""
    from accounts.models import LoginAuditLog
    user = request.user
    if user.is_authenticated:
        try:
            LoginAuditLog.objects.create(
                user=user,
                email=user.email,
                result=LoginAuditLog.LoginResult.LOGOUT,
                ip_address=_get_ip(request) or "127.0.0.1",
                user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
            )
        except Exception:
            pass
    logout(request)


# ─────────────────────────────────────────────────────────────
# EMAIL VERIFICATION
# ─────────────────────────────────────────────────────────────

def verify_email(token: str) -> VerifyResult:
    """Consume an email verification token and activate the user."""
    from accounts.models import EmailVerificationToken, User

    try:
        token_obj = EmailVerificationToken.objects.select_related("user").get(
            token=token
        )
    except EmailVerificationToken.DoesNotExist:
        return VerifyResult(success=False, error="Invalid verification link.", error_code="INVALID_TOKEN")

    if not token_obj.is_valid:
        return VerifyResult(
            success=False,
            error="This verification link has expired. Request a new one.",
            error_code="TOKEN_EXPIRED",
        )

    user = token_obj.user

    if token_obj.purpose == EmailVerificationToken.TokenPurpose.CHANGE_EMAIL:
        old_email = user.email
        user.email = token_obj.new_email
        user.save(update_fields=["email", "updated_at"])
        token_obj.consume()
        logger.info("Email changed: %s → %s", old_email, user.email)
        return VerifyResult(success=True, email=user.email)

    token_obj.consume()
    user.is_verified   = True
    user.verified_at   = timezone.now()
    user.account_status = User.AccountStatus.ACTIVE
    user.save(update_fields=["is_verified", "verified_at", "account_status", "updated_at"])

    logger.info("Email verified: %s", user.email)
    return VerifyResult(success=True, email=user.email)


def resend_verification(email: str) -> bool:
    """Resend a verification email if the user exists and is unverified."""
    from accounts.models import User, EmailVerificationToken

    try:
        user = User.objects.get(email=email.strip().lower(), is_verified=False)
    except User.DoesNotExist:
        return False  # Silently fail — don't reveal if email exists

    token = EmailVerificationToken.create_for_user(user)
    _send_verification_email(user, token.token)
    return True


# ─────────────────────────────────────────────────────────────
# PASSWORD RESET
# ─────────────────────────────────────────────────────────────

def request_password_reset(email: str, ip_address: str = "") -> bool:
    """
    Request a password reset. Always returns True regardless of
    whether the email exists (prevents email enumeration).
    """
    from accounts.models import User, PasswordResetToken

    email = email.strip().lower()
    try:
        user = User.objects.get(email=email, is_active=True)
    except User.DoesNotExist:
        logger.info("Password reset requested for unknown email: %s", email)
        return True  # Silent fail

    token = PasswordResetToken.create_for_user(user, ip_address=ip_address)
    _send_password_reset_email(user, token.token)
    logger.info("Password reset requested for: %s", email)
    return True


def reset_password(token: str, new_password: str, confirm_password: str = "") -> ResetResult:
    """Consume a password reset token and set the new password."""
    from accounts.models import PasswordResetToken

    field_errors = {}

    if not new_password:
        field_errors["password"] = "New password is required."
    elif len(new_password) < 8:
        field_errors["password"] = "Password must be at least 8 characters."
    if confirm_password and new_password != confirm_password:
        field_errors["confirm_password"] = "Passwords do not match."

    if field_errors:
        return ResetResult(success=False, error="Please fix the errors below.",
                          error_code="VALIDATION_ERROR", field_errors=field_errors)

    try:
        token_obj = PasswordResetToken.objects.select_related("user").get(token=token)
    except PasswordResetToken.DoesNotExist:
        return ResetResult(success=False, error="Invalid or expired reset link.",
                          error_code="INVALID_TOKEN")

    if not token_obj.is_valid:
        return ResetResult(success=False,
                          error="This reset link has expired. Please request a new one.",
                          error_code="TOKEN_EXPIRED")

    user = token_obj.user
    token_obj.consume()

    user.set_password(new_password)
    user.password_changed_at  = timezone.now()
    user.force_password_reset = False
    user.failed_login_count   = 0
    user.locked_until         = None
    user.save(update_fields=[
        "password", "password_changed_at",
        "force_password_reset", "failed_login_count",
        "locked_until", "updated_at",
    ])

    logger.info("Password reset completed for: %s", user.email)
    return ResetResult(success=True)


def change_password(
    user,
    current_password: str,
    new_password: str,
    confirm_password: str = "",
) -> ChangePasswordResult:
    """Change password for a logged-in user."""
    field_errors = {}

    if not user.check_password(current_password):
        field_errors["current_password"] = "Current password is incorrect."
    if not new_password or len(new_password) < 8:
        field_errors["new_password"] = "New password must be at least 8 characters."
    if confirm_password and new_password != confirm_password:
        field_errors["confirm_password"] = "Passwords do not match."
    if new_password and new_password == current_password:
        field_errors["new_password"] = "New password must be different from the current one."

    if field_errors:
        return ChangePasswordResult(
            success=False,
            error="Please fix the errors below.",
            field_errors=field_errors,
        )

    user.set_password(new_password)
    user.password_changed_at = timezone.now()
    user.save(update_fields=["password", "password_changed_at", "updated_at"])
    logger.info("Password changed for: %s", user.email)
    return ChangePasswordResult(success=True)


def change_email(user, new_email: str) -> bool:
    """Initiate an email change — sends verification to the new address."""
    from accounts.models import User, EmailVerificationToken

    new_email = new_email.strip().lower()
    if User.objects.filter(email=new_email).exclude(id=user.id).exists():
        return False

    token = EmailVerificationToken.create_for_user(
        user,
        purpose=EmailVerificationToken.TokenPurpose.CHANGE_EMAIL,
        new_email=new_email,
    )
    _send_email_change_verification(user, token.token, new_email)
    return True


# ─────────────────────────────────────────────────────────────
# TWO-FACTOR AUTHENTICATION
# ─────────────────────────────────────────────────────────────

def enable_2fa(user) -> TwoFASetupResult:
    """
    Begin 2FA setup. Generates a TOTP secret and QR code URI.
    The user must confirm with a valid code before 2FA is active.
    """
    import base64
    import struct
    from accounts.models import TOTPDevice, BackupCode

    # Generate random 20-byte secret
    import os
    secret_bytes = os.urandom(20)
    secret_b32   = base64.b32encode(secret_bytes).decode()

    # Encrypt before storing
    from accounts.utils.encryption import encrypt_value
    secret_enc = encrypt_value(secret_b32)

    device, _ = TOTPDevice.objects.update_or_create(
        user=user,
        defaults={
            "secret_enc": secret_enc,
            "status": TOTPDevice.DeviceStatus.UNCONFIRMED,
        }
    )

    # QR code URI for authenticator apps
    qr_uri = (
        f"otpauth://totp/{user.email}"
        f"?secret={secret_b32}"
        f"&issuer=MultiStore"
        f"&algorithm=SHA1"
        f"&digits=6"
        f"&period=30"
    )

    backup_codes = BackupCode.generate_for_user(user)

    return TwoFASetupResult(
        success=True,
        secret=secret_b32,
        qr_code_uri=qr_uri,
        backup_codes=backup_codes,
    )


def confirm_2fa(user, code: str) -> bool:
    """Confirm 2FA setup with the first valid TOTP code."""
    from accounts.models import TOTPDevice

    try:
        device = TOTPDevice.objects.get(user=user, status=TOTPDevice.DeviceStatus.UNCONFIRMED)
    except TOTPDevice.DoesNotExist:
        return False

    if not _verify_totp_code(device, code):
        return False

    device.status       = TOTPDevice.DeviceStatus.CONFIRMED
    device.confirmed_at = timezone.now()
    device.save(update_fields=["status", "confirmed_at"])

    user.totp_enabled      = True
    user.totp_confirmed_at = timezone.now()
    user.save(update_fields=["totp_enabled", "totp_confirmed_at", "updated_at"])
    return True


def verify_2fa_code(user, code: str) -> bool:
    """Verify a TOTP code or backup code at login time."""
    from accounts.models import TOTPDevice, BackupCode
    import hashlib

    code = code.strip().replace(" ", "")

    # Try TOTP device first
    try:
        device = TOTPDevice.objects.get(user=user, status=TOTPDevice.DeviceStatus.CONFIRMED)
        if _verify_totp_code(device, code):
            device.last_used_at   = timezone.now()
            device.last_used_code = code
            device.save(update_fields=["last_used_at", "last_used_code"])
            return True
    except TOTPDevice.DoesNotExist:
        pass

    # Try backup code
    code_hash = hashlib.sha256(code.encode()).hexdigest()
    backup = BackupCode.objects.filter(user=user, code_hash=code_hash, is_used=False).first()
    if backup:
        backup.is_used = True
        backup.used_at = timezone.now()
        backup.save(update_fields=["is_used", "used_at"])
        return True

    return False


def complete_2fa_login(request, user_id: str, code: str) -> LoginResult:
    """
    Second step of 2FA login flow.
    Called after initial credentials pass — verifies the TOTP code.
    """
    from accounts.models import User

    pending_id = request.session.get("2fa_user_id")
    if not pending_id or pending_id != user_id:
        return LoginResult(success=False, error="Session expired.", error_code="SESSION_EXPIRED")

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return LoginResult(success=False, error="User not found.", error_code="NOT_FOUND")

    if not verify_2fa_code(user, code):
        return LoginResult(
            success=False,
            error="Invalid authentication code. Try again.",
            error_code="INVALID_2FA_CODE",
        )

    remember_me = request.session.get("2fa_remember_me", False)
    ip          = _get_ip(request)
    _complete_login(request, user, remember_me, ip)

    del request.session["2fa_user_id"]
    request.session.pop("2fa_remember_me", None)

    return LoginResult(success=True, user_id=str(user.id), email=user.email)


def disable_2fa(user, code: str) -> bool:
    """Disable 2FA after verifying current code. Deletes device and backup codes."""
    from accounts.models import TOTPDevice, BackupCode

    if not verify_2fa_code(user, code):
        return False

    TOTPDevice.objects.filter(user=user).delete()
    BackupCode.objects.filter(user=user).delete()

    user.totp_enabled = False
    user.totp_secret  = ""
    user.save(update_fields=["totp_enabled", "totp_secret", "updated_at"])
    return True


def _verify_totp_code(device, code: str) -> bool:
    """
    Verify a 6-digit TOTP code against the device secret.
    Checks current window ± 1 (allows 30 second clock drift).
    """
    import time
    import hmac
    import hashlib
    import struct
    import base64

    try:
        from accounts.utils.encryption import decrypt_value
        secret_b32 = decrypt_value(bytes(device.secret_enc))
        secret     = base64.b32decode(secret_b32.upper())
    except Exception:
        return False

    # Replay check
    if device.last_used_code == code:
        return False

    timestamp = int(time.time() // 30)
    for offset in [-1, 0, 1]:
        msg    = struct.pack(">Q", timestamp + offset)
        digest = hmac.new(secret, msg, hashlib.sha1).digest()
        offset_val = digest[-1] & 0x0F
        token  = (struct.unpack(">I", digest[offset_val:offset_val + 4])[0] & 0x7FFFFFFF) % 1_000_000
        if code == f"{token:06d}":
            return True
    return False


# ─────────────────────────────────────────────────────────────
# OAUTH / SOCIAL AUTH
# ─────────────────────────────────────────────────────────────

@transaction.atomic
def authenticate_social(
    request,
    provider: str,
    provider_uid: str,
    email: str,
    first_name: str = "",
    last_name: str = "",
    avatar_url: str = "",
    access_token: str = "",
    raw_profile: dict = None,
) -> LoginResult:
    """
    Authenticate or register via OAuth provider.
    If SocialConnection exists → log in the user.
    If email matches existing User → link the social connection.
    Otherwise → create new User + SocialConnection.
    """
    from accounts.models import User, SocialConnection, LoginAuditLog

    email = email.strip().lower()
    ip    = _get_ip(request)

    # ── Find or create user ───────────────────────────────────
    is_new_user = False

    # Check if social connection already exists
    try:
        connection = SocialConnection.objects.select_related("user").get(
            provider=provider, provider_uid=provider_uid
        )
        user = connection.user
    except SocialConnection.DoesNotExist:
        # Try to link to existing user by email
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Create new user
            user = User.objects.create_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                avatar_url=avatar_url,
                is_verified=True,
                account_status=User.AccountStatus.ACTIVE,
            )
            user.set_unusable_password()
            user.save()
            _create_customer_for_user(user, _get_ip(request))
            is_new_user = True

        # Create social connection
        SocialConnection.objects.create(
            user=user,
            provider=provider,
            provider_uid=provider_uid,
            email=email,
            display_name=f"{first_name} {last_name}".strip(),
            avatar_url=avatar_url,
            raw_profile=raw_profile or {},
        )

    if not user.is_active:
        return LoginResult(success=False, error="Account is inactive.", error_code="ACCOUNT_INACTIVE")

    _complete_login(request, user, remember_me=True, ip=ip)

    try:
        LoginAuditLog.objects.create(
            user=user,
            email=email,
            result=LoginAuditLog.LoginResult.OAUTH_SUCCESS,
            ip_address=ip or "127.0.0.1",
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
        )
    except Exception:
        pass

    return LoginResult(
        success=True,
        user_id=str(user.id),
        email=user.email,
        is_new_user=is_new_user,
    )


# ─────────────────────────────────────────────────────────────
# QUERIES
# ─────────────────────────────────────────────────────────────

def get_login_history(user, limit: int = 20):
    from accounts.models import LoginAuditLog
    return LoginAuditLog.objects.filter(user=user).order_by("-created_at")[:limit]


# ─────────────────────────────────────────────────────────────
# EMAIL STUBS (wire to your notification system)
# ─────────────────────────────────────────────────────────────

def _send_verification_email(user, token: str) -> None:
    """
    Send email verification link to user.
    Wire this to App 10 (notifications) when built.
    URL pattern: /accounts/verify-email/<token>/
    """
    logger.info("Verification email queued for: %s (token=%s...)", user.email, token[:8])
    # from notifications.tasks import send_email_task
    # send_email_task.delay(
    #     template="email_verification",
    #     recipient=user.email,
    #     context={"name": user.get_short_name(), "token": token},
    # )


def _send_password_reset_email(user, token: str) -> None:
    logger.info("Password reset email queued for: %s", user.email)
    # Wire to notifications app


def _send_email_change_verification(user, token: str, new_email: str) -> None:
    logger.info("Email change verification queued for: %s → %s", user.email, new_email)
    # Wire to notifications app


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────

def _get_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")
