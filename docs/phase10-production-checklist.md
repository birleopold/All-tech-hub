# Phase 10 production checklist

Use this checklist to deploy the automation control center and recovery controls. The full design and operating rules are in `docs/phase10-automation-control-center.md`.

## 1. Stop timer-driven automation

Stop the timer before pulling code or applying the migration:

```bash
sudo systemctl stop leosoft-marketing-posts.timer
sudo systemctl stop leosoft-marketing-posts.service || true
sudo systemctl status leosoft-marketing-posts.timer --no-pager -l
```

The timer must remain stopped during the migration window because the updated `run_growth_automation` command expects the new automation-control tables.

## 2. Back up and verify

```bash
cd /home/admin/All-tech-hub
source .venv/bin/activate
set -a
source .env
set +a

python manage.py backup_alltech \
  --output /home/admin/All-tech-hub/backups
python manage.py verify_alltech_backup
```

Do not continue if verification fails.

## 3. Add control thresholds

Add or confirm in `.env`:

```dotenv
ALLTECH_AUTOMATION_JOB_MAX_ATTEMPTS=5
ALLTECH_AUTOMATION_HTTP_TIMEOUT_SECONDS=20
ALLTECH_AUTOMATION_HEARTBEAT_MAX_AGE_MINUTES=30
ALLTECH_AUTOMATION_STALE_JOB_MINUTES=15
```

Keep existing campaign delivery switches unchanged during deployment. The safest values remain:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
ALLTECH_CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED=0
```

Reload:

```bash
set -a
source .env
set +a
```

## 4. Pull and install

```bash
git checkout main
git pull origin main
pip install -r requirements.lock
```

## 5. Validate before migration

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py check
python manage.py check --deploy
```

The migration plan must include:

```text
automation.0002_control_runs_job_events
```

## 6. Run PostgreSQL release tests

Temporarily allow Django to create the test database:

```bash
sudo -u postgres psql -c \
  "ALTER ROLE leosoft_user CREATEDB;"
```

Run the release scope:

```bash
set +e

python manage.py test \
  automation \
  growth.test_growth \
  customer_campaigns \
  loyalty.test_loyalty \
  commerce.test_customer_messages \
  commerce.test_retention \
  reports.test_retention \
  reports.test_conversion

TEST_EXIT=$?
set -e

sudo -u postgres psql -c \
  "ALTER ROLE leosoft_user NOCREATEDB;"

if [ "$TEST_EXIT" -ne 0 ]; then
  echo "Phase 10 tests failed. Keep the automation timer stopped and do not migrate."
  exit "$TEST_EXIT"
fi
```

Confirm the temporary privilege was removed:

```bash
sudo -u postgres psql -tAc \
  "SELECT rolcreatedb FROM pg_roles WHERE rolname='leosoft_user';"
```

Expected:

```text
f
```

## 7. Apply migration and roles

```bash
python manage.py migrate --noinput
python manage.py bootstrap_roles
```

The `Manager` group now receives automation-control permissions. Review actual membership before giving anyone operational recovery access:

```bash
python manage.py shell -c \
"from django.contrib.auth.models import Group; g=Group.objects.get(name='Manager'); print(list(g.user_set.values_list('username', flat=True)))"
```

## 8. Create the first heartbeat safely

Run the established worker command in dry mode:

```bash
python manage.py run_growth_automation --dry-run --limit 20
```

This creates an `AutomationRun` and fresh heartbeat but does not queue, publish or send anything.

Inspect:

```bash
python manage.py audit_automation_control --json
```

## 9. Review historical dead letters

The strict audit intentionally fails while any `AutomationJob` remains `Failed`.

Open:

```text
https://leosoftug.com/staff/reports/automation-control/
```

The page may require Gunicorn to be restarted first. It is acceptable to restart the web app while the timer remains stopped:

```bash
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager -l
curl -fsS https://leosoftug.com/healthz/
```

For each failed job:

### Saved-cart or stock-alert email

1. Correct the SMTP, customer-record or product condition.
2. Review the payload and prior error.
3. Enter `REPLAY <job ID>` only when replay is appropriate.
4. Leave the timer stopped until all review work is complete.

The existing executor will re-check whether the reminder or alert is still required.

### Facebook or Instagram post

1. Check the external Facebook Page or Instagram account.
2. Do not replay the failed job from the control center.
3. Rebuild the scheduled post only when no external post exists.
4. Enter `CANCEL <job ID>` with a clear review note to close the failed record.

Running jobs must not be cancelled. Inspect the external or email evidence first.

## 10. Run strict release gates

After dead-letter review:

```bash
python manage.py run_growth_automation --dry-run --limit 20
python manage.py audit_automation_control --strict
python manage.py audit_customer_campaigns --strict
python manage.py audit_consent_loyalty --strict
```

The automation audit must report:

```text
integrity errors: 0
```

Do not restart the timer when:

- a heartbeat is stale;
- a job is stuck running;
- a failed job remains unreviewed;
- a run remains stuck in `Running`;
- the control record contains an unexplained pause.

## 11. Run production health checks

```bash
python manage.py check_operational_health --json
```

This now checks automation heartbeat, stale locks and dead letters in addition to database, backups, disk, private files and reservations.

A missing backup or other existing operational issue will also fail this command and must be reviewed separately.

## 12. Verify the control center

Open:

```text
https://leosoftug.com/staff/reports/automation-control/
```

Confirm:

1. Last heartbeat is fresh.
2. Last run is `Dry run`.
3. No stale locks exist.
4. No dead letters remain.
5. Recent run history appears.
6. A Manager can view pause and recovery controls.
7. An unauthorised staff user receives HTTP 403.
8. Pages use private no-store and noindex headers.

Do not test replay with a real customer email or social post during deployment.

## 13. Restart timer

Verify the service definitions:

```bash
sudo systemctl cat leosoft-marketing-posts.service
sudo systemctl cat leosoft-marketing-posts.timer
```

The service must still invoke:

```text
python manage.py run_growth_automation
```

Restart:

```bash
sudo systemctl daemon-reload
sudo systemctl start leosoft-marketing-posts.timer
sudo systemctl status leosoft-marketing-posts.timer --no-pager -l
sudo systemctl list-timers --all | grep leosoft-marketing-posts
```

## 14. Confirm a real timer heartbeat

After the next scheduled timer cycle, inspect:

```bash
sudo journalctl -u leosoft-marketing-posts.service -n 100 --no-pager
python manage.py audit_automation_control --strict
python manage.py check_operational_health --json
```

The control center should show a new `Timer` run and a heartbeat newer than 30 minutes.

## Normal emergency stop

Use the control center and enter:

```text
PAUSE AUTOMATION
```

Record the incident or maintenance reason. The timer continues to heartbeat in inspection-only mode while no new automation work is queued or executed.

## Hard infrastructure stop

When the web interface is unavailable or an active incident requires infrastructure isolation:

```bash
sudo systemctl stop leosoft-marketing-posts.timer
sudo systemctl stop leosoft-marketing-posts.service || true
sudo journalctl -u leosoft-marketing-posts.service -n 200 --no-pager
```

After recovery:

1. Inspect every running or failed job.
2. Run a dry worker cycle.
3. Run the strict automation audit.
4. Restart the timer only when the audit is green.

## Rollback note

If application rollback is required after migration, stop the timer first. The new tables are additive and may remain in the database while code is rolled back, but older code will not update heartbeat or run evidence. Do not leave older code operating indefinitely with the Phase 10 schema because monitoring will correctly report a stale heartbeat.
