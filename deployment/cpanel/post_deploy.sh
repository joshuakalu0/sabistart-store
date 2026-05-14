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

"${PYTHON_EXECUTABLE}" deployment/cpanel/post_deploy.py
