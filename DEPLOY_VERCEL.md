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

Vercel now supports Django with zero configuration, so this project should deploy as a Django app directly. [`vercel.json`](C:/Users/user/Desktop/build/backend/sabistart-store/vercel.json) only sets the framework to `django` and keeps the custom build command for checks, migrations, and `collectstatic`.

Readiness check:

```bash
python manage.py check_vercel_deployment --strict
```
