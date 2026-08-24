#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ALLTECH_ENV_FILE:-${APP_DIR}/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
    printf 'Production environment file not found: %s\n' "$ENV_FILE" >&2
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings}"
exec "${APP_DIR}/.venv/bin/python" "${APP_DIR}/manage.py" "$@"
