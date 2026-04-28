# Migration Strategy — Multi-Tenant Auth Refactoring

## Overview

This document describes the steps to migrate from the old broken authentication
setup to the new enterprise-grade dual-user-model architecture.

## What Changed

### Before (Broken)

```
system/account/models.py     → Owner model wrapping Django's AuthUser (OneToOne)
public/userauth/models/      → User model wrapping Django's AuthUser (OneToOne)
settings.py                  → No AUTH_USER_MODEL (using Django's default User)
settings.py                  → AUTHENTICALTION_BACKENDS (typo — never worked)
system/account/admin.py      → Importing 'Tenant' model that doesn't exist
system/account/signals.py    → Importing 'Tenant' model that doesn't exist
Customer.user                → FK to User in tenant schema (cross-schema issue)
AuditModel                   → FK to django.contrib.auth.models.User (wrong)
```

### After (Fixed)

```
system/account/models.py     → PlatformUser (AbstractBaseUser) — public schema
public/userauth/models/      → TenantUser (AbstractBaseUser) — tenant schema
settings.py                  → AUTH_USER_MODEL = "account.PlatformUser"
settings.py                  → AUTHENTICATION_BACKENDS = [Platform..., Tenant...]
system/account/admin.py      → Correct PlatformUser admin
system/account/signals.py    → Correct PlatformUser signal
Customer.user                → FK to TenantUser (same tenant schema — safe)
AuditModel                   → FK to settings.AUTH_USER_MODEL (correct)
```

---

## Migration Steps (Fresh Database)

If you're starting fresh (no existing data), follow these steps:

```bash
# 1. Delete all existing migrations (they reference old models)
find . -path "*/migrations/0*.py" -delete

# 2. Create fresh migrations for shared apps (public schema)
python manage.py makemigrations system.account
python manage.py makemigrations system.core
python manage.py makemigrations system.theme_marketplace

# 3. Create fresh migrations for tenant apps
python manage.py makemigrations public.userauth
python manage.py makemigrations public.store_settings
python manage.py makemigrations public.category
python manage.py makemigrations public.product
python manage.py makemigrations dashboard.settings
python manage.py makemigrations dashboard.categories_settings
python manage.py makemigrations dashboard.pricing
python manage.py makemigrations dashboard.product_settings
python manage.py makemigrations dashboard.theme_manager

# 4. Apply migrations to public schema
python manage.py migrate_schemas --shared

# 5. Create the public tenant (required by django-tenants)
python manage.py shell
>>> from django_tenants.utils import schema_context
>>> from system.core.models import Shop, Domain
>>> with schema_context('public'):
...     public_tenant = Shop(schema_name='public', name='Public',owner='c6338f39-ea46-41d9-a1a4-2685c1ac737e')
...     public_tenant.save()
...     domain = Domain(domain='localhost', tenant=public_tenant, is_primary=True)
...     domain.save()

with schema_context('public'):
    public_tenant = Shop(schema_name='public', name='Public',owner='c6338f39-ea46-41d9-a1a4-2685c1ac737e')
    public_tenant.save()
    domain = Domain(domain='localhost', tenant=public_tenant, is_primary=True)
    domain.save()
with schema_context('public'):
    public_tenant = Shop(schema_name='public', name='Public',owner=user)
    public_tenant.save()
    domain = Domain(domain='localhost', tenant=public_tenant, is_primary=True)
    domain.save()

# 6. Create a superuser (PlatformUser)
python manage.py createsuperuser
# Enter email, first_name, last_name, password

# 7. Create a test tenant
python manage.py shell
>>> from system.account.models import PlatformUser
>>> from system.core.models import Shop, Domain
>>> owner = PlatformUser.objects.get(email='your@email.com')
>>> shop = Shop(schema_name='shop1', name='Test Shop', owner=owner)
>>> shop.save()  # auto_create_schema=True will create the schema
>>> domain = Domain(domain='shop1.localhost', tenant=shop, is_primary=True)
>>> domain.save()

# 8. Apply migrations to all tenant schemas
python manage.py migrate_schemas --tenant
```

---

## Migration Steps (Existing Database with Data)

⚠️ WARNING: This is a breaking change. The old User model is being replaced.
If you have existing data, you need a data migration.

```bash
# 1. Back up your database FIRST
pg_dump sabistore > backup_$(date +%Y%m%d).sql

# 2. Create a data migration to copy old User data to PlatformUser
# (Write this manually based on your existing data)

# 3. Follow the fresh database steps above, but add data migrations
# between steps 2 and 4.
```

---

## Key Architecture Rules

### Rule 1: Never create cross-schema foreign keys

```python
# ❌ WRONG — FK from tenant schema to public schema
class Customer(models.Model):
    user = models.ForeignKey('public.userauth.User', ...)  # BREAKS migrations

# ✅ CORRECT — FK within same schema
class Customer(models.Model):
    user = models.ForeignKey(TenantUser, ...)  # Same tenant schema — safe

# ✅ CORRECT — Store ID without FK constraint
class TenantUser(models.Model):
    platform_user_id = models.CharField(max_length=36, blank=True)  # No FK
```

### Rule 2: AUTH_USER_MODEL must be in SHARED_APPS

```python
# settings.py
AUTH_USER_MODEL = "account.PlatformUser"  # Must be in SHARED_APPS

SHARED_APPS = [
    'system.account',  # Contains PlatformUser — AUTH_USER_MODEL
    ...
]
```

### Rule 3: AuditModel must use settings.AUTH_USER_MODEL

```python
# ❌ WRONG
from django.contrib.auth.models import User
created_by = models.ForeignKey(User, ...)

# ✅ CORRECT
from django.conf import settings
created_by = models.ForeignKey(settings.AUTH_USER_MODEL, ...)
```

### Rule 4: TenantUser is NOT AUTH_USER_MODEL

```python
# TenantUser is authenticated via TenantAuthBackend
# It does NOT need to be AUTH_USER_MODEL
# Django sessions store the user's PK — for tenant users, this is their TenantUser UUID
# The session backend must be configured to use the correct schema
```

---

## Common Issues & Solutions

### Issue: "relation 'platform_users' does not exist"

**Cause**: Migrations haven't been applied to the public schema.
**Fix**: `python manage.py migrate_schemas --shared`

### Issue: "relation 'tenant_users' does not exist"

**Cause**: Migrations haven't been applied to the tenant schema.
**Fix**: `python manage.py migrate_schemas --tenant`

### Issue: "AUTH_USER_MODEL refers to model 'account.PlatformUser' that has not been installed"

**Cause**: `system.account` is not in `SHARED_APPS`.
**Fix**: Add `'system.account'` to `SHARED_APPS` in settings.py.

### Issue: "Cannot use a string that resolves to an abstract model for ForeignKey"

**Cause**: Using `settings.AUTH_USER_MODEL` in a model that's in TENANT_APPS.
**Fix**: In tenant apps, use `TenantUser` directly (same schema FK is safe).

### Issue: Login works on platform but not on tenant storefront

**Cause**: `TenantAuthBackend` is not in `AUTHENTICATION_BACKENDS`.
**Fix**: Add `'public.userauth.backends.TenantAuthBackend'` to `AUTHENTICATION_BACKENDS`.

### Issue: Shop owner can't log into their own tenant dashboard

**Cause**: The platform owner bridge in `TenantAuthBackend` requires the Shop to have
the correct `schema_name` matching the current tenant.
**Fix**: Ensure `Shop.schema_name` matches the subdomain being accessed.
