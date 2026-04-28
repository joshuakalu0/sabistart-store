# cPanel Deployment Guide

This project is now wired for **cPanel Python App + Passenger + PostgreSQL** deployment.

## Important hosting requirement

This codebase uses:

- `django-tenants`
- PostgreSQL schemas

So the hosting account must support:

- Python applications in cPanel
- PostgreSQL
- a database user that can create and use schemas in the target database

It is **not** compatible with a MySQL-only shared hosting plan.

## Files added for cPanel

- [`passenger_wsgi.py`](/c:/Users/user/Desktop/build/backend/sabistart-store/passenger_wsgi.py)
- [`.cpanel.yml`](/c:/Users/user/Desktop/build/backend/sabistart-store/.cpanel.yml)
- [`deployment/cpanel/post_deploy.sh`](/c:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/post_deploy.sh)
- [`deployment/cpanel/.env.cpanel.example`](/c:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/.env.cpanel.example)

## cPanel setup flow

1. Create a PostgreSQL database and user in cPanel.
2. Create a Python application in cPanel.
3. Point the application root to this project directory.
4. Set the startup file to `passenger_wsgi.py`.
5. Use the Python version supported by your cPanel host.
6. Add the environment variables from `.env.cpanel.example` in the cPanel Python App environment editor.
7. Make sure `DJANGO_DEBUG=False`.
8. Make sure `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` contain your real domains.

## First deploy commands

If you deploy manually over SSH:

```bash
cd ~/sabistart-store
bash deployment/cpanel/post_deploy.sh
```

If you deploy through cPanel Git Version Control, `.cpanel.yml` will call the same script automatically.

## What the deploy script does

The deploy script will:

1. install `requirements.txt`
2. run `manage.py check`
3. run `manage.py check_cpanel_deployment --strict`
4. run shared migrations
5. run tenant migrations
6. run `sync_theme_catalog`
7. run `collectstatic`
8. touch `tmp/restart.txt`

## Health checks

Two routes are available after deploy:

- `/healthz/`
- `/readyz/`

`/readyz/` checks the database connection and returns `503` if the app is not ready.

## Production checklist

- `DJANGO_SECRET_KEY` is set to a real secret
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS` is not `*`
- `DJANGO_CSRF_TRUSTED_ORIGINS` uses `https://...`
- PostgreSQL credentials are correct
- the database user can create/use schemas
- static root and media root point to writable folders
- SSL is enabled for the domain

## Validation command

Run this before go-live:

```bash
python manage.py check_cpanel_deployment --strict
```

## Notes

- Static files can be served through Apache/cPanel, but WhiteNoise middleware is also enabled so the app still has a safe fallback.
- This project keeps tenant/public routing in Django, so domain mapping must point to the Python app correctly.
