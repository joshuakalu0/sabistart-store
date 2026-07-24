# SabiStart Store Backend

SabiStart Store is a Django multi-tenant commerce platform built on:

- `Django 5`
- `django-tenants`
- PostgreSQL schemas
- tenant storefront + dashboard routing

This repository is prepared for both **cPanel** and **Vercel** deployment using:

- cPanel Python App
- Passenger
- PostgreSQL
- filesystem media/static storage
- Vercel Python runtime
- Vercel Blob for media

## Production target

This repo now supports two maintained deployment paths:

- **cPanel** for traditional shared hosting with Passenger
- **Vercel** for serverless deployment with PostgreSQL and Blob storage

Use the guide that matches your hosting target:

- [deployment/cpanel/README.md](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/README.md)
- [deployment/vercel/README.md](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/vercel/README.md)

## Hosting requirement

This project requires:

- Python application support in cPanel
- PostgreSQL
- a database user that can create and use schemas

It is not suitable for:

- MySQL-only shared hosting
- cPanel plans without Python App support
- hosting that blocks PostgreSQL schema usage

## Important deployment files

- [passenger_wsgi.py](C:/Users/user/Desktop/build/backend/sabistart-store/passenger_wsgi.py)
- [.cpanel.yml](C:/Users/user/Desktop/build/backend/sabistart-store/.cpanel.yml)
- [deployment/cpanel/post_deploy.sh](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/post_deploy.sh)
- [deployment/cpanel/.env.cpanel.example](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/.env.cpanel.example)
- [deployment/cpanel/.htaccess.example](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/.htaccess.example)
- [.env.example](C:/Users/user/Desktop/build/backend/sabistart-store/.env.example)

## Fast deployment flow

1. Create a PostgreSQL database and database user in cPanel.
2. Create a Python application in cPanel Application Manager.
3. Point the app root to this repository.
4. Set the startup file to `passenger_wsgi.py`.
5. Add environment variables from [deployment/cpanel/.env.cpanel.example](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/.env.cpanel.example).
6. Run:

```bash
bash deployment/cpanel/post_deploy.sh
```

7. Restart the Passenger app if cPanel does not do it automatically.

If a host-side tool or script runner executes deployment with Python instead of Bash, use:

```bash
python deployment/cpanel/post_deploy.py
```

Full instructions:

- [deployment/cpanel/README.md](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/README.md)

## Environment variables

Use:

- [.env.example](C:/Users/user/Desktop/build/backend/sabistart-store/.env.example) for the main tracked template
- [deployment/cpanel/.env.cpanel.example](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/.env.cpanel.example) for the cPanel production version

### Required for cPanel production

`DJANGO_SECRET_KEY`
- Long random secret used for sessions, CSRF, password reset tokens, and signing.
- Generate it yourself:
  `python -c "import secrets; print(secrets.token_urlsafe(64))"`

`DJANGO_DEBUG`
- Must be `False` in production.

`DJANGO_ALLOWED_HOSTS`
- Comma-separated hostnames Django may serve.
- Example: `sabistart.store,www.sabistart.store,.sabistart.store`

`DJANGO_CSRF_TRUSTED_ORIGINS`
- Full HTTPS origins used by forms, login, and admin POSTs.
- Example:
  `https://sabistart.store,https://www.sabistart.store,https://*.sabistart.store`

`DB_ENGINE`
- Must remain `django_tenants.postgresql_backend`.

`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- PostgreSQL credentials from cPanel.

`DJANGO_STATIC_ROOT`
- Persistent path where `collectstatic` writes files.
- Example:
  `/home/username/sabistart-store/staticfiles`

`DJANGO_MEDIA_ROOT`
- Persistent path for uploads.
- Example:
  `/home/username/sabistart-store/media`

`DJANGO_LOG_DIR`
- Persistent path for application logs.
- Example:
  `/home/username/sabistart-store/logs`

`PLATFORM_CNAME`
- Your main platform domain.
- Example: `sabistart.store`

`SUBDOMAIN_SUFFIX`
- Tenant subdomain suffix.
- Example: `.sabistart.store`

### Strongly recommended for production

`DJANGO_SECURE_SSL_REDIRECT=True`
- Forces HTTPS.

`DJANGO_SESSION_COOKIE_SECURE=True`
- Prevents session cookies from being sent over plain HTTP.

`DJANGO_CSRF_COOKIE_SECURE=True`
- Prevents CSRF cookies from being sent over plain HTTP.

`DOMAIN_SIMULATE_INFRA=False`
- Must be off in real production.

`DJANGO_LOG_TO_FILE=True`
- Recommended on cPanel so logs survive process restarts better than console-only logging.

### Optional

`DATABASE_URL`
- If your host provides a full PostgreSQL URL, you can use this instead of `DB_*`.

`DATABASE_URL_UNPOOLED`
- Useful mainly for Neon or other pooled managed Postgres setups.
- Usually not needed for normal cPanel localhost PostgreSQL.

`DJANGO_DEFAULT_FILE_STORAGE`
- Leave blank on cPanel.
- The app will automatically use tenant filesystem storage.

## What is not env-driven here

These are currently managed in the database, not from `.env`:

- payment gateway credentials
- tenant/provider payment keys
- most marketplace/payment provider secrets

## Production validation

Run:

```bash
python manage.py check
python manage.py check_cpanel_deployment --strict
```

The deployment script already runs both of those checks.

## Static and media

Recommended cPanel path pattern:

```env
DJANGO_STATIC_ROOT=/home/username/sabistart-store/staticfiles
DJANGO_MEDIA_ROOT=/home/username/sabistart-store/media
DJANGO_LOG_DIR=/home/username/sabistart-store/logs
```

Do not point these at `/tmp`.

## Health endpoints

After deployment, verify:

- `/healthz/`
- `/readyz/`

`/readyz/` checks the DB connection and returns `503` if the app is not ready.

## Optional Apache helper

If your cPanel layout needs extra Apache rules, start from:

- [deployment/cpanel/.htaccess.example](C:/Users/user/Desktop/build/backend/sabistart-store/deployment/cpanel/.htaccess.example)

Use it only in the public web root if your hosting layout requires it.

## Railway

Deploy your SabiStart Store backend to Railway with these steps:

1. **Create a Railway project**
   - Sign in to [Railway](https://railway.app/)
   - Click "New Project" -> "Deploy from GitHub"
   - Select this repository

2. **Configure the service**
   - Railway will automatically detect `railway.json` and `Procfile`
   - Add a PostgreSQL plugin: Click "+" -> "Add Resource" -> "PostgreSQL"
   - Ensure the database is linked to your service

3. **Set environment variables**
   - Go to the "Variables" tab in your service
   - Set:
     - `SECRET_KEY`: Generate a secret key (e.g., `python -c "import secrets; print(secrets.token_urlsafe(64))"`)
     - `DEBUG`: `False`
     - `DJANGO_ALLOWED_HOSTS`: Your domain (e.g., `example.com,www.example.com`)
     - `DJANGO_CSRF_TRUSTED_ORIGINS`: `https://example.com,https://www.example.com`
     - `DJANGO_SECURE_SSL_REDIRECT`: `True` (recommended)
     - `DJANGO_SESSION_COOKIE_SECURE`: `True`
     - `DJANGO_CSRF_COOKIE_SECURE`: `True`
     - `DJANGO_LOG_TO_FILE`: `True`

4. **Deploy**
   - Click "Deploy" and Railway will build and deploy your application
   - Check the logs for any issues

## Render

Your repository already includes a `render.yaml` for Render. To deploy:

1. **Create a Render Web Service**
   - Sign in to [Render](https://render.com/)
   - Click "New" -> "Web Service"
   - Connect your GitHub repository
   - Select this repository

2. **Configure the service**
   - Render will automatically detect `render.yaml`
   - In the service settings, add a PostgreSQL database (if not already defined in render.yaml)
   - Ensure the database is linked to the service

3. **Set environment variables**
   - In the "Environment" section, set:
     - `SECRET_KEY`: Generate a secret key
     - `DEBUG`: `False`
     - `DJANGO_ALLOWED_HOSTS`: Your domain
     - `DJANGO_CSRF_TRUSTED_ORIGINS`: Your domain with HTTPS
     - `DJANGO_SECURE_SSL_REDIRECT`: `True`
     - `DJANGO_SESSION_COOKIE_SECURE`: `True`
     - `DJANGO_CSRF_COOKIE_SECURE`: `True`
     - `DJANGO_LOG_TO_FILE`: `True`

4. **Deploy**
   - Click "Create Web Service" and Render will build and deploy your app

## Defang

Defang allows you to deploy to your own cloud (AWS, GCP, Azure) using a Docker Compose file.

1. **Install Defang CLI**
   ```bash
   curl -fsSL s.defang.io/install | bash
   ```

2. **Login to Defang**
   ```bash
   defang login
   ```

3. **Deploy to Defang Playground (for testing)**
   ```bash
   defang compose up
   ```
   - This will deploy to Defang's shared infrastructure

4. **Deploy to your own cloud (e.g., AWS)**
   - Set your cloud provider:
     ```bash
     export DEFANG_PROVIDER=aws
     ```
   - Ensure your AWS credentials are configured (via AWS CLI or environment variables)
   - Deploy:
     ```bash
     defang compose up
   ```
   - Defang will provision:
     - ECS cluster and service for the web app
     - RDS PostgreSQL instance
     - Necessary networking, load balancer, and security groups

5. **Configure environment variables**
   - Defang uses a secrets management system. Set secrets with:
     ```bash
     defang config set SECRET_KEY=<your-secret-key>
     defang config set DJANGO_ALLOWED_HOSTS="<your-domain>"
     # ... other variables as needed
   ```
   - Alternatively, define them in the `compose.yaml` under the `web` service's `environment` section (not recommended for production secrets)

6. **Verify deployment**
   - After deployment, Defang will provide a URL to access your application
   - Check the health endpoints: `/healthz/` and `/readyz/`

Note: The `compose.yaml` file in the repository defines the services (web and db) and uses the `build.sh` for building the Docker image. The startup script waits for the database, runs migrations, collects static files, and starts the Gunicorn server with Uvicorn workers.