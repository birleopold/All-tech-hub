#!/usr/bin/env bash
# Routine releases for the existing LEOSOFT Ubuntu VPS. Run as admin.
set -Eeuo pipefail
umask 022

APP_DIR="${ALLTECH_APP_DIR:-/home/admin/All-tech-hub}"
VENV_DIR="${ALLTECH_VENV_DIR:-${APP_DIR}/.venv}"
ENV_FILE="${ALLTECH_ENV_FILE:-${APP_DIR}/.env}"
PUBLIC_HEALTH_URL="${ALLTECH_PUBLIC_HEALTH_URL:-https://leosoftug.com/health/ready/}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
trap 'printf "VPS update stopped at line %s. Review the error above before rerunning.\n" "$LINENO" >&2' ERR

[[ "$(id -un)" != root ]] || fail "Run this script as admin, with sudo access."
[[ -d "$APP_DIR/.git" ]] || fail "Repository not found: $APP_DIR"
[[ -x "$VENV_DIR/bin/python" ]] || fail "Virtualenv Python not found: $VENV_DIR/bin/python"
[[ -f "$ENV_FILE" ]] || fail "Production environment file not found: $ENV_FILE"
command -v flock >/dev/null || fail "flock is required for the deployment lock."

# Keep two manual updates from pulling/installing/restarting at the same time.
exec 9>"${APP_DIR}/.vps-update.lock"
flock -n 9 || fail "Another VPS update is already running."
cd "$APP_DIR"
[[ "$(git branch --show-current)" == main ]] || fail "The production checkout must be on main."
[[ -z "$(git ls-files --unmerged)" ]] || fail "Resolve the existing Git merge conflict first."
sudo -v

printf '\nPulling origin/main (existing local edits are preserved)...\n'
git pull --ff-only origin main
EXPECTED_RELEASE="$(git rev-parse --short HEAD)"
printf '\nInstalling locked dependencies for %s...\n' "$EXPECTED_RELEASE"
"$VENV_DIR/bin/python" -m pip install -r requirements.lock

printf '\nUpdating the tracked durable automation units...\n'
sudo install -m 644 deployment/leosoft-marketing-posts.service /etc/systemd/system/leosoft-marketing-posts.service
sudo install -m 644 deployment/leosoft-marketing-posts.timer /etc/systemd/system/leosoft-marketing-posts.timer
sudo systemctl daemon-reload
sudo systemctl enable leosoft-marketing-posts.timer

export ALLTECH_APP_DIR="$APP_DIR" ALLTECH_VENV_DIR="$VENV_DIR" ALLTECH_ENV_FILE="$ENV_FILE"
bash scripts/deploy_production.sh

printf '\nVerifying public readiness...\n'
READINESS_PAYLOAD="$(curl --fail --silent --show-error --max-time 20 "$PUBLIC_HEALTH_URL")"
printf '%s\n' "$READINESS_PAYLOAD"
READINESS_PAYLOAD="$READINESS_PAYLOAD" EXPECTED_RELEASE="$EXPECTED_RELEASE" "$VENV_DIR/bin/python" - <<'PY'
import json
import os

payload = json.loads(os.environ["READINESS_PAYLOAD"])
required = {"status": "ok", "database": "ok", "migrations": "ok",
            "release": os.environ["EXPECTED_RELEASE"]}
failed = [key for key, value in required.items() if payload.get(key) != value]
if failed:
    raise SystemExit("Public readiness verification failed: " + ", ".join(failed))
print("Public site is ready on release " + payload["release"] + ".")
PY

printf '\nVPS update completed successfully.\n'
