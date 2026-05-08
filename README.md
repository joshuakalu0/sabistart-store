# SabiStart Store Backend

This repository is a Django multi-tenant commerce platform built on:

- `Django 5`
- `django-tenants`
- PostgreSQL schemas
- tenant storefront + dashboard routing
- optional Vercel Blob media storage on Vercel

## Environment Variables

The app reads its environment mainly from [settings.py](C:/Users/user/Desktop/build/backend/sabistart-store/sabistart_store/settings.py) and, for Vercel media, [storage_backends.py](C:/Users/user/Desktop/build/backend/sabistart-store/sabistart_store/storage_backends.py).

Two env files are now in the repo root:

- [`.env.example`](C:/Users/user/Desktop/build/backend/sabistart-store/.env.example)
- [`.env`](C:/Users/user/Desktop/build/backend/sabistart-store/.env)

Use `.env.example` as the tracked template and keep real secrets in `.env` or in your hosting provider's environment settings.

The app now auto-loads `.env` and `.env.local` through [env.py](C:/Users/user/Desktop/build/backend/sabistart-store/sabistart_store/env.py) for `manage.py`, WSGI, ASGI, and Passenger startup.

## Quick Start

1. Copy values from [`.env.example`](C:/Users/user/Desktop/build/backend/sabistart-store/.env.example) into your real env.
2. Replace all placeholder values.
3. For local development, keep `DJANGO_DEBUG=True`.
4. For production, set `DJANGO_DEBUG=False` and use real domains in `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`.

## What Each Variable Does

### Core Django

`DJANGO_SECRET_KEY`
- What it does: cryptographic signing key for sessions, CSRF, password reset tokens, and other Django security internals.
- Effect on system: if weak or leaked, account/session security is compromised.
- Where to get it: generate it yourself.
- Good way to generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- Required: yes in any real deployment.

`DJANGO_DEBUG`
- What it does: toggles Django debug mode.
- Effect on system: when `True`, Django exposes debug pages and relaxed defaults. This is not safe for production.
- Where to get it: you set it manually.
- Typical values: `True` locally, `False` in staging/production.

`DJANGO_ALLOWED_HOSTS`
- What it does: list of hostnames the app is allowed to serve.
- Effect on system: wrong values cause `DisallowedHost` errors or unsafe host handling.
- Where to get it: your real domains, subdomains, preview domains, localhost names.
- Example: `example.com,www.example.com,shop.example.com`

`DJANGO_CSRF_TRUSTED_ORIGINS`
- What it does: list of trusted origins for cross-site request forgery validation.
- Effect on system: if missing in HTTPS deployments, forms/login/posts can fail with CSRF errors.
- Where to get it: your public HTTPS origins.
- Example: `https://example.com,https://www.example.com`

`DJANGO_LANGUAGE_CODE`
- What it does: default Django language code.
- Effect on system: influences translations and formatting defaults.
- Where to get it: your app preference.
- Default: `en-us`

`DJANGO_TIME_ZONE`
- What it does: default timezone for Django.
- Effect on system: affects timestamps, reports, scheduling, and display defaults.
- Where to get it: your business timezone choice.
- Default: `UTC`

### Database

`DATABASE_URL`
- What it does: full PostgreSQL connection string.
- Effect on system: this is the preferred database input. If set, it overrides the manual `DB_*` field set.
- Where to get it: Vercel Postgres, Neon, Railway, Supabase, Render, self-hosted Postgres, or any PostgreSQL provider.
- Example: `postgres://user:password@host:5432/dbname`

If you already have a Neon connection string, this is the field that should be active.

`DATABASE_URL_UNPOOLED`
- What it does: optional direct, non-pooled database URL used automatically for migration commands.
- Effect on system: when you run `migrate`, `migrate_schemas`, `showmigrations`, or `sqlmigrate`, the app will prefer this URL over the pooled one.
- Where to get it: from your database provider's direct connection string. On Neon, this is the endpoint without `-pooler` in the hostname.
- Why it matters here: this project uses `django-tenants`, and Neon pooled connections can fail during schema-changing migration flows with errors like `cursor already closed`.

`POSTGRES_URL`
- What it does: alternative full database URL name.
- Effect on system: used if `DATABASE_URL` is absent.
- Where to get it: some providers expose this automatically.

`POSTGRES_PRISMA_URL`
- What it does: another accepted database URL input.
- Effect on system: used if `DATABASE_URL` and `POSTGRES_URL` are absent.
- Where to get it: some platforms expose this naming convention.

`DB_ENGINE`
- What it does: manual database backend engine.
- Effect on system: should remain `django_tenants.postgresql_backend` for this project.
- Where to get it: usually you do not need to change it.

`DB_NAME`
- What it does: database name when not using `DATABASE_URL`.
- Effect on system: tells Django which PostgreSQL database to connect to.
- Where to get it: your database provider or cPanel/Postgres admin panel.

`DB_USER`
- What it does: database username.
- Effect on system: authentication for the PostgreSQL connection.
- Where to get it: your database provider/admin panel.

`DB_PASSWORD`
- What it does: database password.
- Effect on system: authentication for the PostgreSQL connection.
- Where to get it: your database provider/admin panel.

`DB_HOST`
- What it does: database hostname.
- Effect on system: target PostgreSQL server address.
- Where to get it: your database provider/admin panel.

`DB_PORT`
- What it does: database port.
- Effect on system: connection port for PostgreSQL.
- Where to get it: your database provider.
- Default: `5432`

`DB_CONN_MAX_AGE`
- What it does: database connection reuse lifetime in seconds.
- Effect on system: helps performance by reusing DB connections.
- Where to get it: you set it manually.
- Typical value: `60`

`DB_SSLMODE`
- What it does: PostgreSQL SSL mode.
- Effect on system: required by some managed Postgres services.
- Where to get it: your provider’s docs.
- Common values: `require`, `prefer`

### Static Files, Uploads, and Storage

`DJANGO_STATIC_ROOT`
- What it does: filesystem path where `collectstatic` writes static assets.
- Effect on system: required for deployments that collect and serve static files from disk.
- Where to get it: your server/deployment path design.
- Example on cPanel: `/home/username/sabistart-store/staticfiles`

`DJANGO_STATIC_URL`
- What it does: base URL for static assets.
- Effect on system: controls where CSS/JS/theme static files are referenced.
- Default: `/static/`

`DJANGO_MEDIA_ROOT`
- What it does: filesystem path for media uploads when using filesystem storage.
- Effect on system: required on non-Vercel filesystem deployments.
- Where to get it: your server path design.

`DJANGO_MEDIA_URL`
- What it does: base URL for media uploads.
- Effect on system: controls upload URLs for product images, logos, blog images, theme assets, and similar files.
- Default: `/media/`

`DJANGO_DEFAULT_FILE_STORAGE`
- What it does: explicit override of the default Django storage backend.
- Effect on system: lets you force a storage backend manually.
- Where to get it: you only set this if you intentionally want a specific backend.
- Typical use:
  - leave empty on local/cPanel and the app uses tenant filesystem storage
  - leave empty on Vercel and the app auto-selects Vercel Blob storage

`BLOB_READ_WRITE_TOKEN`
- What it does: Vercel Blob read/write token.
- Effect on system: required for persistent uploads on Vercel.
- Where to get it: Vercel Blob project/storage settings.
- Required: yes on Vercel if you want uploads to work.

`VERCEL_BLOB_ACCESS`
- What it does: default access mode for uploaded blobs.
- Effect on system: influences how stored media is managed in Blob.
- Where to get it: you set it manually.
- Typical value: `private`

`VERCEL_BLOB_CACHE_MAX_AGE`
- What it does: cache max age for Blob-backed media responses.
- Effect on system: changes browser/CDN caching behavior for uploads.
- Where to get it: you set it manually.
- Typical value: `31536000`

`VERCEL_BLOB_ALLOW_OVERWRITE`
- What it does: allows overwriting files with the same blob path.
- Effect on system: controls whether repeated saves replace existing media objects.
- Where to get it: you set it manually.
- Typical value: `True`

### Multi-Tenant Domain Routing

`PLATFORM_CNAME`
- What it does: canonical platform domain or CNAME target used by the domain system and tenant routing guidance.
- Effect on system: affects domain onboarding, verification guidance, and generated tenant URLs.
- Where to get it: your main platform domain decision.
- Examples:
  - `sabistart.com`
  - `stores.example.com`
`SUBDOMAIN_SUFFIX`
- What it does: suffix used when generating tenant subdomains.
- Effect on system: affects how account onboarding and subdomain URLs are formed.
- Where to get it: your platform domain strategy.
- Examples:
  - `.sabistart.com`
  - `.stores.example.com`
  - empty if you do not want automatic suffixing

`SERVER_IP`
- What it does: public server IP used by domain verification/documentation flows.
- Effect on system: helps users point root domains correctly.
- Where to get it:
  - your VPS public IP
  - your load balancer public IP
  - or leave local default for development

`DOMAIN_RESOLUTION_CACHE_TTL`
- What it does: cache duration for domain resolution lookups.
- Effect on system: affects how quickly tenant-domain changes are reflected versus how much DB/domain lookup traffic the app generates.
- Where to get it: you set it manually.
- Typical value: `300`

`DOMAIN_SIMULATE_INFRA`
- What it does: simulates domain infrastructure behavior in development.
- Effect on system: useful locally, but should be disabled in real production.
- Where to get it: you set it manually.
- Typical values:
  - `True` locally
  - `False` in production

### Proxy, HTTPS, and Security

`DJANGO_USE_X_FORWARDED_HOST`
- What it does: trust `X-Forwarded-Host` headers from your proxy.
- Effect on system: important behind Vercel, Nginx, cPanel proxying, or load balancers.
- Typical value: `True` in production behind a proxy.

`DJANGO_USE_X_FORWARDED_PORT`
- What it does: trust forwarded port headers.
- Effect on system: helps Django build correct absolute URLs behind proxies.

`DJANGO_TRUST_X_FORWARDED_PROTO`
- What it does: enables `SECURE_PROXY_SSL_HEADER`.
- Effect on system: lets Django understand that the original request was HTTPS even if the upstream proxy talks plain HTTP to Python.
- Typical value: `True` in production behind a proxy.

`DJANGO_SECURE_SSL_REDIRECT`
- What it does: force redirect HTTP to HTTPS.
- Effect on system: important for production security.
- Typical values:
  - `False` locally
  - `True` in production

`DJANGO_SESSION_COOKIE_SECURE`
- What it does: marks session cookies HTTPS-only.
- Effect on system: session cookies won’t be sent over plain HTTP.

`DJANGO_CSRF_COOKIE_SECURE`
- What it does: marks CSRF cookies HTTPS-only.
- Effect on system: improves CSRF token transport security.

`DJANGO_SECURE_HSTS_SECONDS`
- What it does: HSTS duration.
- Effect on system: tells browsers to prefer HTTPS for your domain for a period of time.
- Typical production value: `31536000`

`DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS`
- What it does: extend HSTS to subdomains.
- Effect on system: affects all subdomains, which matters in a tenant/subdomain platform.

`DJANGO_SECURE_HSTS_PRELOAD`
- What it does: signals preload intent for browsers that support HSTS preload lists.
- Effect on system: stronger HTTPS posture, but only use when you are fully committed to HTTPS everywhere.

`DJANGO_SECURE_CONTENT_TYPE_NOSNIFF`
- What it does: sends `X-Content-Type-Options: nosniff`.
- Effect on system: helps prevent MIME sniffing issues.
- Default: `True`

`DJANGO_SECURE_REFERRER_POLICY`
- What it does: sets the Referrer-Policy header.
- Effect on system: controls how much referrer data browsers send.
- Default: `same-origin`

`DJANGO_X_FRAME_OPTIONS`
- What it does: controls iframe embedding policy.
- Effect on system: protects against clickjacking unless you intentionally embed pages.
- Default: `SAMEORIGIN`

### Email

`DJANGO_DEFAULT_FROM_EMAIL`
- What it does: default sender address for outgoing app mail.
- Effect on system: used for platform messages, notifications, and system-generated email sender defaults.
- Where to get it: your sending domain/email strategy.
- Example: `no-reply@yourdomain.com`

`DJANGO_SERVER_EMAIL`
- What it does: sender used for server/admin-originated mail.
- Effect on system: used for technical/admin email sending contexts.
- Where to get it: usually same domain as `DJANGO_DEFAULT_FROM_EMAIL`

### Logging

`DJANGO_LOG_TO_FILE`
- What it does: toggles file logging.
- Effect on system:
  - on Vercel you usually want console logging
  - on cPanel/VPS you may want file logging
- Typical values:
  - `False` on Vercel
  - `True` on persistent servers

`DJANGO_LOG_DIR`
- What it does: filesystem directory for log files.
- Effect on system: required if file logging is enabled and you want a custom log location.
- Where to get it: your server path design.

`DJANGO_LOG_LEVEL`
- What it does: root log verbosity.
- Effect on system: changes how much operational detail gets logged.
- Common values: `INFO`, `WARNING`, `ERROR`, `DEBUG`

### Vercel-Specific

`PUBLIC_VERCEL_URL`
- What it does: optional public Vercel hostname reference.
- Effect on system: helps host and CSRF handling when preview/production Vercel URLs are involved.
- Where to get it: your Vercel deployment/project hostname.

`VERCEL_RUN_MIGRATIONS`
- What it does: controls whether the Vercel build script runs migrations and theme sync.
- Effect on system: powerful but operationally sensitive because this app uses `django-tenants`.
- Typical values:
  - `0` for preview deployments
  - `1` only when you intentionally want Vercel builds to run DB migrations

`VERCEL_BOOTSTRAP_PUBLIC_DOMAIN`
- What it does: tells the Vercel build script to create or update the public-schema domain mapping for the deployed Vercel hostname.
- Effect on system: useful when the platform/public side of the app should answer on the Vercel deployment domain automatically.
- Typical values:
  - `0` by default
  - `1` when you want deployment-time public-domain bootstrap

`PUBLIC_TENANT_OWNER_EMAIL`
- What it does: email of the PlatformUser who should own the public `Shop` row if it has to be created.
- Effect on system: only used when the public tenant row does not already exist.
- Where to get it: one of your platform admin user email addresses.

`PUBLIC_TENANT_NAME`
- What it does: display name used if the public `Shop` row must be created automatically.
- Effect on system: cosmetic/admin-facing label for the public tenant record.
- Typical value: `Public Platform`

## What Is Not In Env Right Now

These are not being sourced from environment variables in the current codebase:

- payment gateway credentials
- platform/tenant gateway API keys
- most marketplace/payment provider secrets

Those are currently managed in the database through the platform payment configuration UI/models, not through `.env`.

## Recommended Minimum Local Dev Env

```env
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,[::1]
DB_ENGINE=django_tenants.postgresql_backend
DB_NAME=sabistore
DB_USER=sabistore
DB_PASSWORD=replace-with-db-password
DB_HOST=localhost
DB_PORT=5432
PLATFORM_CNAME=localhost
SUBDOMAIN_SUFFIX=
DOMAIN_SIMULATE_INFRA=True
```

## Recommended Minimum Vercel Env

```env
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=.vercel.app,yourdomain.com,www.yourdomain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
DATABASE_URL=postgres://user:password@host:5432/dbname
BLOB_READ_WRITE_TOKEN=vercel_blob_rw_token
PLATFORM_CNAME=yourdomain.com
SUBDOMAIN_SUFFIX=
VERCEL_RUN_MIGRATIONS=0
```

## Recommended Minimum cPanel / VPS Env

```env
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=example.com,www.example.com,shop.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://example.com,https://www.example.com,https://shop.example.com
DB_ENGINE=django_tenants.postgresql_backend
DB_NAME=your_db
DB_USER=your_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
PLATFORM_CNAME=example.com
SUBDOMAIN_SUFFIX=.example.com
DOMAIN_SIMULATE_INFRA=False
DJANGO_SECURE_SSL_REDIRECT=True
```

## Deployment-Specific References

- Vercel guide: [DEPLOY_VERCEL.md](C:/Users/user/Desktop/build/backend/sabistart-store/DEPLOY_VERCEL.md)
- Detailed Vercel notes: [deployment/vercel/README.md](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/vercel/README.md)
- cPanel guide: [deployment/cpanel/README.md](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/README.md)
