# LEOSOFT Phase 1 hardening

This release begins the security, reliability and operational-hardening phase.
It must be deployed as one coordinated change because Django templates, protected
file views and Nginx media rules depend on one another.

## Included in this batch

- Privacy-safe service worker that never stores authenticated or customer HTML.
- Permission-checked ticket attachments, job photos and customer signatures.
- Nginx denial of direct URLs for protected upload directories.
- Authenticated Nginx `X-Accel-Redirect` delivery with private no-store headers.
- AES-GCM encryption for staff TOTP secrets without changing the database column.
- Password and current OTP verification before staff can disable 2FA.
- Audit events for 2FA enablement and disablement.
- Database, public-media and private-media backups.
- SHA-256 backup manifests and archive verification.
- Daily systemd backup timer with optional rclone off-site copying.
- Database, disk-space, backup-age and private-directory operational checks.
- Production hashed static filenames for safe immutable browser caching.
- Phase 1 regression tests and CI validation.

## Important boundaries

This first batch protects the known ticket and job upload routes. Company stamp
and signature files still need a dedicated private-storage migration because the
company logo currently shares their `media/company/` directory. Until that
migration is completed, do not upload a high-resolution legal signature or stamp
that would be unsafe if its media filename were discovered.

The health timer writes failures to systemd/journald. External alert delivery
(email, SMS, Slack or an uptime provider) must still be connected separately.

The optional off-site backup sync runs only after `ALLTECH_BACKUP_RCLONE_DEST`
is configured against an existing secure rclone remote.

## Before deployment

Create a fresh field-encryption key. Store it safely; changing or losing this key
after TOTP secrets have been encrypted will invalidate those records.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Add the generated value to `/home/admin/All-tech-hub/.env`:

```dotenv
ALLTECH_FIELD_ENCRYPTION_KEY="PASTE_THE_NEW_RANDOM_VALUE"
ALLTECH_PRIVATE_MEDIA_ROOT=/home/admin/All-tech-hub/private_media
ALLTECH_PRIVATE_MEDIA_USE_X_ACCEL=1
ALLTECH_BACKUP_ROOT=/home/admin/All-tech-hub/backups
```

Keep `.env` private:

```bash
chmod 600 /home/admin/All-tech-hub/.env
```

Prepare protected directories:

```bash
sudo install -d -m 700 -o admin -g admin /home/admin/All-tech-hub/private_media
sudo install -d -m 700 -o admin -g admin /home/admin/All-tech-hub/backups
```

## Deploy and test the Django changes first

```bash
cd /home/admin/All-tech-hub
git checkout main
git pull origin main

source .venv/bin/activate
set -a
source .env
set +a

pip install -r requirements.lock
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py check --deploy
python manage.py test core.test_phase1_security
python manage.py test \
  core.test_phase1_security \
  catalog.test_watermarks \
  catalog.test_discovery \
  catalog.test_social_marketing \
  growth.test_growth \
  marketing.test_automation
```

No database migration is expected from this batch.

## Encrypt existing staff authenticator secrets

Preview first:

```bash
python manage.py encrypt_staff_totp_secrets --dry-run
```

Create and verify a backup before modifying the records:

```bash
python manage.py backup_alltech --output /home/admin/All-tech-hub/backups
python manage.py verify_alltech_backup
```

Then encrypt existing plaintext secrets:

```bash
python manage.py encrypt_staff_totp_secrets
```

Do not change `ALLTECH_FIELD_ENCRYPTION_KEY` after this command.

## Build hashed static assets and restart Django

```bash
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager -l
curl -fsS https://leosoftug.com/healthz/
```

Open the public homepage, staff login, two-factor page, customer portal and one
product page before changing Nginx.

## Install the protected-media Nginx configuration

Only after the new Django routes and templates are running:

```bash
sudo cp /home/admin/All-tech-hub/deployment/nginx-leosoftug.com.conf \
  /etc/nginx/sites-available/leosoftug.com
sudo nginx -t
sudo systemctl reload nginx
```

Verify direct access is blocked:

```bash
curl -I https://leosoftug.com/media/tickets/test.txt
curl -I https://leosoftug.com/media/job_attachments/test.jpg
curl -I https://leosoftug.com/media/job_signatures/test.png
```

Each should return `404`. Then verify a real attachment still opens through its
staff or customer-portal **protected attachment** link.

Search for any old direct template references before considering this complete:

```bash
grep -RInE 'attachment\.url|a\.image\.url|customer_signature\.url' \
  templates core operations portal messaging || true
```

Review every match. Sensitive files must use one of the permission-checked named
URLs rather than a raw `/media/` URL.

## Install daily backups

```bash
sudo cp deployment/leosoft-backup.service /etc/systemd/system/
sudo cp deployment/leosoft-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now leosoft-backup.timer
sudo systemctl start leosoft-backup.service
sudo systemctl status leosoft-backup.service --no-pager -l
sudo journalctl -u leosoft-backup.service -n 100 --no-pager
sudo systemctl list-timers leosoft-backup.timer --no-pager
```

Confirm the server time zone so the scheduled 02:30 run is understood correctly:

```bash
timedatectl
```

## Install operational health checks

Run a successful backup first; otherwise backup freshness correctly fails.

```bash
sudo cp deployment/leosoft-healthcheck.service /etc/systemd/system/
sudo cp deployment/leosoft-healthcheck.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now leosoft-healthcheck.timer
sudo systemctl start leosoft-healthcheck.service
sudo systemctl status leosoft-healthcheck.service --no-pager -l
sudo journalctl -u leosoft-healthcheck.service -n 100 --no-pager
```

A manual JSON check is also available:

```bash
python manage.py check_operational_health --json
```

## Configure an off-site copy

Create and test an encrypted or otherwise access-controlled rclone remote before
setting the destination. Do not place remote credentials in Git.

```dotenv
ALLTECH_BACKUP_RCLONE_DEST=secure-remote:leosoft-production-backups
```

After editing `.env`, manually test:

```bash
sudo systemctl start leosoft-backup.service
sudo journalctl -u leosoft-backup.service -n 100 --no-pager
```

Confirm the database dump, public-media ZIP, private-media ZIP and manifest are
present in the remote destination.

## Two-factor acceptance test

1. Sign in as a non-superuser staff account with 2FA enabled.
2. Confirm the current authenticator code still works.
3. Open **Staff → Two-factor security**.
4. Try disabling with a wrong password; 2FA must remain enabled.
5. Disable with the current password and a fresh OTP; it should succeed and add
   a `security.2fa_disabled` audit event.
6. Re-enable 2FA before finishing the test.

## Rollback

Do not roll back only Nginx while leaving protected links untested. A safe
application rollback is:

1. Restore the previous application commit.
2. Re-run `collectstatic`.
3. Restart Gunicorn.
4. Restore the previous Nginx file only when templates again use direct media
   URLs.

Never restore an old database copy merely to roll back code unless a migration
or data transformation requires it. TOTP records encrypted with the new field
key remain readable by the new code; older code cannot authenticate against
those encrypted values.
