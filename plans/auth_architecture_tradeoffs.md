# Multi-Tenant Authentication Architecture — Trade-Off Analysis

## Current Critical Issues (Must Fix Regardless)

| Issue                                                                                 | File                                     | Severity                                  |
| ------------------------------------------------------------------------------------- | ---------------------------------------- | ----------------------------------------- |
| Missing `AUTH_USER_MODEL`                                                             | `settings.py`                            | CRITICAL — Django won't start correctly   |
| Typo `AUTHENTICALTION_BACKENDS`                                                       | `settings.py`                            | CRITICAL — auth backends silently ignored |
| Import `from system.account.models import Tenant` (model doesn't exist)               | `system/account/admin.py`                | CRITICAL — server crash on startup        |
| Import `from system.account.models import Tenant` (model doesn't exist)               | `system/account/signals.py`              | CRITICAL — signals fail silently          |
| `Customer.user` FK points to `User` in tenant schema (cross-schema FK)                | `public/userauth/models/models_part3.py` | HIGH — migration failures                 |
| `User` model wraps Django's `AuthUser` via OneToOneField (double-user anti-pattern)   | `public/userauth/models/models_part1.py` | HIGH — complexity, migration issues       |
| `AuditModel` in `dashboard/settings/models.py` uses `django.contrib.auth.models.User` | `dashboard/settings/models.py`           | HIGH — wrong user model referenced        |

---

## Decision 1: PlatformUser Access to Tenant Dashboards

### Option A — PlatformUsers ONLY manage from public platform (Strict Separation)

```
PlatformUser → manages → Shop (tenant) → via platform dashboard only
TenantUser   → logs into → tenant storefront/dashboard
```

**Pros:**

- Cleanest architecture — zero coupling between layers
- Easiest to reason about security boundaries
- No risk of platform admin accidentally acting as a tenant user
- Simplest to implement and maintain

**Cons:**

- If a shop owner wants to test their own store as a customer, they need a separate TenantUser account
- Support staff can't impersonate tenant users for debugging

**Best for:** Platforms where shop owners primarily manage via a separate admin panel (like Shopify's partner dashboard)

---

### Option B — PlatformUsers can access their own tenant dashboards

```
PlatformUser → owns → Shop → can log into tenant dashboard as "Owner" role
TenantUser   → logs into → tenant storefront/dashboard
```

**Pros:**

- Shop owners can manage their store directly from the tenant dashboard
- More intuitive UX — one login to rule their store

**Cons:**

- Requires a "bridge" mechanism — PlatformUser identity must be recognized in tenant schema
- Can't use a simple FK (cross-schema) — must use a "platform_user_id" integer field (no FK constraint)
- More complex authentication backend logic

**Best for:** Platforms where shop owners are also the primary store managers (like WooCommerce)

---

### Option C — PlatformUsers can access ALL tenants (Super Admin)

```x
PlatformUser (is_platform_admin=True) → can impersonate any tenant user
```

**Pros:**

- Useful for support/debugging
- Platform admins can fix issues in any tenant

**Cons:**

- Security risk — one compromised platform admin = all tenants exposed
- Complex audit trail requirements
- Requires careful permission scoping

**Best for:** Internal support teams, not recommended as default

---

## Decision 2: Cross-Role Users (Same Person as PlatformUser AND TenantUser)

### Option A — Completely Separate (No Linking)

```
john@gmail.com as PlatformUser → owns Shop A
john@gmail.com as TenantUser in Shop B → is a customer
```

These are treated as COMPLETELY different people. Same email, different systems.

**Pros:**

- True isolation — no shared state between platform and tenant layers
- Simplest mental model
- No risk of privilege escalation
- Easiest migrations

**Cons:**

- If John owns Shop A and wants to buy from Shop B, he needs two separate accounts
- No way to "link" accounts later without a migration

**Best for:** Platforms where shop owners and customers are distinct populations

---

### Option B — Allow Linking (Optional Account Bridge)

```
PlatformUser (john@gmail.com) ←→ TenantUser (john@gmail.com in Shop B)
                                   linked via platform_user_id (no FK)
```

**Pros:**

- Better UX — one person, multiple roles
- Can show "you also own a shop" prompts
- Useful for analytics (same person across contexts)

**Cons:**

- More complex — need to handle the case where linking fails
- `platform_user_id` stored in tenant schema as a plain integer (no FK constraint due to cross-schema)
- Risk of data leakage if not carefully scoped

**Best for:** Platforms where the same person might be both a merchant and a buyer

---

## Decision 3: Tenant Identification During Login

### Option A — Subdomain-Based (Recommended for Production)

```
shop1.yourplatform.com/login → knows tenant = shop1 from URL
shop2.yourplatform.com/login → knows tenant = shop2 from URL
```

**Pros:**

- Clean UX — user just goes to their store URL
- Tenant is always known before login attempt
- No ambiguity — `john@gmail.com` in shop1 is different from shop2
- Standard approach (Shopify, Slack, etc.)
- Works perfectly with `django-tenants` middleware

**Cons:**

- Requires proper DNS/subdomain setup
- Custom domains need extra configuration

---

### Option B — Email-Based Tenant Selection

```
yourplatform.com/login → user enters email → system finds all tenants → user selects
```

**Pros:**

- Works without subdomain setup
- Good for development/testing

**Cons:**

- Reveals which tenants a user belongs to (privacy concern)
- Extra round-trip in login flow
- More complex backend logic

---

### Option C — Both (Subdomain preferred, fallback to selection)

**Pros:** Maximum flexibility
**Cons:** Most complex to implement and maintain

---

## Recommended Architecture (My Recommendation)

Based on enterprise best practices and the django-tenants architecture:

```
Decision 1: Option B — PlatformUsers can access their OWN tenant dashboards
            (they own the shop, they should be able to manage it directly)

Decision 2: Option A — Completely Separate (No Linking)
            (cleanest architecture, easiest to scale, no cross-contamination)

Decision 3: Option A — Subdomain-Based
            (standard for multi-tenant SaaS, works perfectly with django-tenants)
```

### Why this combination works best:

1. **PlatformUser logs into platform** → manages subscriptions, billing, creates shops
2. **PlatformUser logs into their tenant dashboard** → manages products, orders, staff
   - Recognized via `platform_user_id` stored in tenant schema (no FK)
   - Gets "Owner" role automatically in their own tenant
3. **TenantUser logs into storefront** → shops, manages their account
   - Completely isolated per tenant
   - Same email can exist in multiple tenants independently

---

## Architecture Diagram

```
PUBLIC SCHEMA
┌─────────────────────────────────────────────────────────┐
│  PlatformUser (AbstractBaseUser)                        │
│  - email (unique across platform)                       │
│  - password                                             │
│  - is_platform_admin                                    │
│  - 2FA, OAuth, API keys                                 │
│                                                         │
│  Shop (TenantMixin)                                     │
│  - owner → PlatformUser                                 │
│  - schema_name                                          │
│                                                         │
│  Domain (DomainMixin)                                   │
└─────────────────────────────────────────────────────────┘

TENANT SCHEMA (per shop — completely isolated)
┌─────────────────────────────────────────────────────────┐
│  TenantUser (AbstractBaseUser)                          │
│  - email (unique WITHIN this tenant only)               │
│  - password                                             │
│  - user_type: CUSTOMER | STAFF                          │
│  - platform_user_id (int, nullable, NO FK CONSTRAINT)   │
│    └── links to PlatformUser if shop owner logs in      │
│                                                         │
│  Customer (profile for TenantUser with CUSTOMER type)   │
│  StoreStaff (profile for TenantUser with STAFF type)    │
│  Role, Permission (tenant-specific RBAC)                │
└─────────────────────────────────────────────────────────┘

AUTHENTICATION BACKENDS
┌─────────────────────────────────────────────────────────┐
│  PlatformAuthBackend                                    │
│  - Authenticates against PUBLIC schema PlatformUser     │
│  - Used for: /platform/login, /admin/                   │
│                                                         │
│  TenantAuthBackend                                      │
│  - Authenticates against CURRENT TENANT schema          │
│  - Used for: shop1.platform.com/login                   │
│  - Falls back to PlatformUser check (for shop owners)   │
└─────────────────────────────────────────────────────────┘
```

---

## Files That Will Be Created/Modified

### New Files

| File                                    | Purpose                                            |
| --------------------------------------- | -------------------------------------------------- |
| `system/account/models.py`              | PlatformUser (AbstractBaseUser) — complete rewrite |
| `system/account/backends.py`            | PlatformAuthBackend                                |
| `system/account/managers.py`            | PlatformUserManager                                |
| `public/userauth/models/tenant_user.py` | TenantUser (AbstractBaseUser)                      |
| `public/userauth/backends.py`           | TenantAuthBackend                                  |
| `public/userauth/managers.py`           | TenantUserManager                                  |

### Modified Files

| File                                     | Change                                             |
| ---------------------------------------- | -------------------------------------------------- |
| `sabistart_store/settings.py`            | Add `AUTH_USER_MODEL`, fix typo, add both backends |
| `system/account/admin.py`                | Fix broken import                                  |
| `system/account/signals.py`              | Fix broken import                                  |
| `public/userauth/models/models_part2.py` | Remove `User` FK, use `TenantUser`                 |
| `public/userauth/models/models_part3.py` | Change `Customer.user` to `TenantUser`             |
| `dashboard/settings/models.py`           | Fix `AuditModel` to use `settings.AUTH_USER_MODEL` |

### Deleted/Replaced

| File                                     | Reason                                   |
| ---------------------------------------- | ---------------------------------------- |
| `public/userauth/models/models_part1.py` | Replaced by `tenant_user.py`             |
| `system/core/backend.py`                 | Replaced by `system/account/backends.py` |
