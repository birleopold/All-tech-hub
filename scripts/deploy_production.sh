#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${ALLTECH_APP_DIR:-/home/admin/All-tech-hub}"
VENV_DIR="${ALLTECH_VENV_DIR:-${APP_DIR}/.venv}"
ENV_FILE="${ALLTECH_ENV_FILE:-${APP_DIR}/.env}"
SERVICE_NAME="${ALLTECH_GUNICORN_SERVICE:-leosoft_gunicorn}"
HEALTH_URL="${ALLTECH_LOCAL_HEALTH_URL:-http://127.0.0.1:8010/health/ready/}"
HEALTH_HOST="${ALLTECH_HEALTH_HOST:-leosoftug.com}"
DEPLOY_BACKUP_ENABLED="${ALLTECH_DEPLOY_BACKUP_ENABLED:-1}"
DEPLOY_BACKUP_OFFSITE="${ALLTECH_DEPLOY_BACKUP_OFFSITE:-0}"
BACKUP_RETENTION_DAYS="${ALLTECH_BACKUP_RETENTION_DAYS:-30}"
SERVICE_RESTARTED=0

log() {
    printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

fail() {
    printf '\nERROR: %s\n' "$*" >&2
    return 1
}

is_true() {
    case "${1,,}" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
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
python manage.py audit_project --strict-environment --environment-only

if is_true "$DEPLOY_BACKUP_ENABLED"; then
    log "Pre-migration database backup"
    backup_arguments=(--retention-days "$BACKUP_RETENTION_DAYS")
    if is_true "$DEPLOY_BACKUP_OFFSITE"; then
        backup_arguments+=(--offsite)
    fi
    python manage.py backup_project "${backup_arguments[@]}"
else
    log "Pre-migration backup disabled by ALLTECH_DEPLOY_BACKUP_ENABLED"
fi

log "Database migrations"
python manage.py migrate --noinput

log "Ensuring missing commercial hubs and buying guides"
python manage.py ensure_growth_content

log "Post-migration project audit"
python manage.py audit_project

log "Search discoverability audit"
python manage.py audit_seo --strict

log "Merchant-enabled catalogue audit"
python manage.py audit_merchant --strict

log "Static asset manifest"
python manage.py collectstatic --noinput
python manage.py shell -c '
from django.contrib.staticfiles.storage import staticfiles_storage
for name in (
    "css/marketplace_experience.css",
    "css/search_conversion_refinement.css",
    "css/catalogue_growth_operations.css",
    "css/home_tech_ambient.css",
    "css/home_engagement.css",
    "js/marketplace_experience.js",
    "js/catalogue_bulk_enrichment.js",
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
readiness_payload="$(
    curl \
        --fail \
        --silent \
        --show-error \
        --max-time 15 \
        -H "Host: ${HEALTH_HOST}" \
        -H "X-Forwarded-Proto: https" \
        "$HEALTH_URL"
)"
printf '%s\n' "$readiness_payload"
READINESS_PAYLOAD="$readiness_payload" python - <<'PY'
import json
import os

try:
    payload = json.loads(os.environ["READINESS_PAYLOAD"])
except (KeyError, json.JSONDecodeError) as exc:
    raise SystemExit(f"Readiness endpoint returned invalid JSON: {exc}") from exc

expected_release = os.environ["ALLTECH_RELEASE_SHA"]
checks = {
    "status": payload.get("status") == "ok",
    "database": payload.get("database") == "ok",
    "release": payload.get("release") == expected_release,
}
failed = [name for name, passed in checks.items() if not passed]
if failed:
    raise SystemExit(
        "Readiness verification failed for "
        + ", ".join(failed)
        + f"; expected release {expected_release!r}, received {payload!r}"
    )
PY

sudo systemctl status "$SERVICE_NAME" --no-pager -l
trap - ERR
log "Deployment completed successfully"
