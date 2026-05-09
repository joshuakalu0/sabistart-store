#!/usr/bin/env bash
set -euo pipefail

export DJANGO_DEBUG="${DJANGO_DEBUG:-False}"
export DOMAIN_SIMULATE_INFRA="${DOMAIN_SIMULATE_INFRA:-False}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

python --version
python -c "import sys; print('python_executable=', sys.executable)"
python -c "import psycopg; print('psycopg_version=', psycopg.__version__)"

python manage.py check_vercel_deployment --strict

if [ "${VERCEL_RUN_MIGRATIONS:-0}" = "1" ]; then
  python manage.py migrate_schemas --shared --noinput
  python manage.py migrate_schemas --tenant --noinput
  python manage.py sync_theme_catalog
fi

python manage.py collectstatic --noinput
