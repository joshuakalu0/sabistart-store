#!/usr/bin/env bash
set -euo pipefail

export DJANGO_DEBUG="${DJANGO_DEBUG:-False}"
export DOMAIN_SIMULATE_INFRA="${DOMAIN_SIMULATE_INFRA:-False}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

RUNTIME_PACKAGES_DIR="${RUNTIME_PACKAGES_DIR:-/tmp/sabistart_runtime_packages}"
export SABISTART_RUNTIME_PACKAGES_DIR="$RUNTIME_PACKAGES_DIR"
BUNDLED_APPS_DIR="${BUNDLED_APPS_DIR:-sabistart/_runtime_apps}"

python --version
python -c "import sys; print('python_executable=', sys.executable)"

rm -rf "$BUNDLED_APPS_DIR"
mkdir -p "$BUNDLED_APPS_DIR"
cp -R public "$BUNDLED_APPS_DIR/public"
cp -R dashboard "$BUNDLED_APPS_DIR/dashboard"
cp -R system "$BUNDLED_APPS_DIR/system"

if [ -n "${VERCEL:-}" ] && [ "${VERCEL_PRUNE_SOURCE_PACKAGES:-1}" = "1" ]; then
  rm -rf public dashboard system
fi

rm -rf "$RUNTIME_PACKAGES_DIR"
python -m pip install --disable-pip-version-check --no-cache-dir --target "$RUNTIME_PACKAGES_DIR" -r requirements.txt
export PYTHONPATH="$RUNTIME_PACKAGES_DIR${PYTHONPATH:+:$PYTHONPATH}"

python -c "import psycopg; print('psycopg_version=', psycopg.__version__)"

python manage.py check_vercel_deployment --strict

if [ "${VERCEL_RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate_schemas --shared --noinput
  python manage.py migrate_schemas --tenant --noinput
  python manage.py sync_theme_catalog
fi

if [ "${VERCEL_BOOTSTRAP_PUBLIC_DOMAIN:-0}" = "1" ]; then
  if [ "${VERCEL_BOOTSTRAP_PUBLIC_DOMAIN_REASSIGN:-0}" = "1" ]; then
    python manage.py sync_public_vercel_domain --create-public-tenant --make-primary --reassign
  else
    python manage.py sync_public_vercel_domain --create-public-tenant --make-primary
  fi
fi

python manage.py collectstatic --noinput
