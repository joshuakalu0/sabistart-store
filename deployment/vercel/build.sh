#!/usr/bin/env bash
set -euo pipefail

python manage.py check_vercel_deployment --strict

if [ "${VERCEL_RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate_schemas --shared --noinput
  python manage.py migrate_schemas --tenant --noinput
  python manage.py sync_theme_catalog
fi

python manage.py collectstatic --noinput
