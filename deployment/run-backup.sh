#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/admin/All-tech-hub"
PYTHON="$APP_DIR/.venv/bin/python"
BACKUP_ROOT="${ALLTECH_BACKUP_ROOT:-$APP_DIR/backups}"

cd "$APP_DIR"
umask 077
mkdir -p "$BACKUP_ROOT" "${ALLTECH_PRIVATE_MEDIA_ROOT:-$APP_DIR/private_media}"
chmod 700 "$BACKUP_ROOT" "${ALLTECH_PRIVATE_MEDIA_ROOT:-$APP_DIR/private_media}"

"$PYTHON" manage.py backup_alltech --output "$BACKUP_ROOT"
"$PYTHON" manage.py verify_alltech_backup

# Optional encrypted/off-site destination configured through an existing rclone
# remote, for example: secure-s3:leosoft-production-backups
if [[ -n "${ALLTECH_BACKUP_RCLONE_DEST:-}" ]]; then
    if ! command -v rclone >/dev/null 2>&1; then
        echo "ALLTECH_BACKUP_RCLONE_DEST is configured but rclone is unavailable." >&2
        exit 1
    fi
    rclone copy "$BACKUP_ROOT" "$ALLTECH_BACKUP_RCLONE_DEST" \
        --include "alltech-*" \
        --transfers 2 \
        --checkers 4
fi
