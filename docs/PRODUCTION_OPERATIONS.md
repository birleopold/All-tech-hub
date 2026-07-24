# LEOSOFT production operations

## Required settings selector

This project uses a flat `config/settings.py` selector. Production must use:

```dotenv
DJANGO_SETTINGS_MODULE=config.settings
ALLTECH_ENV=production
```

`config.settings.prod` and `config.settings.production` are invalid module paths.
The selector imports `config.settings_production` when `ALLTECH_ENV=production`.

## Standard release

Pull the reviewed `main` branch, then use the fail-fast release script:

```bash
cd /home/admin/All-tech-hub
git pull --ff-only origin main
bash scripts/deploy_production.sh
```

The script:

1. verifies the repository, virtual environment and protected `.env` file;
2. overrides an invalid settings-module value inside the release shell;
3. imports production settings and confirms `DEBUG=False`;
4. runs Django deployment checks;
5. fails when model changes exist without migrations;
6. runs migrations and builds the hashed static manifest;
7. restarts Gunicorn only after preflight steps succeed;
8. checks systemd and the local database-backed readiness endpoint.

The script does not edit `.env`. Correct the protected file permanently after any warning.

## Manual audit

```bash
cd /home/admin/All-tech-hub
source .venv/bin/activate
set -a
source .env
set +a
export DJANGO_SETTINGS_MODULE=config.settings
export ALLTECH_ENV=production
python manage.py audit_project --strict-environment
```

To make critical catalogue listings fail an audit run:

```bash
python manage.py audit_project --strict-environment --fail-on-catalogue-critical
```

Catalogue quality is also visible at `/staff/catalogue-quality/`.

## Health endpoints

- `/health/live/` confirms that the web process can answer requests without using the database.
- `/health/ready/` confirms that Django can complete a read-only database query.
- `/healthz/` remains a backwards-compatible alias for readiness monitoring.

All health responses are non-cacheable and excluded from search indexing.

A reverse proxy can use `/health/ready/` for upstream readiness. External uptime
monitoring should normally check both `/health/ready/` and a real public page such
as `/catalog/`.

## Request correlation

Every response includes `X-Request-ID`. A customer or staff member can provide
that value when reporting an error, allowing the related request to be located in
proxy and Gunicorn logs. A safe incoming request ID is retained; malformed values
are replaced.

## Release verification

After deployment:

```bash
curl -I https://leosoftug.com/
curl -I https://leosoftug.com/catalog/
curl -sS https://leosoftug.com/health/ready/
```

Confirm that public responses include `X-Request-ID`, private pages use
`Cache-Control: private, no-store`, and static asset URLs contain content hashes.

## Failure handling

- Do not restart Gunicorn after `check`, migration or static collection fails.
- Do not use `git reset --hard` on the production checkout.
- Capture `journalctl -u leosoft_gunicorn -n 100 --no-pager` when workers fail.
- Correct the underlying environment or code issue, then rerun the same release script.
- Database restoration should use a verified backup and a documented maintenance window.
