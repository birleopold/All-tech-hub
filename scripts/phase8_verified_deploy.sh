#!/usr/bin/env bash
# Always enforce the isolated test gate before running the tracked VPS update.
# Unlike a pasted multi-line shell session, a failing test cannot fall through
# to the production deployment command.
set -Eeuo pipefail

APP_DIR="${ALLTECH_APP_DIR:-/home/admin/All-tech-hub}"
cd "$APP_DIR"
[[ -f .env && -x .venv/bin/python ]] || {
  echo "Existing application environment is missing." >&2
  exit 2
}
[[ "$(git branch --show-current)" == "main" ]] || {
  echo "Production checkout must be on main." >&2
  exit 2
}
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || {
  echo "Tracked local changes exist. Resolve them before deployment." >&2
  exit 2
}

# Verify the latest published commit, not a stale local checkout.
# This is safe: no dependencies, production settings or database are touched.
git fetch origin main
git merge --ff-only origin/main
tested_release="$(git rev-parse HEAD)"
[[ "$tested_release" == "$(git rev-parse origin/main)" ]] || {
  echo "Source changed while preparing the test gate. Retry." >&2
  exit 2
}

mkdir -p "$HOME/leosoft-release-logs"
log="$HOME/leosoft-release-logs/phase8-$(date +%Y%m%d-%H%M%S).log"

echo "Checking source ${tested_release:0:12} before any production changes."
echo "Full release-gate log: $log"
(
  source .venv/bin/activate
  bash -n scripts/phase8_release_gate.sh
  bash scripts/phase8_release_gate.sh
) 2>&1 | tee "$log"

echo "All isolated checks passed for $tested_release. Beginning existing guarded VPS update."
# The updater refuses to install a different Git revision from the one tested.
export ALLTECH_TESTED_RELEASE="$tested_release"
exec bash scripts/update_vps.sh
