# Vercel Deployment

This project can run on Vercel's Python runtime with PostgreSQL and Vercel Blob.

## Required Vercel resources

1. A PostgreSQL database reachable from Vercel.
2. A Vercel Blob store connected to the project.

## PostgreSQL driver note

This project uses [`psycopg[binary]`](C:/Users/user/Desktop/build/backend/sabistart-store/requirements.txt) on Vercel instead of `psycopg2-binary`.

Why:

- Django 5.2 supports psycopg 3 directly.
- `django-tenants` detects psycopg 3 automatically and uses it when available.
- Vercel's Python runtime was failing to import `psycopg2._psycopg`, so psycopg 3 is the safer deployment target here.

## Python version pin

The repository includes [`.python-version`](C:/Users/user/Desktop/build/backend/sabistart-store/.python-version) pinned to `3.12`, and that file must remain committed.

Why:

- your Vercel logs showed dependency installation under Python `3.14.3`
- but the runtime stack paths were executing under Python `3.12`
- compiled PostgreSQL drivers are sensitive to that mismatch

Keeping build and runtime on the same Python version avoids those binary import failures.

## Required environment variables

At minimum, set these in Vercel Project Settings:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL`
- `BLOB_READ_WRITE_TOKEN`
- `PLATFORM_CNAME`

Optional but useful:

- `PUBLIC_VERCEL_URL`
- `DJANGO_DEFAULT_FROM_EMAIL`
- `DOMAIN_SIMULATE_INFRA=False`
- `VERCEL_BLOB_ACCESS=private`
- `VERCEL_BLOB_CACHE_MAX_AGE=31536000`
- `VERCEL_RUN_MIGRATIONS=1`
- `VERCEL_BOOTSTRAP_PUBLIC_DOMAIN=1`
- `PUBLIC_TENANT_OWNER_EMAIL=admin@yourdomain.com`
- `PUBLIC_TENANT_NAME=Public Platform`

Use [`deployment/vercel/.env.vercel.example`](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/vercel/.env.vercel.example) as the starting point.

## Runtime shape

- Vercel runs the app through the explicit Python function entrypoint at [`api/index.py`](C:/Users/user/Desktop/build/backend/sabistart-store/api/index.py).
- [`vercel.json`](C:/Users/user/Desktop/build/backend/sabistart-store/vercel.json) rewrites incoming requests to that function after checking the filesystem first.
- The function config force-includes the `public`, `dashboard`, `system`, `templates`, `themes`, and `sabistart_store` directories so Django's string-based `INSTALLED_APPS` loading works reliably in the deployment bundle.
- Static files are collected at build time and served from the deployment filesystem.
- Uploaded media is stored in Vercel Blob and streamed back through Django's `/media/...` URLs.
- [`vercel.json`](C:/Users/user/Desktop/build/backend/sabistart-store/vercel.json) sets the framework to `null` so Vercel treats this as an explicitly configured Python app instead of zero-config Django.

## PDF dependency note

This repo uses `xhtml2pdf` for PDF exports in analytics and POS. On Vercel, `svglib 1.6.x` pulls in `rlpycairo -> pycairo`, which requires native Cairo build libraries that are not available in the standard Vercel Python build image.

To keep Vercel deployments stable, [`requirements.txt`](C:/Users/user/Desktop/build/backend/sabistart-store/requirements.txt) pins:

```txt
svglib==1.5.1
```

That avoids the Cairo-native dependency chain while keeping `xhtml2pdf` available.

## Build command

The root [`vercel.json`](C:/Users/user/Desktop/build/backend/sabistart-store/vercel.json) runs:

```bash
bash deployment/vercel/build.sh
```

That script:

1. Runs `manage.py check_vercel_deployment --strict`
2. Optionally runs schema migrations when `VERCEL_RUN_MIGRATIONS=1`
3. Optionally creates/updates the public-schema domain for the Vercel hostname when `VERCEL_BOOTSTRAP_PUBLIC_DOMAIN=1`
4. Runs `collectstatic`

## Public domain bootstrap

If you want Vercel deployments to register the deployed hostname against the public schema automatically, set:

```bash
VERCEL_BOOTSTRAP_PUBLIC_DOMAIN=1
```

The build script will run:

```bash
python manage.py sync_public_vercel_domain --create-public-tenant --make-primary
```

That command:

- reads `PUBLIC_VERCEL_URL` first, then falls back to `VERCEL_URL`
- creates the public `Shop` row if it does not exist yet
- attaches the Vercel hostname to the public schema through the shared `Domain` table
- can use `PUBLIC_TENANT_OWNER_EMAIL` and `PUBLIC_TENANT_NAME` when it has to create the public tenant row

If the hostname is already attached to another tenant, the command will fail loudly instead of stealing it silently.

## Important note about migrations

This app uses `django-tenants`, so database migrations are operationally sensitive.

Recommended approach:

- Keep `VERCEL_RUN_MIGRATIONS=0` for normal preview deployments.
- Run shared and tenant migrations from a trusted deployment job or one-off admin shell before promoting production changes.

If you intentionally want Vercel builds to run migrations, set:

```bash
VERCEL_RUN_MIGRATIONS=1
```

## Deployment checklist

1. Connect the repo to a Vercel project.
2. Add the environment variables above.
3. Attach Postgres.
4. Attach Blob storage.
5. Deploy once.
6. Check:
   - `/healthz/`
   - `/readyz/`
   - storefront pages
   - dashboard login
   - media uploads

## Local readiness check

Run:

```bash
python manage.py check_vercel_deployment --strict
```
