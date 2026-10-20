# LEOSOFT three-point verified local backup retention

Production remains on the existing `leosoft-backup.timer` (daily ~02:30 VPS local
time) and `leosoft-backup.service`. The command
`deployment/run-backup.sh` still invokes `backup_project --include-media`.
Legacy 30-day deletion is explicitly disabled. Once the new backup completes,
is checksummed, and (if enabled) offsite copying succeeds, the script runs
`deployment/rotate-verified-backups.py`.

## Recovery-point policy
- Latest verified backup: **daily**.
- Most recent distinct backup from a previous ISO week: **weekly**.
- Most recent distinct backup from a previous calendar month: **monthly**.
- Exactly three **checksum-verified** points remain *when suitable history
  exists*. During creation there may temporarily be a fourth.
- A backup whose checksum or manifest fails is never auto-deleted; investigate
  and manually isolate it before enforcing a strict three-directory limit.
- If a weekly or monthly distinct point is not available, rotation is skipped
  rather than deleting the only usable history.
- Checksums prove archive consistency, not restorable data. Perform periodic
  restoration drills and keep an off-VPS copy.

## First deployment: PREVIEW only

```bash
cd /home/admin/All-tech-hub
git pull --ff-only origin main
.venv/bin/python deployment/rotate-verified-backups.py --root /home/admin/All-tech-hub/backups
```

Review the KEEP, UNVERIFIED, and ELIGIBLE output before proceeding.
To remove *only* checksum-valid extras after reviewing the preview:

```bash
.venv/bin/python deployment/rotate-verified-backups.py --root /home/admin/All-tech-hub/backups --apply
```

Be aware that this permanently removes old local copies. Confirm an independent
offsite backup first if you need disaster recovery.

## Enable automatic pruning after a successful full backup

The daily service is deliberately in preview mode by default. Add
`ALLTECH_BACKUP_ROTATE_APPLY=true` to the existing, protected
`/home/admin/All-tech-hub/.env` (not Git), then restart the timer scheduling
with `sudo systemctl daemon-reload` and
`sudo systemctl restart leosoft-backup.timer`. The service's EnvironmentFile
already loads that variable. Automatic pruning happens **only after** the
backup and any enabled offsite upload complete successfully.

Do not run the backup service simultaneously with manual rotation; the timer
may be checked with `systemctl list-timers leosoft-backup.timer`.

Verification requires a non-empty database file, a media archive, and hashes
matching manifest.json. Old backups without valid manifests are preserved.
