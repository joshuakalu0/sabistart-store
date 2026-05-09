# Deploying on Vercel

The repo is now wired for Vercel's Python runtime.

Start with the full guide here:

- [`deployment/vercel/README.md`](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/vercel/README.md)

Key files:

- [`vercel.json`](C:/Users/user/Desktop/build/backend/sabistart-store/vercel.json)
- [`.python-version`](C:/Users/user/Desktop/build/backend/sabistart-store/.python-version)
- [`deployment/vercel/build.sh`](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/vercel/build.sh)
- [`deployment/vercel/.env.vercel.example`](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/vercel/.env.vercel.example)
- [`sabistart_store/storage_backends.py`](C:/Users/user/Desktop/build/backend/sabistart-store/sabistart_store/storage_backends.py)

Before deploying, make sure Vercel has:

- a PostgreSQL `DATABASE_URL`
- a `BLOB_READ_WRITE_TOKEN`
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`

The PostgreSQL driver is provided through `psycopg[binary]` in [`requirements.txt`](C:/Users/user/Desktop/build/backend/sabistart-store/requirements.txt). This codebase intentionally uses psycopg 3 on Vercel because Django 5.2 and `django-tenants` support it, and it avoids the `_psycopg` binary-extension loading issue that can happen with `psycopg2-binary` in Vercel's Python runtime.

Vercel is also pinned to Python `3.12` through [`.python-version`](C:/Users/user/Desktop/build/backend/sabistart-store/.python-version). That file must be committed to git. This is intentional: the runtime logs showed a build/install step using Python `3.14` while the deployed runtime paths were loading Python `3.12`, which can break compiled database drivers.

This project now uses an explicit Python function entrypoint at [`api/index.py`](C:/Users/user/Desktop/build/backend/sabistart-store/api/index.py) instead of relying on Vercel's Django auto-detection. That is intentional for this codebase because Django loads many apps from string names in `INSTALLED_APPS`, and the explicit function config in [`vercel.json`](C:/Users/user/Desktop/build/backend/sabistart-store/vercel.json) lets us force-include [`public`](C:/Users/user/Desktop/build/backend/sabistart-store/public), [`dashboard`](C:/Users/user/Desktop/build/backend/sabistart-store/dashboard), [`system`](C:/Users/user/Desktop/build/backend/sabistart-store/system), [`templates`](C:/Users/user/Desktop/build/backend/sabistart-store/templates), and [`themes`](C:/Users/user/Desktop/build/backend/sabistart-store/themes) in the deployment bundle.

The Vercel build script also vendors a temporary, runtime-compatible dependency set into `/tmp/sabistart_runtime_packages` using the actual Python interpreter running the build command. That is a deliberate workaround for the build/runtime Python mismatch visible in the Vercel logs, and keeping it outside the repository tree avoids bloating the deployed function bundle.

To make Django app imports stable on Vercel, the build script also copies the `public`, `dashboard`, and `system` packages into [`sabistart_store/_runtime_apps`](C:/Users/user/Desktop/build/backend/sabistart-store/sabistart_store/_runtime_apps) before bundling. The runtime prepends that directory to `sys.path`, which avoids the repeated Vercel-side `No module named 'public'` failure.

Readiness check:

```bash
python manage.py check_vercel_deployment --strict
```
