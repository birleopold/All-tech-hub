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
4. runs Django deployment and model-migration checks;
5. audits unsafe environment gaps;
6. creates and verifies a database backup before migrations;
7. runs migrations and builds the hashed static manifest;
8. records the validated Git revision in `.release`;
9. restarts Gunicorn only after every preflight step succeeds;
10. checks systemd and confirms the readiness endpoint reports the same revision.

The script does not edit `.env`. Correct the protected file permanently after any warning.

Release backups are enabled by default. They can be controlled through:

```dotenv
ALLTECH_DEPLOY_BACKUP_ENABLED=1
ALLTECH_BACKUP_RETENTION_DAYS=30
ALLTECH_DEPLOY_BACKUP_OFFSITE=0
ALLTECH_BACKUP_RCLONE_DEST=secure-remote:leosoft-production-backups
```

Keep release backups enabled. Off-site mode should point to a tested rclone remote,
preferably an encrypted `crypt` remote. Backup directories contain business and
customer data and must not be placed in a public web directory.

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

## Backups

Create a database-only backup:

```bash
python manage.py backup_project
```

Create a full local backup containing the database, public media and private media:

```bash
python manage.py backup_project --include-media
```

Create a full backup and copy it to the configured rclone destination:

```bash
python manage.py backup_project --include-media --offsite
```

Each backup is stored under `ALLTECH_BACKUP_ROOT` with restrictive permissions. It
contains a JSON manifest, file sizes and SHA-256 checksums. SQLite uses the native
online backup API. PostgreSQL uses a custom-format `pg_dump` archive and therefore
requires the PostgreSQL client tools on the application server.

A checksum proves that the backup file was written consistently; it does not prove
that the business can restore it. Schedule a restore drill into a separate test
database and private-media location, then document the date and result.

## Health endpoints

- `/health/live/` confirms that the web process can answer requests without using the database.
- `/health/ready/` confirms that Django can complete a read-only database query.
- `/healthz/` remains a backwards-compatible alias for readiness monitoring.

All health responses are non-cacheable and excluded from search indexing. They
also report the revision stored by the completed release workflow.

A reverse proxy can use `/health/ready/` for upstream readiness. External uptime
monitoring should normally check both `/health/ready/` and a real public page such
as `/catalog/`.

## Request correlation and customer-safe errors

Every response includes `X-Request-ID`. A customer or staff member can provide
that value when reporting an error, allowing the related request to be located in
proxy and Gunicorn logs. A safe incoming request ID is retained; malformed values
are replaced.

Customer-facing 400, 403, 404 and 500 pages show the same support reference and
avoid database-dependent context processors. Private pages and error responses are
non-cacheable and excluded from indexing.

## Release verification

After deployment:

```bash
curl -I https://leosoftug.com/
curl -I https://leosoftug.com/catalog/
curl -sS https://leosoftug.com/health/ready/
```

Confirm that public responses include `X-Request-ID`, private pages use
`Cache-Control: private, no-store`, the health response reports the deployed Git
revision, and static asset URLs contain content hashes.

## Failure handling

- Do not restart Gunicorn after checks, backups, migrations or static collection fail.
- Do not use `git reset --hard` on the production checkout.
- Capture `journalctl -u leosoft_gunicorn -n 100 --no-pager` when workers fail.
- Correct the underlying environment or code issue, then rerun the same release script.
- Database restoration should use a verified backup and a documented maintenance window.
