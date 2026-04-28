"""
public/userauth/backends.py
============================
Tenant-Level Authentication Backend — TENANT SCHEMA

Authenticates TenantUser instances within the current tenant's schema.
Used for:
  - shop1.yourplatform.com/login  (storefront login)
  - shop1.yourplatform.com/dashboard/login  (tenant dashboard login)

This backend ONLY authenticates against the CURRENT TENANT schema.
It also handles the "platform owner bridge" — when a PlatformUser (shop owner)
logs into their own tenant dashboard, this backend creates or retrieves a
TenantUser record linked via platform_user_id.

Authentication flow:
  1. Request arrives at shop1.yourplatform.com/login
  2. django-tenants middleware sets connection to shop1's schema
  3. TenantAuthBackend.authenticate() runs against shop1's TenantUser table
  4. If email matches a TenantUser → authenticate normally
  5. If no TenantUser found → check if email matches a PlatformUser who owns this shop
     → if yes, create/retrieve a TenantUser with platform_user_id set
     → authenticate as that TenantUser with STAFF role

Usage in settings.py:
    AUTHENTICATION_BACKENDS = [
        'system.account.backends.PlatformAuthBackend',
        'public.userauth.backends.TenantAuthBackend',
    ]
"""

from __future__ import annotations

from django.contrib.auth.backends import BaseBackend
from django.utils import timezone

from public.userauth.models.tenant_user import TenantUser, TenantLoginAuditLog


class TenantAuthBackend(BaseBackend):
    """
    Authenticates TenantUser by email + password within the current tenant schema.

    Also handles the platform owner bridge:
    When a PlatformUser (shop owner) logs into their own tenant dashboard,
    this backend verifies their credentials against the PUBLIC schema PlatformUser,
    then creates/retrieves a TenantUser record linked via platform_user_id.

    Enforces:
      - Account must be ACTIVE
      - Account must not be locked
      - Records login audit log on every attempt
      - Increments failed_login_count on failure
      - Locks account after max_attempts failures
    """

    MAX_FAILED_ATTEMPTS = 5
    LOCKOUT_MINUTES = 30

    def authenticate(self, request, username: str = None, password: str = None,
                     email: str = None, **kwargs):
        """
        Authenticate a tenant user.

        Accepts both `username` (Django convention) and `email` as the
        email identifier.

        Falls back to platform owner bridge if no TenantUser found.
        """
        print('we are here ')
        login_email = email or username
        if not login_email or not password:
            return None

        ip_address = self._get_ip(request)
        user_agent = self._get_user_agent(request)

        # ── Step 1: Try to find a TenantUser in the current schema ────────
        try:
            print('this is the user', login_email, TenantUser.objects.all())
            tenant_user = TenantUser.objects.get(email=login_email)
            print(tenant_user, 'this is the user')
            return self._authenticate_tenant_user(
                tenant_user, password, login_email, ip_address, user_agent
            )
        except TenantUser.DoesNotExist as e:
            print(e, '+++++++++')
            pass

        # ── Step 2: Platform owner bridge ─────────────────────────────────
        # Check if this email belongs to a PlatformUser who owns the current shop.
        # This allows shop owners to log into their own tenant dashboard.
        platform_user = self._get_platform_owner_for_current_tenant(
            login_email)
        if platform_user is not None:
            if platform_user.check_password(password) and platform_user.can_login:
                tenant_user = self._get_or_create_owner_tenant_user(
                    platform_user)
                tenant_user.record_login(ip_address=ip_address)
                TenantLoginAuditLog.objects.create(
                    user=tenant_user,
                    attempted_email=login_email,
                    result=TenantLoginAuditLog.LoginResult.PLATFORM_OWNER,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    metadata={"platform_user_id": str(platform_user.id)},
                )
                return tenant_user

        # ── Step 3: No match found ─────────────────────────────────────────
        TenantLoginAuditLog.objects.create(
            user=None,
            attempted_email=login_email,
            result=TenantLoginAuditLog.LoginResult.FAILED_CREDS,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return None

    def get_user(self, user_id):
        """
        Retrieve a TenantUser by primary key.
        Called by Django's session framework on every request.
        """
        # print(user_id, '===================', TenantUser.objects.all())
        try:
            return TenantUser.objects.get(pk=user_id, is_active=True)
        except TenantUser.DoesNotExist:
            return None

    # ── Internal helpers ──────────────────────────────────────────────────

    def _authenticate_tenant_user(
        self,
        user: TenantUser,
        password: str,
        login_email: str,
        ip_address: str,
        user_agent: str,
    ) -> TenantUser | None:
        """Authenticate an existing TenantUser record."""

        # Check if account can log in
        if not user.can_login:
            result = (
                TenantLoginAuditLog.LoginResult.LOCKED
                if user.is_locked
                else TenantLoginAuditLog.LoginResult.SUSPENDED
            )
            TenantLoginAuditLog.objects.create(
                user=user,
                attempted_email=login_email,
                result=result,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return None

        # Verify password
        if not user.check_password(password):
            user.record_failed_login(
                max_attempts=self.MAX_FAILED_ATTEMPTS,
                lockout_minutes=self.LOCKOUT_MINUTES,
            )
            TenantLoginAuditLog.objects.create(
                user=user,
                attempted_email=login_email,
                result=TenantLoginAuditLog.LoginResult.FAILED_CREDS,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return None

        # Success
        user.record_login(ip_address=ip_address)
        TenantLoginAuditLog.objects.create(
            user=user,
            attempted_email=login_email,
            result=TenantLoginAuditLog.LoginResult.SUCCESS,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return user

    def _get_platform_owner_for_current_tenant(self, email: str):
        """
        Check if the given email belongs to a PlatformUser who owns the
        current tenant (shop). Returns the PlatformUser if found, else None.

        This is the cross-schema bridge — we import PlatformUser here and
        query the public schema. This is safe because we're reading from
        public schema, not writing cross-schema FKs.
        """
        try:
            from system.account.models import PlatformUser
            from django_tenants.utils import get_current_schema_name
            from django.db import connection

            # Get the current tenant's schema name
            current_schema = get_current_schema_name()
            if current_schema == "public":
                # Don't apply platform bridge on the public schema itself
                return None

            # Find the PlatformUser with this email
            platform_user = PlatformUser.objects.get(email__iexact=email)

            # Verify this PlatformUser owns the current tenant
            # We check via the Shop model in the public schema
            from system.core.models import Shop
            owns_current_shop = Shop.objects.filter(
                owner=platform_user,
                schema_name=current_schema,
            ).exists()

            if owns_current_shop:
                return platform_user

        except Exception:
            # Any import error, DoesNotExist, etc. — fail silently
            pass

        return None

    def _get_or_create_owner_tenant_user(self, platform_user) -> TenantUser:
        """
        Get or create a TenantUser record for a PlatformUser (shop owner).

        The TenantUser is linked via platform_user_id (no FK constraint).
        The user gets STAFF type and is_staff=True so they can access the
        tenant dashboard.
        """
        platform_user_id_str = str(platform_user.id)

        tenant_user, created = TenantUser.objects.get_or_create(
            platform_user_id=platform_user_id_str,
            defaults={
                "email":          platform_user.email,
                "first_name":     platform_user.first_name,
                "last_name":      platform_user.last_name,
                "user_type":      TenantUser.UserType.STAFF,
                "account_status": TenantUser.AccountStatus.ACTIVE,
                "is_verified":    True,
                "is_staff":       True,
                "is_active":      True,
            },
        )

        if not created:
            # Sync name/email changes from PlatformUser
            updated = False
            if tenant_user.email != platform_user.email:
                tenant_user.email = platform_user.email
                updated = True
            if tenant_user.first_name != platform_user.first_name:
                tenant_user.first_name = platform_user.first_name
                updated = True
            if tenant_user.last_name != platform_user.last_name:
                tenant_user.last_name = platform_user.last_name
                updated = True
            if updated:
                tenant_user.save(
                    update_fields=["email", "first_name", "last_name"])

        return tenant_user

    # ── Request helpers ───────────────────────────────────────

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
