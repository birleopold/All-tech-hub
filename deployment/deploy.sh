#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
VENV_DIR="${VENV_DIR:-${APP_DIR}/.venv}"
ENV_FILE="${ENV_FILE:-${APP_DIR}/.env}"
SYSTEMD_SERVICE="${SYSTEMD_SERVICE:-leosoft_gunicorn}"
HEALTHCHECK_URL="${HEALTHCHECK_URL:-http://127.0.0.1:8010/healthz/}"

cd "${APP_DIR}"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing production environment file: ${ENV_FILE}" >&2
    echo "Copy deployment/leosoft.env.example to .env and replace every placeholder." >&2
    exit 1
fi

if [[ -d .git && "${SKIP_GIT_PULL:-0}" != "1" ]]; then
    current_branch="$(git branch --show-current)"
    if [[ "${current_branch}" != "main" ]]; then
        echo "Expected the production checkout to remain on main, but it is on ${current_branch}." >&2
        exit 1
    fi
    git pull --ff-only origin main
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
if [[ -f requirements.lock ]]; then
    "${VENV_DIR}/bin/python" -m pip install -r requirements.lock
else
    "${VENV_DIR}/bin/python" -m pip install -r requirements.txt
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

if [[ "${ALLTECH_ENV:-}" != "production" ]]; then
    echo "ALLTECH_ENV must be set to production in ${ENV_FILE}." >&2
    exit 1
fi

mkdir -p staticfiles media backups

if [[ "${RUN_BACKUP:-0}" == "1" ]]; then
    "${VENV_DIR}/bin/python" manage.py backup_alltech --output backups
fi

"${VENV_DIR}/bin/python" manage.py check
"${VENV_DIR}/bin/python" manage.py check --deploy
"${VENV_DIR}/bin/python" manage.py migrate --noinput
"${VENV_DIR}/bin/python" manage.py collectstatic --noinput
"${VENV_DIR}/bin/python" manage.py bootstrap_roles
"${VENV_DIR}/bin/python" manage.py configure_company \
    --company-name "LEOSOFT" \
    --legal-name "LEOSOFT UG LTD" \
    --website "https://leosoftug.com" \
    --country "Uganda" \
    --currency "UGX"

sudo systemctl restart "${SYSTEMD_SERVICE}"
sudo systemctl is-active --quiet "${SYSTEMD_SERVICE}"

curl --fail --silent --show-error --retry 5 --retry-delay 2 "${HEALTHCHECK_URL}"
echo
echo "LEOSOFT UG LTD deployment completed successfully from origin/main."
