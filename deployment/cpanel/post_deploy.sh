#!/bin/bash
set -euo pipefail

APP_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

find_python_bin() {
  if [[ -n "${PYTHON_BIN:-}" && -x "${PYTHON_BIN}" ]]; then
    printf '%s\n' "${PYTHON_BIN}"
    return 0
  fi

  local candidates=(
    "${APP_ROOT}/venv/Scripts/python.exe"
    "${APP_ROOT}/.venv/Scripts/python.exe"
    "${APP_ROOT}/venv/bin/python"
    "${APP_ROOT}/.venv/bin/python"
    "${HOME}/virtualenv/$(basename "${APP_ROOT}")/3.14/bin/python"
    "${HOME}/virtualenv/$(basename "${APP_ROOT}")/3.13/bin/python"
    "${HOME}/virtualenv/$(basename "${APP_ROOT}")/3.12/bin/python"
    "${HOME}/virtualenv/$(basename "${APP_ROOT}")/3.11/bin/python"
    "${HOME}/virtualenv/$(basename "${APP_ROOT}")/3.10/bin/python"
  )

  local candidate
  for candidate in "${candidates[@]}"; do
    if [[ -x "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  command -v python3
}

PYTHON_EXECUTABLE="$(find_python_bin)"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-sabistart_store.settings}"

cd "${APP_ROOT}"

"${PYTHON_EXECUTABLE}" -m pip install -r requirements.txt
"${PYTHON_EXECUTABLE}" manage.py check
"${PYTHON_EXECUTABLE}" manage.py check_cpanel_deployment --strict
"${PYTHON_EXECUTABLE}" - <<'PY'
from pathlib import Path
import os
import sys

sys.path.insert(0, os.getcwd())
from sabistart_store.env import load_environment

load_environment()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sabistart_store.settings")
from django.conf import settings

paths = [
    Path(settings.STATIC_ROOT),
    Path(settings.MEDIA_ROOT),
    Path(getattr(settings, "LOG_DIR", settings.BASE_DIR / "logs")),
    Path(settings.BASE_DIR / "tmp"),
]
for path in paths:
    path.mkdir(parents=True, exist_ok=True)
print("Ensured deploy directories exist.")
PY
"${PYTHON_EXECUTABLE}" manage.py migrate_schemas --shared --noinput
"${PYTHON_EXECUTABLE}" manage.py migrate_schemas --tenant --noinput
"${PYTHON_EXECUTABLE}" manage.py sync_theme_catalog
"${PYTHON_EXECUTABLE}" manage.py collectstatic --noinput

mkdir -p tmp
touch tmp/restart.txt

echo "cPanel post-deploy finished successfully."
