#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/admin/All-tech-hub"
PYTHON="$APP_DIR/.venv/bin/python"
BACKUP_ROOT="${ALLTECH_BACKUP_ROOT:-$APP_DIR/backups}"

cd "$APP_DIR"
umask 077
mkdir -p "$BACKUP_ROOT" "${ALLTECH_PRIVATE_MEDIA_ROOT:-$APP_DIR/private_media}"
chmod 700 "$BACKUP_ROOT" "${ALLTECH_PRIVATE_MEDIA_ROOT:-$APP_DIR/private_media}"

backup_arguments=(
    --include-media
    --retention-days 0
)

# backup_project verifies checksums before completing and understands the same
# off-site destination as the release workflow and dashboard health monitor.
if [[ -n "${ALLTECH_BACKUP_RCLONE_DEST:-}" ]]; then
    backup_arguments+=(--offsite)
fi

"$PYTHON" manage.py backup_project "${backup_arguments[@]}"

# Rotate only after the complete backup command succeeds, including off-site copy
# when configured. The rotation itself verifies all retained candidates.
# Deploy in preview mode first; explicitly opt in after inspecting the report.
rotate_args=(--root "$BACKUP_ROOT")
if [[ "${ALLTECH_BACKUP_ROTATE_APPLY:-false}" == "true" ]]; then
    rotate_args+=(--apply)
fi
"$PYTHON" "$APP_DIR/deployment/rotate-verified-backups.py" "${rotate_args[@]}"
