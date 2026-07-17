# Phase 9 production checklist

Use this checklist for the production rollout of scheduled customer campaigns. The detailed design and operating rules are in `docs/phase9-scheduled-campaign-operations.md`.

## 1. Stop timer-driven automation

Before pulling code or changing the database:

```bash
sudo systemctl stop leosoft-marketing-posts.timer
sudo systemctl stop leosoft-marketing-posts.service || true
sudo systemctl status leosoft-marketing-posts.timer --no-pager -l
```

The timer must be inactive during the code-and-migration window because `run_growth_automation` now imports the Phase 9 scheduler and expects migration `customer_campaigns.0002_scheduled_campaign_operations`.

## 2. Back up

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

## 3. Confirm both delivery switches are off

In `.env`:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
ALLTECH_CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED=0
ALLTECH_CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER=1
ALLTECH_CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=10
ALLTECH_CUSTOMER_CAMPAIGN_BATCH_SIZE=2
ALLTECH_CUSTOMER_CAMPAIGN_APPROVAL_VALID_HOURS=48
ALLTECH_CUSTOMER_CAMPAIGN_SCHEDULE_MAX_LEAD_HOURS=24
ALLTECH_CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE=1
ALLTECH_CUSTOMER_CAMPAIGN_AUTOMATION_INTERVAL_MINUTES=15
ALLTECH_CUSTOMER_CAMPAIGN_FAILURE_MIN_ATTEMPTS=3
ALLTECH_CUSTOMER_CAMPAIGN_FAILURE_RATE_PERCENT=50
```

Reload and verify:

```bash
set -a
source .env
set +a

python manage.py shell -c \
  "from django.conf import settings; print(settings.CUSTOMER_CAMPAIGN_SEND_ENABLED, settings.CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED)"
```

Expected:

```text
False False
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
customer_campaigns.0002_scheduled_campaign_operations
```

## 6. Run PostgreSQL release tests

```bash
sudo -u postgres psql -c \
  "ALTER ROLE leosoft_user CREATEDB;"

set +e
python manage.py test \
  customer_campaigns \
  growth.test_growth \
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
  echo "Phase 9 tests failed. Keep the timer stopped and do not migrate."
  exit "$TEST_EXIT"
fi
```

Confirm privilege removal:

```bash
sudo -u postgres psql -tAc \
  "SELECT rolcreatedb FROM pg_roles WHERE rolname='leosoft_user';"
```

Expected:

```text
f
```

## 7. Apply migration and run gates

```bash
python manage.py migrate --noinput
python manage.py run_customer_campaign_scheduler --dry-run --json
python manage.py audit_customer_campaigns --strict
python manage.py audit_consent_loyalty --strict
```

Do not restart automation when either strict audit fails.

## 8. Publish and restart the web app

```bash
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager -l
curl -fsS https://leosoftug.com/healthz/
```

## 9. Verify automation configuration

```bash
sudo systemctl cat leosoft-marketing-posts.service
sudo systemctl cat leosoft-marketing-posts.timer
```

The service should invoke:

```text
python manage.py run_growth_automation
```

Run a safe dry check:

```bash
python manage.py run_growth_automation --dry-run --limit 20
```

## 10. Restart the timer with both switches still off

```bash
sudo systemctl daemon-reload
sudo systemctl start leosoft-marketing-posts.timer
sudo systemctl status leosoft-marketing-posts.timer --no-pager -l
sudo systemctl list-timers --all | grep leosoft-marketing-posts
```

Starting the timer is safe while both campaign switches remain zero. It can expire stale approval records and process other established growth automation, but it cannot release scheduled customer campaign batches.

## 11. Disabled-mode verification

Using internal records only:

1. Create a campaign draft.
2. Prepare the consent-safe audience.
3. Approve with a different authorised staff member.
4. Schedule using the exact confirmation phrase.
5. Confirm schedule and event history appear.
6. Run `python manage.py run_customer_campaign_scheduler --dry-run --json`.
7. Confirm no customer campaign outbound record is created.
8. Pause and resume the schedule.
9. Run `python manage.py audit_customer_campaigns --strict`.

## 12. Controlled internal enablement

Only after disabled-mode verification passes, temporarily use one or two staff-controlled mailboxes:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=1
ALLTECH_CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED=1
ALLTECH_CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=2
ALLTECH_CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE=1
```

Reload and restart Gunicorn:

```bash
set -a
source .env
set +a
sudo systemctl restart leosoft_gunicorn
```

Schedule a new internal campaign and process one due campaign:

```bash
python manage.py run_customer_campaign_scheduler --limit 1
```

Verify delivery evidence, unsubscribe links, counters, notifications and the strict audit.

Return both switches to zero after the test and restart Gunicorn.

## Emergency stop

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
ALLTECH_CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED=0
```

Then:

```bash
set -a
source .env
set +a
sudo systemctl restart leosoft_gunicorn
```

Do not cancel or retry a campaign while any recipient remains `processing`. Inspect the linked outbound record first.
