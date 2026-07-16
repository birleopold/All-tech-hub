# Phase 3 — Durable marketing and customer automation

This phase replaces the old status-only scheduler with a database-backed automation queue.

## What is implemented

### Durable jobs

Every automated action now has a persistent `AutomationJob` record containing:

- a unique idempotency key;
- job type;
- queued, running, retrying, succeeded, failed or cancelled status;
- attempt count and maximum attempts;
- next retry time;
- worker lock and worker identity;
- safe payload and result metadata;
- last error and completion time.

A server restart does not erase queued or retrying work. Running jobs whose worker disappears are recovered after the stale-lock period.

### Per-channel social delivery

Each scheduled post receives one `PostChannelDelivery` record per selected channel.

A post can therefore show outcomes such as:

```text
Facebook: Published
Instagram: Retrying
WhatsApp: Manual action required
```

The whole post is marked published only when every selected channel is recorded as published. Mixed results remain partial or manual-ready instead of pretending that all platforms succeeded.

### Automatic channels

The first official connectors are:

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

### Email retry protection

Consented saved-cart reminders and triggered stock/price alerts now enter the same durable queue. Email exceptions are recorded and retried with exponential backoff instead of being silently counted and forgotten.

### Retry policy

The default maximum is five attempts:

```dotenv
ALLTECH_AUTOMATION_JOB_MAX_ATTEMPTS=5
```

Retry delays increase approximately as follows:

```text
1 minute
2 minutes
4 minutes
8 minutes
16 minutes
```

The delay is capped at six hours. Permanent permission, configuration and validation failures are not retried automatically.

## Safe Meta setup

Complete the official Meta Business and developer setup outside LEOSOFT before enabling automatic publishing.

You need:

1. a Meta developer application owned by the correct business;
2. the official Facebook Page ID;
3. an Instagram professional account connected through the Meta business setup;
4. the Instagram account ID used by the Instagram Platform;
5. the required approved publishing permissions for the app and business;
6. a valid Page access token suitable for the approved publishing workflow;
7. the Graph API version shown as supported for that Meta application.

Never paste the access token into chat, a support ticket, GitHub, Django admin or a scheduled-post caption.

Store it only in the protected production `.env` file.

## Environment variables

Keep publishing disabled during deployment and testing:

```dotenv
ALLTECH_META_AUTO_PUBLISH_ENABLED=0
ALLTECH_META_GRAPH_VERSION=v23.0
ALLTECH_META_PAGE_ID=""
ALLTECH_META_INSTAGRAM_ACCOUNT_ID=""
ALLTECH_META_PAGE_ACCESS_TOKEN=""
ALLTECH_AUTOMATION_JOB_MAX_ATTEMPTS=5
ALLTECH_AUTOMATION_HTTP_TIMEOUT_SECONDS=20
```

After the IDs, token, app permissions and test account are verified, enable the connector:

```dotenv
ALLTECH_META_AUTO_PUBLISH_ENABLED=1
```

The Graph version is deliberately configurable. Confirm the version in the Meta developer dashboard before production use and update it before Meta retires that version.

Protect `.env`:

```bash
chmod 600 /home/admin/All-tech-hub/.env
```

## How scheduled posts work

In the scheduled-post form, choose:

```text
Manual publishing
```

or:

```text
Automatic where connected
```

Automatic mode is the staff approval to publish when the selected time arrives.

For Instagram, the post must have either:

- a selected product with a public product image; or
- a public HTTPS media URL entered in the form.

Facebook can publish an image caption or a message/link post. Channels without an approved connector become `Manual action required` rather than failing the whole post.

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

Add to `.env`:

```dotenv
ALLTECH_META_AUTO_PUBLISH_ENABLED=0
ALLTECH_AUTOMATION_JOB_MAX_ATTEMPTS=5
ALLTECH_AUTOMATION_HTTP_TIMEOUT_SECONDS=20
```

Load the environment again:

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

Confirm the database role no longer has `CREATEDB`:

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
```

Run one cycle manually:

```bash
sudo systemctl start leosoft-marketing-posts.service
sudo systemctl status leosoft-marketing-posts.service --no-pager -l
sudo journalctl -u leosoft-marketing-posts.service -n 100 --no-pager
```

Confirm the one-minute schedule:

```bash
sudo systemctl list-timers leosoft-marketing-posts.timer --no-pager
```

## Test without Meta credentials

Create a post with:

```text
Publish mode: Automatic where connected
Channels: Facebook, Instagram, WhatsApp
Status: Scheduled
Schedule: a few minutes in the future
```

With Meta disabled, the due post must become ready and show each channel as manual/configuration-required. It must not claim to have published anything.

Run:

```bash
python manage.py run_automation_jobs --dry-run
python manage.py run_automation_jobs
```

## Test the Meta connector

After the official setup is ready:

1. add the Page ID, Instagram account ID, access token and supported Graph version to `.env`;
2. keep the production post small and non-sensitive;
3. restart Gunicorn and the timer;
4. run the configuration check;
5. schedule Facebook only first;
6. confirm the external post ID and public URL are recorded;
7. then test Instagram using a public product image;
8. only then begin scheduling normal campaigns.

Commands:

```bash
set -a
source .env
set +a

python manage.py check_marketing_integrations --require-meta
sudo systemctl restart leosoft_gunicorn
sudo systemctl restart leosoft-marketing-posts.timer
python manage.py run_automation_jobs --dry-run
```

Do not test by reusing the same production post repeatedly. Each successful channel delivery is idempotent and will not be published twice by an ordinary worker retry.

## Failed jobs

Inspect failures:

```bash
python manage.py shell -c \
  "from automation.models import AutomationJob; print(list(AutomationJob.objects.filter(status='failed').values('idempotency_key','last_error')[:20]))"
```

After correcting the token, permissions, SMTP or network problem, requeue failed jobs:

```bash
python manage.py retry_failed_automation_jobs --limit 100
python manage.py run_automation_jobs --process-only
```

The staff marketing dashboard also shows queued, running, failed, published and manual-delivery counts. Detailed records are read-only under Django admin automation diagnostics.

## Security rules

- never store Meta tokens in the database;
- never include tokens in job payloads or logs;
- never commit `.env`;
- never automate a personal Facebook profile;
- never use a personal Facebook or Instagram password in server code;
- verify webhook or callback signatures before trusting future inbound integrations;
- keep Meta publishing disabled when permissions or token ownership are uncertain;
- rotate a token immediately if it is exposed;
- use a dedicated test post before normal campaign publishing.

## Rollback

Stop the worker first:

```bash
sudo systemctl disable --now leosoft-marketing-posts.timer
```

Disable external publishing:

```dotenv
ALLTECH_META_AUTO_PUBLISH_ENABLED=0
```

Restart Gunicorn after changing the environment:

```bash
sudo systemctl restart leosoft_gunicorn
```

The automation tables should normally be retained during a code rollback because they contain the delivery and retry audit trail. Do not reverse the migration after real jobs or social deliveries have been recorded unless a verified backup exists and the data-loss impact is accepted.
