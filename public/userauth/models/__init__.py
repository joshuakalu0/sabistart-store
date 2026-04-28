"""
public/userauth/models/__init__.py
====================================
APP — userauth (Tenant Schema)

PUBLIC API — import everything from here:

    from public.userauth.models import TenantUser, Customer, StoreStaff, ...

─────────────────────────────────────────────────────────────
COMPLETE MODEL INVENTORY
─────────────────────────────────────────────────────────────

FILE: tenant_user.py — Authentication & Identity  (TENANT schema)
┌──────────────────────────────┬─────────────────────────────────────────────────┐
│ TenantUser                   │ Custom AbstractBaseUser. Email login, 2FA.       │
│                              │ Email unique WITHIN tenant only — same email     │
│                              │ can exist in multiple tenants independently.     │
│                              │ platform_user_id bridges shop owner login.       │
│                              │ user_type: CUSTOMER | STAFF                      │
├──────────────────────────────┼─────────────────────────────────────────────────┤
│ TenantEmailVerificationToken │ Secure 64-byte token, 24hr TTL.                  │
│                              │ Supports VERIFY_EMAIL / CHANGE_EMAIL / REACTIVATE│
├──────────────────────────────┼─────────────────────────────────────────────────┤
│ TenantPasswordResetToken     │ 1hr TTL, one active per user, IP recorded.       │
├──────────────────────────────┼─────────────────────────────────────────────────┤
│ TenantLoginAuditLog          │ Immutable. Every login attempt (pass/fail).      │
│                              │ Includes PLATFORM_OWNER result type.             │
└──────────────────────────────┴─────────────────────────────────────────────────┘

FILE: models_part2.py — Staff, Roles & Permissions  (TENANT schema)
┌──────────────────────────────┬─────────────────────────────────────────────────┐
│ Permission                   │ 42 seeded permission codenames across 12         │
│                              │ categories. is_sensitive flag for critical perms.│
├──────────────────────────────┼─────────────────────────────────────────────────┤
│ Role                         │ Named permission sets. 6 built-in system roles.  │
├──────────────────────────────┼─────────────────────────────────────────────────┤
│ RolePermission               │ Junction: Role ↔ Permission.                    │
├──────────────────────────────┼─────────────────────────────────────────────────┤
│ StoreStaff                   │ TenantUser ↔ store membership. RBAC.            │
│                              │ get_effective_permissions() resolves full set.   │
├──────────────────────────────┼─────────────────────────────────────────────────┤
│ StaffActivityLog             │ Immutable staff action log.                      │
└──────────────────────────────┴─────────────────────────────────────────────────┘

FILE: models_part3.py — Customers  (TENANT schema)
┌──────────────────────────────┬─────────────────────────────────────────────────┐
│ CustomerGroup                │ Manual or automatic customer segments.           │
├──────────────────────────────┼─────────────────────────────────────────────────┤
│ Customer                     │ Tenant-scoped buyer profile. FK to TenantUser.   │
│                              │ Supports guests (user=None). Order stats.        │
├──────────────────────────────┼─────────────────────────────────────────────────┤
│ CustomerAddress              │ Multiple saved addresses per customer.           │
├──────────────────────────────┼─────────────────────────────────────────────────┤
│ CustomerNote                 │ Staff-written notes. Append-only. Pinnable.      │
├──────────────────────────────┼─────────────────────────────────────────────────┤
│ CustomerSession              │ Rich storefront session tracking.                │
├──────────────────────────────┼─────────────────────────────────────────────────┤
│ GuestToken                   │ Anonymous shopper persistence.                   │
└──────────────────────────────┴─────────────────────────────────────────────────┘

─────────────────────────────────────────────────────────────
ARCHITECTURE NOTES
─────────────────────────────────────────────────────────────
1. TenantUser is NOT AUTH_USER_MODEL.
   AUTH_USER_MODEL = "account.PlatformUser" (public schema)
   TenantUser is authenticated via TenantAuthBackend.

2. Email uniqueness is per-tenant only.
   The same email can exist in multiple tenant schemas independently.
   This is enforced by the DB unique constraint within each tenant schema.

3. platform_user_id (CharField, no FK) bridges PlatformUser → TenantUser.
   When a shop owner logs into their own store, a TenantUser is created
   with platform_user_id = str(platform_user.id). No cross-schema FK.

4. All models use app_label = "userauth" so Django routes them to the
   tenant schema via django-tenants.

─────────────────────────────────────────────────────────────
SETTINGS REQUIRED
─────────────────────────────────────────────────────────────
# settings.py
AUTH_USER_MODEL = "account.PlatformUser"

AUTHENTICATION_BACKENDS = [
    'system.account.backends.PlatformAuthBackend',
    'public.userauth.backends.TenantAuthBackend',
]

TENANT_APPS = [
    ...
    'public.userauth',
    ...
]

SHARED_APPS = [
    ...
    'system.account',
    ...
]
"""

# ── Tenant User (Authentication & Identity) ───────────────────────────────────
from .tenant_user import (
    TenantUser,
    TenantUserManager,
    TenantEmailVerificationToken,
    TenantPasswordResetToken,
    TenantLoginAuditLog,
)

# ── Staff, Roles & Permissions ────────────────────────────────────────────────
from .models_part2 import (
    Permission,
    Role,
    RolePermission,
    StoreStaff,
    StaffActivityLog,
)

# ── Customers ─────────────────────────────────────────────────────────────────
from .models_part3 import (
    CustomerGroup,
    Customer,
    CustomerAddress,
    CustomerNote,
    CustomerSession,
    GuestToken,
)

__all__ = [
    # Tenant User
    "TenantUser",
    "TenantUserManager",
    "TenantEmailVerificationToken",
    "TenantPasswordResetToken",
    "TenantLoginAuditLog",
    # Staff & Roles
    "Permission",
    "Role",
    "RolePermission",
    "StoreStaff",
    "StaffActivityLog",
    # Customers
    "CustomerGroup",
    "Customer",
    "CustomerAddress",
    "CustomerNote",
    "CustomerSession",
    "GuestToken",
]
