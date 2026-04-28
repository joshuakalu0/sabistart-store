"""
system/account/backends.py
===========================
Platform-Level Authentication Backend — PUBLIC SCHEMA

Authenticates PlatformUser instances (shop owners / tenant creators).
Used for:
  - /platform/login  (platform dashboard)
  - /admin/          (Django admin)
  - API key authentication

This backend ONLY authenticates against the PUBLIC schema.
It will never authenticate TenantUser instances.

Usage in settings.py:
    AUTHENTICATION_BACKENDS = [
        'system.account.backends.PlatformAuthBackend',
        'public.userauth.backends.TenantAuthBackend',
    ]
"""

from __future__ import annotations

from django.contrib.auth.backends import BaseBackend
from django.utils import timezone

from system.account.models import PlatformUser, PlatformLoginAuditLog


class PlatformAuthBackend(BaseBackend):
    """
    Authenticates PlatformUser by email + password.

    Enforces:
      - Account must be ACTIVE
      - Account must not be locked
      - Records login audit log on every attempt (success or failure)
      - Increments failed_login_count on failure
      - Locks account after max_attempts failures
    """

    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 30

    def authenticate(self, request, username: str = None, password: str = None,
                     email: str = None, **kwargs):
        """
        Authenticate a platform user.

        Accepts both `username` (Django convention) and `email` as the
        email identifier so it works with Django's built-in login forms.
        """
        print('how are about here')
        login_email = email or username
        if not login_email or not password:
            return None

        ip_address = self._get_ip(request)

        try:
            user = PlatformUser.objects.get(email__iexact=login_email)
        except PlatformUser.DoesNotExist:
            # Record failed attempt with unknown email (no user FK)
            PlatformLoginAuditLog.objects.create(
                user=None,
                attempted_email=login_email,
                result=PlatformLoginAuditLog.LoginResult.FAILED_CREDS,
                ip_address=ip_address,
                user_agent=self._get_user_agent(request),
            )
            return None

        # Check if account can log in
        if not user.can_login:
            result = (
                PlatformLoginAuditLog.LoginResult.LOCKED
                if user.is_locked
                else PlatformLoginAuditLog.LoginResult.SUSPENDED
            )
            PlatformLoginAuditLog.objects.create(
                user=user,
                attempted_email=login_email,
                result=result,
                ip_address=ip_address,
                user_agent=self._get_user_agent(request),
            )
            return None

        # Verify password
        if not user.check_password(password):
            user.record_failed_login(
                max_attempts=self.MAX_FAILED_ATTEMPTS,
                lockout_minutes=self.LOCKOUT_MINUTES,
            )
            PlatformLoginAuditLog.objects.create(
                user=user,
                attempted_email=login_email,
                result=PlatformLoginAuditLog.LoginResult.FAILED_CREDS,
                ip_address=ip_address,
                user_agent=self._get_user_agent(request),
            )
            return None

        # Success
        user.record_login(ip_address=ip_address)
        PlatformLoginAuditLog.objects.create(
            user=user,
            attempted_email=login_email,
            result=PlatformLoginAuditLog.LoginResult.SUCCESS,
            ip_address=ip_address,
            user_agent=self._get_user_agent(request),
        )
        return user

    def get_user(self, user_id):
        """
        Retrieve a PlatformUser by primary key.
        Called by Django's session framework on every request.
        """
        try:
            return PlatformUser.objects.get(pk=user_id, is_active=True)
        except PlatformUser.DoesNotExist:
            return None

    def has_perm(self, user_obj, perm, obj=None):
        """
        Platform admins have all permissions.
        Regular platform users only have permissions granted via PermissionsMixin.
        """
        if not user_obj.is_active or user_obj.is_soft_deleted:
            return False
        if user_obj.is_platform_admin:
            return True
        return super().has_perm(user_obj, perm, obj)

    # ── Helpers ───────────────────────────────────────────────

    @staticmethod
    def _get_ip(request) -> str | None:
        if request is None:
            return None
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    @staticmethod
    def _get_user_agent(request) -> str:
        if request is None:
            return ""
        return request.META.get("HTTP_USER_AGENT", "")
