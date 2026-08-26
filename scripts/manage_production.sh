#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${ALLTECH_APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="${ALLTECH_ENV_FILE:-${APP_DIR}/.env}"
VENV_DIR="${ALLTECH_VENV_DIR:-${APP_DIR}/.venv}"

[[ -f "${ENV_FILE}" ]] || {
    printf 'Production environment file not found: %s\n' "${ENV_FILE}" >&2
    exit 2
}
[[ -x "${VENV_DIR}/bin/python" ]] || {
    printf 'Production virtualenv Python not found: %s\n' "${VENV_DIR}/bin/python" >&2
    exit 2
}
[[ $# -gt 0 ]] || {
    printf 'Usage: scripts/manage_production.sh <management command> [arguments]\n' >&2
    exit 2
}

cd "${APP_DIR}"
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
export DJANGO_SETTINGS_MODULE=config.settings
export ALLTECH_ENV=production

"${VENV_DIR}/bin/python" - <<'PY'
import os

import django

django.setup()

from django.conf import settings
from django.db import connection

database = settings.DATABASES["default"]
engine = str(database.get("ENGINE") or "")
name = str(database.get("NAME") or "")
expected = os.getenv("ALLTECH_EXPECTED_DB_NAME", "").strip()

if settings.DEBUG:
    raise SystemExit("Refusing production command because DEBUG=True.")
if connection.vendor != "postgresql" or "postgresql" not in engine:
    raise SystemExit(
        "Refusing production command: the configured database is not PostgreSQL."
    )
if not name:
    raise SystemExit("Refusing production command: database NAME is empty.")
if expected and name != expected:
    raise SystemExit(
        f"Refusing production command: database is {name!r}, expected {expected!r}."
    )

host = str(database.get("HOST") or "local socket")
print(f"Production database verified: vendor=postgresql name={name} host={host}")
PY

exec "${VENV_DIR}/bin/python" manage.py "$@"
