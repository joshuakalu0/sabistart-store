# cPanel Deploy Guide

This cPanel path is optimized for a direct deploy first, then a full database maintenance run when the database is ready.

## cPanel App Values

Use these values when creating the Python app:

- Application root: `/home/sabistar/repositories/sabistart-store`
- Startup file: `passenger_wsgi.py`
- Entry point: `application`
- Python version: `3.12` or newer
- Domain: `sabistart.store`

If your cPanel app root is different, keep using that actual path everywhere.

## Environment

The app loads:

```text
deployment/cpanel/.env.cpanel
```

For the local cPanel PostgreSQL database, the important DB values are:

```env
DB_ENGINE=django_tenants.postgresql_backend
DB_NAME=sabistar_store
DB_USER=sabistar_store
DB_PASSWORD=sabi.NJ.start.oo**LTD_DB
DB_HOST=
DB_PORT=
DB_SSLMODE=
DATABASE_URL=
DATABASE_URL_UNPOOLED=
POSTGRES_URL=
POSTGRES_PRISMA_URL=
```

Keep old Neon variables out of the cPanel Python App environment if you want the app to use the cPanel DB.

## Direct Deploy

This is the default path. It installs packages, prepares folders, collects static files, and restarts Passenger.

It skips:

- Django deployment checks
- database preflight
- migrations
- theme catalog sync
- domain TLD catalog sync

Run:

```bash
cd /home/sabistar/repositories/sabistart-store
bash deployment/cpanel/post_deploy.sh
```

cPanel Git Deployment also uses this direct path through:

```text
.cpanel.yml
```

After deploy, open:

```text
https://sabistart.store/deployz/
```

If cPanel is serving this Django app, that URL returns JSON with `ok: true` and a deployment marker. If it shows a cPanel/default page, a 404 from another app, or old content, the domain is not pointing at this Python app or Passenger did not reload this app root.

## Full Deploy

Run this only after the database connection is working.

It performs the full deployment, including Django checks, DB preflight, shared migrations, tenant migrations, theme sync, and domain catalog sync.

```bash
cd /home/sabistar/repositories/sabistart-store
SABISTART_FULL_DEPLOY=1 bash deployment/cpanel/post_deploy.sh
```

## Checks Only

If you want the direct deploy path but still want the lightweight Django checks, run:

```bash
SABISTART_RUN_CHECKS=1 bash deployment/cpanel/post_deploy.sh
```

## Useful Checks

Check which DB host Django is using:

```bash
SABISTART_ENV_FILE=deployment/cpanel/.env.cpanel SABISTART_ENV_OVERRIDE=1 python manage.py shell -c "from django.db import connection; print(connection.settings_dict.get('HOST'), connection.settings_dict.get('PORT'))"
```

Check Django without touching migrations:

```bash
python manage.py check
python manage.py check_cpanel_deployment --strict
```

Check the latest deploy marker on the server:

```bash
cat tmp/deploy.json
```

## FastAPI Server Smoke Test

Use this only to prove the server can run a tiny Python web process. It is separate from the Django/Passenger app.

Install the test-only packages inside the cPanel virtualenv:

```bash
python -m pip install fastapi uvicorn
```

Run the smoke server:

```bash
python -m uvicorn deployment.cpanel.fastapi_smoke:app --host 127.0.0.1 --port 8090
```

From another shell on the same server:

```bash
curl http://127.0.0.1:8090/
curl http://127.0.0.1:8090/healthz
```

If that returns JSON, Python and the virtualenv can run a simple HTTP server. Most shared cPanel plans will not expose this port publicly, so this test is mainly for server-side verification.

If the shell script shows weird `pipefail` or syntax errors, normalize line endings once:

```bash
sed -i 's/\r$//' deployment/cpanel/post_deploy.sh
```

## Important Reality Check

Direct deploy can make the deployment finish, but the live app still needs a working PostgreSQL database for tenant routing, login, dashboard pages, and storefront data.

Use direct deploy to get Passenger and static files in place. Use full deploy once PostgreSQL is fixed.
i want you to work on the ui of the entry system by for now only do the public part of the system, i want you to completely redesign and rebrand it , and make the ui totally morden and outstanding
and properly arrange thingd inother, use brown-wine color for the color
note this is a multi tenant syustem with a tennt system and the normal system where the tenat register and su[per admin live(plublic also localhost)
"neon": {
"url": "https://mcp.neon.tech/sse",
"type": "http"
},
"github": {
"url": "https://api.githubcopilot.com/mcp/",
"type": "http"
},
