#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${ALLTECH_APP_DIR:-/home/admin/All-tech-hub}"
VENV_DIR="${ALLTECH_VENV_DIR:-${APP_DIR}/.venv}"
ENV_FILE="${ALLTECH_ENV_FILE:-${APP_DIR}/.env}"
SERVICE_NAME="${ALLTECH_GUNICORN_SERVICE:-leosoft_gunicorn}"
HEALTH_URL="${ALLTECH_LOCAL_HEALTH_URL:-http://127.0.0.1:8010/health/ready/}"
HEALTH_HOST="${ALLTECH_HEALTH_HOST:-leosoftug.com}"
SERVICE_RESTARTED=0

log() {
    printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

fail() {
    printf '\nERROR: %s\n' "$*" >&2
    exit 1
}

on_error() {
    local exit_code=$?
    printf '\nDeployment stopped before completion (exit %s).\n' "$exit_code" >&2
    if [[ "$SERVICE_RESTARTED" -eq 0 ]]; then
        printf 'Gunicorn was not restarted because a release preflight step failed.\n' >&2
    else
        printf 'Gunicorn was restarted, but post-restart verification failed.\n' >&2
        sudo systemctl status "$SERVICE_NAME" --no-pager -l >&2 || true
        sudo journalctl -u "$SERVICE_NAME" -n 60 --no-pager >&2 || true
    fi
    exit "$exit_code"
}
trap on_error ERR

[[ -d "$APP_DIR" ]] || fail "Application directory not found: $APP_DIR"
[[ -x "$VENV_DIR/bin/python" ]] || fail "Virtual environment is missing: $VENV_DIR"
[[ -f "$ENV_FILE" ]] || fail "Environment file is missing: $ENV_FILE"
[[ -f "$APP_DIR/manage.py" ]] || fail "manage.py is missing from $APP_DIR"

cd "$APP_DIR"
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# The project has a flat config/settings.py selector. A historic production
# value of config.settings.prod is invalid and previously allowed deployment
# commands to fail while systemd was still restarted. Keep the release shell
# authoritative even before the protected .env file is corrected.
if [[ "${DJANGO_SETTINGS_MODULE:-}" != "config.settings" ]]; then
    log "Overriding invalid DJANGO_SETTINGS_MODULE=${DJANGO_SETTINGS_MODULE:-<unset>}"
fi
export DJANGO_SETTINGS_MODULE="config.settings"
export ALLTECH_ENV="production"
export ALLTECH_RELEASE_SHA="${ALLTECH_RELEASE_SHA:-$(git rev-parse --short HEAD 2>/dev/null || printf unknown)}"

log "Release preflight"
printf 'Commit: %s\n' "$ALLTECH_RELEASE_SHA"
printf 'Settings: %s\n' "$DJANGO_SETTINGS_MODULE"
printf 'Environment: %s\n' "$ALLTECH_ENV"

python - <<'PY'
import os
from django.conf import settings

assert os.environ.get("DJANGO_SETTINGS_MODULE") == "config.settings"
assert os.environ.get("ALLTECH_ENV") == "production"
assert settings.DEBUG is False, "Production deployment cannot run with DEBUG=True"
assert settings.ALLOWED_HOSTS, "ALLTECH_ALLOWED_HOSTS must not be empty"
backend = settings.STORAGES["staticfiles"]["BACKEND"]
assert backend.endswith("ManifestStaticFilesStorage"), backend
print("Django production settings imported successfully.")
print("Static backend:", backend)
PY

python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py audit_project --strict-environment

log "Database migrations"
python manage.py migrate --noinput

log "Static asset manifest"
python manage.py collectstatic --noinput
python manage.py shell -c '
from django.contrib.staticfiles.storage import staticfiles_storage
for name in (
    "css/marketplace_experience.css",
    "css/search_conversion_refinement.css",
    "js/marketplace_experience.js",
):
    print(name, "=>", staticfiles_storage.url(name))
'

# Gunicorn is managed by systemd and does not inherit this release shell's
# environment. Persist the validated revision so the restarted process can
# expose the exact deployed code through the health endpoints.
printf '%s\n' "$ALLTECH_RELEASE_SHA" > "${APP_DIR}/.release.tmp"
mv "${APP_DIR}/.release.tmp" "${APP_DIR}/.release"

log "Restarting ${SERVICE_NAME}"
sudo systemctl restart "$SERVICE_NAME"
SERVICE_RESTARTED=1
sleep 3
sudo systemctl is-active --quiet "$SERVICE_NAME"

log "Application readiness"
readiness_payload="$({
    curl \
        --fail \
        --silent \
        --show-error \
        --max-time 15 \
        -H "Host: ${HEALTH_HOST}" \
        -H "X-Forwarded-Proto: https" \
        "$HEALTH_URL"
})"
printf '%s\n' "$readiness_payload"
[[ "$readiness_payload" == *"\"release\": \"${ALLTECH_RELEASE_SHA}\""* ]] \
    || fail "Readiness endpoint did not report release ${ALLTECH_RELEASE_SHA}."

sudo systemctl status "$SERVICE_NAME" --no-pager -l
trap - ERR
log "Deployment completed successfully"
