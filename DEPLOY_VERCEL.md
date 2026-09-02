# Deploying on Vercel

The repo is now wired for Vercel's Python runtime.

Start with the full guide here:

- [`deployment/vercel/README.md`](deployment/vercel/README.md)

Key files:

- [`vercel.json`](vercel.json)
- [`.python-version`](.python-version)
- [`deployment/vercel/build.sh`](deployment/vercel/build.sh)
- [`deployment/vercel/.env.vercel.example`](deployment/vercel/.env.vercel.example)
- [`sabistart/storage_backends.py`](sabistart/storage_backends.py)

Before deploying, make sure Vercel has:

- a PostgreSQL `DATABASE_URL`
- a `BLOB_READ_WRITE_TOKEN`
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
  - preview builds can rely on `VERCEL_URL` / `PUBLIC_VERCEL_URL`
  - production should still set `PLATFORM_CNAME` explicitly

The PostgreSQL driver is provided through `psycopg[binary]` in [`requirements.txt`](requirements.txt). This codebase intentionally uses psycopg 3 on Vercel because Django 5.2 and `django-tenants` support it, and it avoids the `_psycopg` binary-extension loading issue that can happen with `psycopg2-binary` in Vercel's Python runtime.

Vercel is also pinned to Python `3.12` through [`.python-version`](.python-version). That file must be committed to git. This is intentional: the runtime logs showed a build/install step using Python `3.14` while the deployed runtime paths were loading Python `3.12`, which can break compiled database drivers.

This project now uses an explicit Python function entrypoint at [`api/index.py`](api/index.py) instead of relying on Vercel's Django auto-detection. That is intentional for this codebase because Django loads many apps from string names in `INSTALLED_APPS`, and the explicit function config in [`vercel.json`](vercel.json) lets us force-include [`public`](public), [`dashboard`](dashboard), [`system`](system), [`templates`](templates), and [`themes`](themes) in the deployment bundle.

The Vercel build script also vendors a temporary, runtime-compatible dependency set into `/tmp/sabistart_runtime_packages` using the actual Python interpreter running the build command. That is a deliberate workaround for the build/runtime Python mismatch visible in the Vercel logs, and keeping it outside the repository tree avoids bloating the deployed function bundle.

To make Django app imports stable on Vercel, the build script also copies the `public`, `dashboard`, and `system` packages into [`sabistart/_runtime_apps`](sabistart/_runtime_apps) before bundling. On Vercel builds it then prunes those source packages from the deployment root so the final bundle does not rely on top-level runtime imports or accidentally expose the repo’s `public/` Python package as static content.

Readiness check:

```bash
python manage.py check_vercel_deployment --strict
```
