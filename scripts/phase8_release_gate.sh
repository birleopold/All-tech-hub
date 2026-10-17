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
mkdir -p "$ALLTECH_MEDIA_ROOT" "$ALLTECH_PRIVATE_MEDIA_ROOT"

printf 'Checking source and browser script syntax...\n'
python -m compileall -q -x '/migrations/' .
for source in \
    static/js/alltech_ui.js \
    static/js/pwa.js \
    static/js/marketing_analytics.js \
    static/js/marketplace_experience.js \
    static/js/mobile_commerce_pro.js; do
    node --check "$source"
done

printf 'Checking Django and migration drift...\n'
python manage.py check
python manage.py makemigrations --check --dry-run

printf 'Rehearsing migrations on an empty temporary database...\n'
python manage.py migrate --noinput

printf 'Running isolated Django tests...\n'
if [[ "$#" -gt 0 ]]; then
    python manage.py test --noinput "$@"
else
    python manage.py test --noinput
fi

printf 'Phase 8 offline code and migration rehearsal passed.\n'
printf 'This does not certify PostgreSQL restore, mobile browsers or external providers.\n'
