#!/usr/bin/env bash
# =============================================================================
# provision_tenants.sh — Auto-detecting Cron Runner for Tenant Migrations
# =============================================================================
set -euo pipefail

# 1. Auto-detect project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${SCRIPT_DIR}"

# 2. Auto-detect Python virtualenv
if [ -f "${PROJECT_ROOT}/venv/bin/python" ]; then
    VENV_PYTHON="${PROJECT_ROOT}/venv/bin/python"
elif [ -f "${PROJECT_ROOT}/.venv/bin/python" ]; then
    VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
elif [ -f "${HOME}/virtualenv/sabistart-store/3.12/bin/python" ]; then
    VENV_PYTHON="${HOME}/virtualenv/sabistart-store/3.12/bin/python"
else
    VENV_PYTHON="$(which python3)"
fi

MANAGE="${PROJECT_ROOT}/manage.py"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/provision.log"
LOCK_FILE="/tmp/sabistart_provision.lock"

# 3. Ensure log dir exists
mkdir -p "${LOG_DIR}"

# 4. Prevent overlapping runs with flock
exec 200>"${LOCK_FILE}"
if ! flock -n 200; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Another run is still in progress. Skipping." >> "${LOG_FILE}"
    exit 0
fi

echo "" >> "${LOG_FILE}"
echo "=== [$(date -u +%Y-%m-%dT%H:%M:%SZ)] provision_tenants START ===" >> "${LOG_FILE}"

# 5. Load .env if present
if [ -f "${PROJECT_ROOT}/.env" ]; then
    set -a
    source <(grep -v '^\s*#' "${PROJECT_ROOT}/.env" | grep -v '^\s*$')
    set +a
fi

# 6. Run the tenant provisioning sweep
"${VENV_PYTHON}" "${MANAGE}" process_pending_tenants \
    --max-per-run 1 \
    --subprocess-timeout 600 \
    >> "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "=== [$(date -u +%Y-%m-%dT%H:%M:%SZ)] provision_tenants END (exit=${EXIT_CODE}) ===" >> "${LOG_FILE}"
exit "${EXIT_CODE}"
