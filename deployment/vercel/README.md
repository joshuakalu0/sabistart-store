# Vercel Deployment

This project can run on Vercel's Python runtime with PostgreSQL and Vercel Blob.

## Required Vercel resources

1. A PostgreSQL database reachable from Vercel.
2. A Vercel Blob store connected to the project.

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
- `VERCEL_BLOB_ACCESS=private`
- `VERCEL_BLOB_CACHE_MAX_AGE=31536000`
- `VERCEL_RUN_MIGRATIONS=1`

Use [`deployment/vercel/.env.vercel.example`](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/vercel/.env.vercel.example) as the starting point.

## Runtime shape

- Requests are routed into [`api/index.py`](C:/Users/user/Desktop/build/backend/sabistart-store/api/index.py).
- Django serves dynamic pages from the Python function.
- Static files are collected at build time and served from the deployment filesystem.
- Uploaded media is stored in Vercel Blob and streamed back through Django's `/media/...` URLs.
- [`vercel.json`](C:/Users/user/Desktop/build/backend/sabistart-store/vercel.json) keeps per-function settings like `maxDuration`, but does not set a `runtime` field for Python. Vercel infers the official Python runtime from the `.py` entrypoint automatically.

## Build command

The root [`vercel.json`](C:/Users/user/Desktop/build/backend/sabistart-store/vercel.json) runs:

```bash
bash deployment/vercel/build.sh
```

That script:

1. Runs `manage.py check_vercel_deployment --strict`
2. Optionally runs schema migrations when `VERCEL_RUN_MIGRATIONS=1`
3. Runs `collectstatic`

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
