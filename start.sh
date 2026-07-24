#!/usr/bin/env bash
set -o errexit

python manage.py migrate
gunicorn sabistart_store.asgi:application -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT