#!/usr/bin/env bash
# =============================================================================
# provision_tenants.sh — Cron-driven tenant migration sweep for SABIStart
# =============================================================================
# Runs `manage.py process_pending_tenants` as a separate OS process every N
# minutes so ALL migration DDL executes outside Gunicorn/Passenger (no OOM).
#
# SETUP:
#   1. Upload to /home/sabistar/sabi-store/provision_tenants.sh
#   2. Make executable:  chmod +x /home/sabistar/sabi-store/provision_tenants.sh
#   3. cPanel Cron Jobs ? every 3 minutes:
#        */3 * * * * /home/sabistar/sabi-store/provision_tenants.sh
# =============================================================================
set -euo pipefail

PROJECT_ROOT="/home/sabistar/repositories/sabistart-store"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"

# Fallback virtualenv paths used by some cPanel providers
[ ! -f "${VENV_PYTHON}" ] && VENV_PYTHON="${HOME}/virtualenv/sabistart-store/3.12/bin/python"
[ ! -f "${VENV_PYTHON}" ] && VENV_PYTHON="${HOME}/.venv/bin/python"

MANAGE="${PROJECT_ROOT}/manage.py"
ENV_FILE="${PROJECT_ROOT}/deployment/cpanel/.env.cpanel"
LOG_FILE="/home/sabistar/logs/provision.log"
LOCK_FILE="/tmp/sabistart_provision.lock"

# Prevent overlapping runs
exec 200>"${LOCK_FILE}"
if ! flock -n 200; then
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] [provision_tenants] Another run still in progress. Skipping." >> "${LOG_FILE}"
    exit 0
fi

mkdir -p "$(dirname "${LOG_FILE}")"

echo "" >> "${LOG_FILE}"
echo "=== [$(date -u +%Y-%m-%dT%H:%M:%SZ)] START ===" >> "${LOG_FILE}"

# Load env file
if [ -f "${ENV_FILE}" ]; then
    set -a
    source <(grep -v '^\s*#' "${ENV_FILE}" | grep -v '^\s*$')
    set +a
else
    echo "[provision_tenants] WARNING: env file not found at ${ENV_FILE}" >> "${LOG_FILE}"
fi

# Run migration sweep (subprocess isolates DDL from Gunicorn memory)
"${VENV_PYTHON}" "${MANAGE}" process_pending_tenants \
    --max-per-run 1 \
    --subprocess-timeout 600 \
    >> "${LOG_FILE}" 2>&1

EXIT_CODE=$?
echo "=== [$(date -u +%Y-%m-%dT%H:%M:%SZ)] END (exit=${EXIT_CODE}) ===" >> "${LOG_FILE}"
exit "${EXIT_CODE}"
