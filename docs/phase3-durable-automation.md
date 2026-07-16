# Phase 3 — Durable marketing and customer automation

This phase replaces the old status-only scheduler with a database-backed automation queue.

## What is implemented

### Durable jobs

Every automated action now has an `AutomationJob` record containing:

- a unique idempotency key;
- job type;
- queued, running, retrying, succeeded, failed or cancelled status;
- attempt count and maximum attempts;
- next retry time;
- worker lock and worker identity;
- safe payload and result metadata;
- last error and completion time.

A server restart does not erase queued or retrying work. Running jobs whose worker disappears can be recovered after the stale-lock period.

### Per-channel social delivery

Each scheduled post receives one delivery record per selected channel. A post can therefore show:

```text
Facebook: Published
Instagram: Retrying
WhatsApp: Manual action required
```

The whole post becomes `Published` only when every selected channel has a recorded published result. Mixed outcomes remain partial, failed or manual-ready.

### Automatic channels

The first official connector paths are:

- Facebook Page publishing through the Meta Graph API;
- Instagram professional-account image publishing through the Instagram Platform.

The following remain manual in this release:

- WhatsApp Status;
- TikTok;
- X;
- LinkedIn;
- YouTube;
- Telegram;
- Pinterest;
- bulk email campaigns.

The system does not use browser automation, personal social-media passwords or unofficial WhatsApp libraries.

### Email retries

Consented saved-cart reminders and triggered stock or price alerts enter the durable queue. Email exceptions are recorded and retried with exponential backoff instead of being silently counted and discarded.

## Delivery guarantee

The database guarantees that LEOSOFT does not intentionally create duplicate queue jobs for the same post/channel, saved-cart reminder or stock alert.

External APIs and SMTP are still **at-least-once integrations**. A rare network failure can occur after a provider accepts a post or email but before LEOSOFT receives the response. In that ambiguous case:

1. inspect the external platform and the automation error;
2. confirm whether the content was already published or sent;
3. record the outcome manually when appropriate;
4. requeue only after verifying that a duplicate will not be created.

Do not describe external delivery as mathematically exactly-once.

## Retry policy

The default maximum is five attempts:

```dotenv
ALLTECH_AUTOMATION_JOB_MAX_ATTEMPTS=5
```

Retry delays begin at approximately one minute and double, capped at six hours. Permission, missing-credential and validation failures are treated as permanent rather than retried endlessly.

## Safe Meta setup

Complete the official Meta Business and developer setup outside LEOSOFT before enabling automatic publishing.

You need:

1. a Meta developer application owned by the correct business;
2. the official Facebook Page ID;
3. an Instagram professional account connected through the Meta business setup;
4. the Instagram account ID used by the Instagram Platform;
5. approved publishing permissions for the app and business;
6. a valid Page access token for that approved workflow;
7. a Graph API version supported by the connected Meta application.

Never paste the access token into chat, a support ticket, GitHub, Django admin or a scheduled-post caption. Store it only in the protected production `.env` file.

## Environment variables

Keep publishing disabled during initial deployment:

```dotenv
ALLTECH_META_AUTO_PUBLISH_ENABLED=0
ALLTECH_META_GRAPH_VERSION=v23.0
ALLTECH_META_PAGE_ID=""
ALLTECH_META_INSTAGRAM_ACCOUNT_ID=""
ALLTECH_META_PAGE_ACCESS_TOKEN=""
ALLTECH_AUTOMATION_JOB_MAX_ATTEMPTS=5
ALLTECH_AUTOMATION_HTTP_TIMEOUT_SECONDS=20
```

`ALLTECH_META_GRAPH_VERSION` is configurable because supported Meta versions change. Confirm the version shown in the developer dashboard before enabling production publishing.

Protect `.env`:

```bash
chmod 600 /home/admin/All-tech-hub/.env
```

## Scheduled-post behaviour

The form now offers:

```text
Manual publishing
```

or:

```text
Automatic where connected
```

Automatic mode is the staff approval to publish when the scheduled time arrives.

Instagram requires either a selected product with a public image or a public HTTPS media URL. Facebook can publish an image caption or a message/link post. Channels without an approved connector become `Manual action required` rather than failing the whole post.

A post that was already processed while Meta was disabled remains ready/manual. After credentials are configured, edit the post, set its status back to `Scheduled`, confirm automatic mode and save it again.

## Deployment

### 1. Back up production

```bash
cd /home/admin/All-tech-hub
source .venv/bin/activate
set -a
source .env
set +a

python manage.py backup_alltech --output /home/admin/All-tech-hub/backups
python manage.py verify_alltech_backup
```

### 2. Pull and install

```bash
git checkout main
git pull origin main
pip install -r requirements.lock
```

### 3. Keep external publishing disabled initially

Add or confirm in `.env`:

```dotenv
ALLTECH_META_AUTO_PUBLISH_ENABLED=0
ALLTECH_AUTOMATION_JOB_MAX_ATTEMPTS=5
ALLTECH_AUTOMATION_HTTP_TIMEOUT_SECONDS=20
```

Reload the environment:

```bash
set -a
source .env
set +a
```

### 4. Validate migrations and tests

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py check
python manage.py check --deploy
python manage.py check_marketing_integrations
```

The plan should include:

```text
automation.0001_initial
```

Run tests before applying the production migration:

```bash
sudo -u postgres psql -c "ALTER ROLE leosoft_user CREATEDB;"

set +e
python manage.py test \
  automation \
  reliability \
  core.test_phase1_security \
  growth.test_growth \
  marketing.test_automation \
  catalog.test_watermarks \
  catalog.test_discovery
TEST_EXIT=$?
set -e

sudo -u postgres psql -c "ALTER ROLE leosoft_user NOCREATEDB;"

if [ "$TEST_EXIT" -ne 0 ]; then
  echo "Tests failed. Do not migrate or restart production."
  exit "$TEST_EXIT"
fi
```

Confirm the privilege was removed:

```bash
sudo -u postgres psql -tAc \
  "SELECT rolcreatedb FROM pg_roles WHERE rolname='leosoft_user';"
```

Expected:

```text
f
```

### 5. Migrate and restart

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager -l
curl -fsS https://leosoftug.com/healthz/
```

### 6. Install the durable worker timer

```bash
sudo cp deployment/leosoft-marketing-posts.service /etc/systemd/system/
sudo cp deployment/leosoft-marketing-posts.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now leosoft-marketing-posts.timer
sudo systemctl restart leosoft-marketing-posts.timer
sudo systemctl start leosoft-marketing-posts.service
```

Verify:

```bash
sudo systemctl status leosoft-marketing-posts.service --no-pager -l
sudo systemctl list-timers leosoft-marketing-posts.timer --no-pager
sudo journalctl -u leosoft-marketing-posts.service -n 100 --no-pager
```

### 7. Install automation health monitoring

```bash
sudo cp deployment/leosoft-automation-health.service /etc/systemd/system/
sudo cp deployment/leosoft-automation-health.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now leosoft-automation-health.timer
sudo systemctl start leosoft-automation-health.service
```

Verify:

```bash
python manage.py check_automation_health --json
sudo systemctl status leosoft-automation-health.service --no-pager -l
sudo systemctl list-timers leosoft-automation-health.timer --no-pager
sudo journalctl -u leosoft-automation-health.service -n 100 --no-pager
```

The health check fails when the queue is not draining, a worker lock is stale or a permanent failure needs investigation.

## Test with Meta disabled

Create a post with:

```text
Publish mode: Automatic where connected
Channels: Facebook, Instagram, WhatsApp
Status: Scheduled
Schedule: a few minutes in the future
```

With Meta disabled, the due post must become ready and show manual/configuration-required outcomes. It must not claim to have published anything.

```bash
python manage.py run_automation_jobs --dry-run
python manage.py run_automation_jobs
```

## Test the Meta connector

After official setup is complete:

1. add the Page ID, Instagram account ID, Page access token and supported Graph version to `.env`;
2. set `ALLTECH_META_AUTO_PUBLISH_ENABLED=1`;
3. restart Gunicorn and the worker timer;
4. run the integration check;
5. schedule a small Facebook-only test post;
6. verify the external post ID and public URL;
7. test Instagram using a public product image;
8. begin normal scheduling only after both tests are confirmed.

```bash
set -a
source .env
set +a

python manage.py check_marketing_integrations --require-meta
sudo systemctl restart leosoft_gunicorn
sudo systemctl restart leosoft-marketing-posts.timer
python manage.py run_automation_jobs --dry-run
```

## Failed jobs

Inspect failures through the marketing dashboard or the read-only automation diagnostics in Django admin.

After correcting the token, permissions, SMTP or network problem, first verify that the provider did not already accept an ambiguous delivery. Then requeue:

```bash
python manage.py retry_failed_automation_jobs --limit 100
python manage.py run_automation_jobs --process-only
```

## Security rules

- never store Meta tokens in the database;
- never include tokens in job payloads or logs;
- never commit `.env`;
- never automate a personal Facebook profile;
- never use a personal social-media password in server code;
- keep Meta publishing disabled when permissions or token ownership are uncertain;
- rotate a token immediately if it is exposed;
- use a dedicated test post before normal campaign publishing.

## Rollback

Stop the worker and health timers:

```bash
sudo systemctl disable --now leosoft-marketing-posts.timer
sudo systemctl disable --now leosoft-automation-health.timer
```

Disable external publishing:

```dotenv
ALLTECH_META_AUTO_PUBLISH_ENABLED=0
```

Restart Gunicorn:

```bash
sudo systemctl restart leosoft_gunicorn
```

Retain the automation tables during a normal code rollback because they contain delivery and retry history. Do not reverse the migration after real jobs or social deliveries have been recorded unless a verified backup exists and the data-loss impact is accepted.
