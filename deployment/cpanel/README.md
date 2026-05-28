# cPanel Production Deployment Guide

This repository is prepared for **cPanel Python App + Passenger + PostgreSQL** deployment.

## Hosting requirements

Your cPanel plan must support:

- Python applications
- PostgreSQL
- a database user allowed to create and use schemas

This app will not work correctly on:

- MySQL-only hosting
- shared plans without Python App support
- PostgreSQL setups that block schema creation
- hosts that block outbound connections to your external PostgreSQL provider

## Files you will use

- [passenger_wsgi.py](C:/Users/user/Desktop/build/backend/sabistart-store/passenger_wsgi.py)
- [.cpanel.yml](C:/Users/user/Desktop/build/backend/sabistart-store/.cpanel.yml)
- [deployment/cpanel/post_deploy.sh](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/post_deploy.sh)
- [deployment/cpanel/.env.cpanel.example](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/.env.cpanel.example)
- [deployment/cpanel/.htaccess.example](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/.htaccess.example)

## Recommended server layout

Keep the application code outside the public web root when possible.

Example:

- app root: `/home/sabistar/sabi-store`
- static root: `/home/sabistar/sabi-store/staticfiles`
- media root: `/home/sabistar/sabi-store/media`
- log dir: `/home/sabistar/sabi-store/logs`

## cPanel setup steps

1. Create a PostgreSQL database in cPanel.
2. Create a PostgreSQL user and assign it to that database.
3. Make sure the user has enough privileges for schema-based migration work.
4. Open **Application Manager** or **Setup Python App** in cPanel.
5. Create the Python app and point the application root to this repository.
6. Set the startup file to `passenger_wsgi.py`.
7. Use the Python version supported by your host. Python `3.12` or newer is preferred.
8. Add environment variables from [deployment/cpanel/.env.cpanel.example](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/.env.cpanel.example).
9. Make sure `DJANGO_DEBUG=False`.
10. Make sure `DOMAIN_SIMULATE_INFRA=False`.

## Required environment values

At minimum, set:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DB_ENGINE=django_tenants.postgresql_backend`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`
- `DJANGO_STATIC_ROOT`
- `DJANGO_MEDIA_ROOT`
- `DJANGO_LOG_DIR`
- `PLATFORM_CNAME`
- `SUBDOMAIN_SUFFIX`

## Recommended domain strategy for sabistart.store

Use:

- platform root: `sabistart.store`
- optional public marketing alias: `www.sabistart.store`
- tenant stores: `{tenant}.sabistart.store`

Recommended values:

```env
DJANGO_ALLOWED_HOSTS=sabistart.store,www.sabistart.store,.sabistart.store
DJANGO_CSRF_TRUSTED_ORIGINS=https://sabistart.store,https://www.sabistart.store,https://*.sabistart.store
PLATFORM_CNAME=sabistart.store
SUBDOMAIN_SUFFIX=.sabistart.store
DJANGO_DEFAULT_FROM_EMAIL=no-reply@sabistart.store
DJANGO_SERVER_EMAIL=no-reply@sabistart.store
```

If your cPanel host supports wildcard subdomains, create:

- an `A` or `CNAME` record for `sabistart.store`
- an `A` or `CNAME` record for `www`
- a wildcard `*` subdomain pointing to the same app target

If wildcard DNS or wildcard subdomains are not supported on your plan, tenant subdomain routing will not be fully usable and you should rely on custom domains instead.

## First deploy

After the app is created and the env values are in place:

```bash
cd ~/sabistart-store
bash deployment/cpanel/post_deploy.sh
```

If Bash reports `set: pipefail` or other odd syntax errors, the server copy of the script usually has Windows line endings. Normalize it once, then rerun:

```bash
sed -i 's/\r$//' deployment/cpanel/post_deploy.sh
bash deployment/cpanel/post_deploy.sh
```

If a deployment tool insists on executing deployment through Python instead of Bash, use:

```bash
python deployment/cpanel/post_deploy.py
```

## What the deploy script does

The deploy script:

1. finds the correct Python executable for the cPanel app
2. calls `deployment/cpanel/post_deploy.py`

The Python deploy script then:

1. installs `requirements.txt`
2. runs `manage.py check`
3. runs `manage.py check_cpanel_deployment --strict`
4. ensures static, media, log, and `tmp` directories exist
5. runs shared migrations
6. runs tenant migrations
7. runs `sync_theme_catalog`
8. runs `sync_domain_tld_catalog`
9. runs `collectstatic`

If you already know the database is reachable and the migrations are already applied, you can skip those steps explicitly for a redeploy:

```bash
SABISTART_SKIP_DATABASE_PREFLIGHT=1 SABISTART_SKIP_MIGRATIONS=1 bash deployment/cpanel/post_deploy.sh
```

You can also skip only the preflight and still let migrations run:

```bash
SABISTART_SKIP_DATABASE_PREFLIGHT=1 bash deployment/cpanel/post_deploy.sh
```

If you want the deploy script to bypass all DB-dependent deployment work and just install dependencies, run checks, collect static files, and trigger the app reload, use:

```bash
SABISTART_FAST_DEPLOY=1 bash deployment/cpanel/post_deploy.sh
```

`SABISTART_FAST_DEPLOY=1` implies:

- skip database preflight
- skip schema migrations
- skip `sync_theme_catalog`
- skip `sync_domain_tld_catalog`

If the server previously used Neon or another remote database, clear any stale cPanel app-level database variables before rerunning deploy. The cPanel runtime can keep exporting old values such as `DATABASE_URL`, `DATABASE_URL_UNPOOLED`, `POSTGRES_URL`, or `POSTGRES_PRISMA_URL` until you remove or replace them.
10. touches `tmp/restart.txt`

## Validation commands

Run these before go-live:

```bash
python manage.py check
python manage.py check_cpanel_deployment --strict
```

## Static files

Use persistent filesystem paths.

Example:

```env
DJANGO_STATIC_ROOT=/home/username/sabistart-store/staticfiles
DJANGO_MEDIA_ROOT=/home/username/sabistart-store/media
DJANGO_LOG_DIR=/home/username/sabistart-store/logs
```

Do not use:

- `/tmp`
- short-lived cache folders
- directories your Passenger user cannot write to

## Optional Apache rules

If your hosting layout needs Apache-side hardening or caching, start from:

- [deployment/cpanel/.htaccess.example](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/.htaccess.example)

That file includes:

- HTTPS redirect
- basic security headers
- protection for sensitive files
- static cache examples

## Domain and tenant routing

This project keeps tenant routing inside Django.

That means:

- the domain must point to the Python app correctly
- subdomain routing must reach Passenger
- `PLATFORM_CNAME` and `SUBDOMAIN_SUFFIX` must match your real domain strategy

Example:

```env
PLATFORM_CNAME=sabistart.store
SUBDOMAIN_SUFFIX=.sabistart.store
```

## Health checks

After deploy, test:

- `/healthz/`
- `/readyz/`

`/readyz/` returns `503` if the database is not ready.

## Important notes

- WhiteNoise is enabled, so the app still has a safe static fallback.
- The default cPanel path uses filesystem media storage, not Vercel Blob storage.
- If you still see schema-related migration errors, verify that the PostgreSQL user can create and use schemas.
- If you use an external PostgreSQL provider such as Neon instead of local cPanel PostgreSQL, the cPanel host must allow outbound access to that provider on the required port. If the host cannot reach the external database, deployment and runtime will both fail.
