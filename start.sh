#!/usr/bin/env bash
set -o errexit

until python manage.py check --database default; do
  echo 'Waiting for database...'
  sleep 1
done
python manage.py migrate

# Ensure setuptools is available before starting gunicorn
python -c "import setuptools; print('setuptools version:', setuptools.__version__)"
exec gunicorn sabistart.wsgi:application --bind 0.0.0.0:${PORT:-8000}