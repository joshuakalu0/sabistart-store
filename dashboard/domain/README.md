# domains/ — Custom Domain Management App
# Phase 1: Foundation
# ═══════════════════════════════════════════════════════

## Files in this package

| File                  | Purpose                                                      |
|-----------------------|--------------------------------------------------------------|
| models.py             | All 12 models covering the full domain lifecycle             |
| admin.py              | Django admin with badges, inlines, and bulk actions          |
| signals.py            | Auto event logging, cache invalidation, SSL trigger          |
| apps.py               | AppConfig — registers signals on startup                     |
| middleware.py         | 3-layer resolution: Redis → DB cache → Full lookup           |
| settings_snippet.py   | Paste these settings into your main settings.py              |

## Setup Steps

1. Copy this `domains/` folder into your Django project root.

2. Add to INSTALLED_APPS in settings.py:
       'domains',

3. Replace your existing tenant middleware in MIDDLEWARE:
       'domains.middleware.CustomDomainMiddleware',   # must be FIRST

4. Paste the contents of settings_snippet.py into your settings.py.

5. Run migrations:
       python manage.py makemigrations domains
       python manage.py migrate

6. Install dependencies:
       pip install django-redis celery

## How it works

When a tenant adds a custom domain (e.g. mycoolbrand.com):

  1. A CustomDomain row is created (status=PENDING)
  2. Signals auto-generate DNS records the tenant must add:
       - Root domain:  A @ → SERVER_IP, A www → SERVER_IP, TXT _platform-verify → token
       - Subdomain:    CNAME shop → PLATFORM_CNAME,       TXT _platform-verify → token
  3. Tenant adds records at their registrar (Namecheap, GoDaddy, etc.)
  4. Celery polls DNS every 60s until TXT + A records are detected
  5. On verification: status → DNS_VERIFIED → SSL auto-provisioned
  6. On SSL active: status → ACTIVE → Nginx config updated
  7. All traffic to mycoolbrand.com now routed to the correct tenant

## Next Phases

  Phase 2: Domain management API views + tenant dashboard UI
  Phase 3: Celery verification worker (DNS polling)
  Phase 4: Let's Encrypt SSL automation
  Phase 5: Nginx config automation
  Phase 6: Health checks & monitoring
  Phase 7: Security hardening & quota enforcement
