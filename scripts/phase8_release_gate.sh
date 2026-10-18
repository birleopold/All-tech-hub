#!/usr/bin/env bash
# Offline release-candidate verification. Never loads the VPS .env or touches
# its database; uses a disposable SQLite database and a temporary media path.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v python >/dev/null || { echo "Python required" >&2; exit 1; }
command -v node >/dev/null || { echo "Node.js required for JS syntax checks" >&2; exit 1; }
WORK="$(mktemp -d -t leosoft-phase8.XXXXXXXX)"
trap 'rm -rf "$WORK"' EXIT
umask 077

# Override all release-target settings; never source .env.
export DJANGO_SETTINGS_MODULE=config.settings
export ALLTECH_ENV=development
export ALLTECH_DB_ENGINE=django.db.backends.sqlite3
export ALLTECH_DB_NAME="$WORK/rehearsal.sqlite3"
export ALLTECH_ALLOWED_HOSTS=localhost,127.0.0.1,testserver
export ALLTECH_EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend
export ALLTECH_MEDIA_ROOT="$WORK/media"
export ALLTECH_PRIVATE_MEDIA_ROOT="$WORK/private"
export ALLTECH_BACKUP_ROOT="$WORK/backups"
export ALLTECH_SECRET_KEY="phase8-local-only-not-a-production-secret-123456789"
export ALLTECH_FIELD_ENCRYPTION_KEY="phase8-local-encryption-key-not-production-123456789"
export ALLTECH_DB_HOST=""
export ALLTECH_DB_PORT=""
export ALLTECH_DB_USER=""
export ALLTECH_DB_PASSWORD=""
mkdir -p "$ALLTECH_MEDIA_ROOT" "$ALLTECH_PRIVATE_MEDIA_ROOT" "$ALLTECH_BACKUP_ROOT"

# A release gate must fail closed if a settings refactor sends test data to
# persistent production or developer storage. Do not rely on exported values
# alone: inspect the actual Django settings before running any migrations.
python - <<'PY'
import os
from pathlib import Path
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.conf import settings
expected = {
    "DATABASES.default.NAME": ("ALLTECH_DB_NAME", settings.DATABASES["default"]["NAME"]),
    "MEDIA_ROOT": ("ALLTECH_MEDIA_ROOT", settings.MEDIA_ROOT),
    "PRIVATE_MEDIA_ROOT": ("ALLTECH_PRIVATE_MEDIA_ROOT", settings.PRIVATE_MEDIA_ROOT),
    "BACKUP_ROOT": ("ALLTECH_BACKUP_ROOT", settings.BACKUP_ROOT),
}
for label, (variable, effective) in expected.items():
    required = Path(os.environ[variable]).resolve()
    actual = Path(effective).resolve()
    if actual != required:
        raise SystemExit(f"Refusing unsafe release rehearsal: {label}={actual} expected {required}")
    print(f"Isolated {label}: {actual}")
if settings.DEBUG is not True:
    raise SystemExit("Offline release rehearsal must run development settings.")
if "locmem" not in settings.EMAIL_BACKEND:
    raise SystemExit("Offline release rehearsal must use in-memory email.")
PY

printf 'Checking source and browser script syntax...\n'
python -m compileall -q -x '/migrations/' .
for source in \
    static/js/alltech_ui.js \
    static/js/pwa.js \
    static/js/marketing_analytics.js \
    static/js/marketplace_experience.js \
    static/js/mobile_commerce_pro.js \
    static/js/job_handover_signature.js \
    static/js/field_notes_offline.js; do
    node --check "$source"
done

printf 'Checking Django and migration drift...\n'
python manage.py check
python manage.py makemigrations --check --dry-run

printf 'Compiling high-traffic Django templates before expensive test suite...\n'
python - <<'PY'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.template.loader import get_template
for template in (
    "core/home.html",
    "catalog/_marketplace_product_card.html",
    "operations/_offline_field_notes.html",
    "operations/job_bench.html",
    "operations/job_detail.html",
    "billing/document_detail.html",
    "billing/quote_customer.html",
    "billing/revision_comparison.html",
    "portal/documents.html",
):
    get_template(template)
    print(f"Template syntax OK: {template}")
PY

printf 'Rehearsing migrations on an empty temporary database...\n'
python manage.py migrate --noinput

printf 'Verifying backup and isolated SQLite restore...\n'
python manage.py backup_project --include-media --retention-days 0
manifest="$WORK/backups/$(ls -1 "$WORK/backups" | grep '^leosoft-' | tail -n 1)/manifest.json"
[[ -f "$manifest" ]] || { echo "Isolated backup manifest missing" >&2; exit 1; }
python manage.py verify_alltech_backup "$manifest"
python - "$manifest" "$WORK/restore.sqlite3" <<'PY'
import json
import shutil
import sqlite3
import sys
from pathlib import Path
manifest = Path(sys.argv[1]).resolve()
restored = Path(sys.argv[2]).resolve()
records = json.loads(manifest.read_text(encoding="utf-8"))["files"]
database_records = [entry for entry in records if entry["name"] == "database.sqlite3"]
if len(database_records) != 1:
    raise SystemExit("Exactly one SQLite database backup is required for the restore drill.")
backup = manifest.parent / database_records[0]["name"]
shutil.copyfile(backup, restored)
with sqlite3.connect(f"file:{restored}?mode=ro", uri=True) as database:
    result = database.execute("PRAGMA integrity_check").fetchone()
    if result != ("ok",):
        raise SystemExit(f"Restored SQLite integrity check failed: {result}")
    migrations = database.execute("SELECT COUNT(*) FROM django_migrations").fetchone()[0]
    if migrations <= 0:
        raise SystemExit("Restored database has no migration records.")
    print(f"Temporary database restore passed; migration records: {migrations}")
PY
ALLTECH_DB_NAME="$WORK/restore.sqlite3" python manage.py migrate --check --noinput

printf 'Running isolated Django tests...\n'
if [[ "$#" -gt 0 ]]; then
    python manage.py test --noinput "$@"
else
    python manage.py test --noinput
fi

printf 'Phase 8 offline code and migration rehearsal passed.\n'
printf 'This does not certify PostgreSQL restore, mobile browsers or external providers.\n'
