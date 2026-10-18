#!/usr/bin/env bash
# Fail-closed final LEOSOFT release and durable evidence capture. Run as admin.
set -Eeuo pipefail
umask 077
APP_DIR=/home/admin/All-tech-hub
LOG_ROOT="$HOME/leosoft-release-logs"
mkdir -p "$LOG_ROOT"
LOG="$LOG_ROOT/closeout-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$LOG") 2>&1
trap 'rc=$?; printf "\nCloseout exited with code %s. Log: %s\n" "$rc" "$LOG"' EXIT
cd "$APP_DIR"
[[ -d .git && -x .venv/bin/python ]] || { echo "Missing application checkout/virtualenv" >&2; exit 2; }
[[ "$(git branch --show-current)" == main ]] || { echo "Checkout must be on main" >&2; exit 2; }
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || { echo "Tracked local changes must be resolved first" >&2; exit 2; }
echo "Guarded release started: $(date -u +%FT%TZ)"
echo "Source: $(git rev-parse HEAD)"
# Existing wrapper runs isolated migrations, backups and full Django tests;
# production deployment is called ONLY after those checks pass.
bash scripts/phase8_verified_deploy.sh
RELEASE="$(git rev-parse HEAD)"
SHORT="$(git rev-parse --short HEAD)"
PAYLOAD="$(curl --fail --silent --show-error --max-time 25 https://leosoftug.com/health/ready/)"
export RELEASE SHORT PAYLOAD
.venv/bin/python - <<'PY'
import json, os
p=json.loads(os.environ['PAYLOAD'])
expected={'status':'ok','database':'ok','migrations':'ok','release':os.environ['SHORT']}
wrong={k:(p.get(k),v) for k,v in expected.items() if p.get(k)!=v}
if wrong: raise SystemExit('Readiness mismatch: '+repr(wrong))
print('Public readiness matches tested Git revision.')
PY
systemctl is-active --quiet leosoft_gunicorn
systemctl is-active --quiet leosoft-marketing-posts.timer
REPORT="$LOG_ROOT/closeout-verified-$SHORT.json"
export REPORT
.venv/bin/python - <<'PY'
import json,os
from datetime import datetime,timezone
from pathlib import Path
report={
 'status':'release_checks_passed',
 'release_sha':os.environ['RELEASE'],
 'checked_utc':datetime.now(timezone.utc).isoformat(),
 'health_database_migrations_services':'verified',
 'external_manual_acceptance':'pending',
 'pending':['stock/specification inspections and Merchant approval',
            'live payment/SMTP/social provider verification',
            'actual phone/tablet browser acceptance',
            'isolated real PostgreSQL+media restore',
            'GitHub Actions runner execution']
}
Path(os.environ['REPORT']).write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print('Release evidence:',os.environ['REPORT'])
print('Automated release complete; independent external certification remains open.')
PY
