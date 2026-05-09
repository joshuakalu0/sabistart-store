# Deploying on Vercel

The repo is now wired for Vercel's Python runtime.

Start with the full guide here:

- [`deployment/vercel/README.md`](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/vercel/README.md)

Key files:

- [`vercel.json`](C:/Users/user/Desktop/build/backend/sabistart-store/vercel.json)
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

This project now uses an explicit Python function entrypoint at [`api/index.py`](C:/Users/user/Desktop/build/backend/sabistart-store/api/index.py) instead of relying on Vercel's Django auto-detection. That is intentional for this codebase because Django loads many apps from string names in `INSTALLED_APPS`, and the explicit function config in [`vercel.json`](C:/Users/user/Desktop/build/backend/sabistart-store/vercel.json) lets us force-include [`public`](C:/Users/user/Desktop/build/backend/sabistart-store/public), [`dashboard`](C:/Users/user/Desktop/build/backend/sabistart-store/dashboard), [`system`](C:/Users/user/Desktop/build/backend/sabistart-store/system), [`templates`](C:/Users/user/Desktop/build/backend/sabistart-store/templates), and [`themes`](C:/Users/user/Desktop/build/backend/sabistart-store/themes) in the deployment bundle.

Readiness check:

```bash
python manage.py check_vercel_deployment --strict
```
