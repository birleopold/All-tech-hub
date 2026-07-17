# Phase 9 — Scheduled campaign operations and delivery-health controls

Phase 9 extends the Phase 8 controlled customer email workflow with safe future scheduling, approval expiry, pause and resume controls, bounded automated batches, append-only automation evidence and automatic delivery-health pauses.

It does not enable customer delivery by itself. Both independent production switches remain off by default.

## Safety model

Scheduled execution requires both:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=1
ALLTECH_CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED=1
```

The first switch controls all customer campaign delivery. The second switch controls timer-driven scheduled execution only.

This separation means:

- turning off `SEND_ENABLED` stops manual and scheduled delivery;
- turning off `SCHEDULER_ENABLED` stops scheduled batches while leaving the already controlled manual workflow available;
- leaving either switch off prevents automatic delivery;
- an approved campaign is not automatically scheduled;
- scheduling requires a separate exact confirmation phrase.

Recommended initial production values are:

```dotenv
ALLTECH_PUBLIC_BASE_URL=https://leosoftug.com
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

## Campaign states

Phase 9 supports:

```text
draft
prepared
approved
scheduled
sending
paused
completed
cancelled
expired
failed
```

### Approved

A different authorised staff member has reviewed the campaign. Approval now receives an expiry time.

Default validity:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_APPROVAL_VALID_HOURS=48
```

An approved campaign must be manually processed or scheduled before that approval expires.

### Scheduled

Scheduling requires the exact phrase:

```text
SCHEDULE <campaign ID>
```

Staff must select:

- the first run time;
- the bounded automated batch size;
- a time before approval expiry;
- a time inside the configured maximum lead window.

Default lead window:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SCHEDULE_MAX_LEAD_HOURS=24
```

Scheduling records:

- who scheduled it;
- when it was scheduled;
- the original requested time;
- the next due run;
- batch size;
- approval expiry;
- an append-only scheduling event.

Saving a schedule does not bypass either kill switch.

### Sending

The scheduler claims a due campaign and moves it briefly to `sending` while processing one bounded batch.

A scheduled campaign cannot be manually processed from the Phase 8 action. Manual and automated delivery modes are intentionally separate.

### Paused

A scheduled campaign can be paused with:

```text
PAUSE <campaign ID>
```

A pause requires a reason. The system also pauses automatically when:

- a recipient remains in an uncertain processing state;
- a processing delivery needs manual review;
- delivery failures cross the configured circuit-breaker threshold;
- an automation operation fails safely.

A campaign cannot be paused or cancelled while an active recipient is processing. Staff must first disable the switches and reconcile the delivery evidence.

### Resume

A paused campaign can be resumed with:

```text
RESUME <campaign ID>
```

The new run time must remain before approval expiry. Expired approval cannot be resumed.

### Expired

When approval expires:

- remaining pending recipients are suppressed;
- the suppression reason becomes `campaign_approval_expired`;
- automated delivery is disabled for that campaign;
- the campaign becomes `expired`;
- an append-only expiry event is recorded.

If a recipient is processing when approval expires, the campaign pauses for manual review instead of falsely suppressing an uncertain delivery.

## Bounded automated batches

Default scheduled batch size:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE=1
```

The configured value is the server-side maximum. A campaign cannot schedule a larger automated batch.

After a successful bounded run with pending recipients, the next run becomes due after:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_AUTOMATION_INTERVAL_MINUTES=15
```

The existing `run_growth_automation` command now also invokes the scheduled campaign service. Therefore, an existing systemd timer that runs this command can process due campaigns without introducing another timer unit.

The scheduler can also be run directly:

```bash
python manage.py run_customer_campaign_scheduler --dry-run --json
python manage.py run_customer_campaign_scheduler --limit 10
```

Dry-run mode reports due and expired work without changing records or delivering anything.

## Final consent validation

Phase 8 consent safeguards remain active for every automated recipient.

Immediately before delivery, LEOSOFT checks:

- the customer still exists;
- the current email still matches the prepared snapshot;
- email consent remains active;
- the selected topic remains active;
- consent was not withdrawn;
- the latest append-only consent event supports the channel and topic;
- the campaign approval remains valid.

A failed check suppresses the recipient instead of delivering.

## Duplicate-delivery protection

Before SMTP submission:

1. the recipient is row-locked and claimed;
2. consent is checked;
3. a queued `OutboundEmail` record is created;
4. that record is linked to the recipient;
5. SMTP submission occurs;
6. the final delivery result is written back.

If the application stops after SMTP may have accepted the email, the linked queued record remains in `processing`. It is not automatically retried.

The scheduler pauses when uncertain linked processing evidence exists. Generic email-log retry remains blocked for campaign-linked messages.

## Delivery-health circuit breaker

The scheduler calculates cumulative delivery attempts as:

```text
sent + failed
```

It pauses remaining scheduled delivery when both conditions are true:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_FAILURE_MIN_ATTEMPTS=3
ALLTECH_CUSTOMER_CAMPAIGN_FAILURE_RATE_PERCENT=50
```

With these defaults, once at least three delivery attempts exist, a failure rate of 50 percent or higher pauses the campaign when pending recipients remain.

The pause reason is:

```text
delivery_failure_rate_circuit_breaker
```

Staff must investigate SMTP, sender reputation, recipient quality and outbound logs before resuming.

## Append-only automation history

`CampaignAutomationEvent` records:

```text
scheduled
batch_started
batch_finished
paused
resumed
expired
completed
failed
cancelled
```

Each event can contain:

- campaign;
- action;
- staff actor or system actor;
- message;
- structured metadata;
- event time.

Django admin exposes campaigns, recipients and automation events as read-only evidence.

## Staff interface

Open:

```text
/staff/reports/customer-campaigns/
```

Campaign detail now shows:

- delivery-switch state;
- scheduler-switch state;
- approval expiry;
- original schedule;
- next run;
- automated batch size;
- number of automated runs;
- pause reason;
- automation event history;
- recipient-level consent and delivery evidence.

Access still requires:

```text
marketing.change_marketingcampaign
```

## Strict audit

Run:

```bash
python manage.py audit_customer_campaigns --json
python manage.py audit_customer_campaigns --strict
```

The Phase 9 audit checks for:

- missing approval evidence;
- active approvals without expiry;
- active campaigns whose approval is already expired;
- creator or preparer self-approval;
- scheduled campaigns without schedule fields;
- scheduled campaigns without a scheduling event;
- paused campaigns without a reason or pause event;
- expired campaigns with pending recipients;
- completed scheduled campaigns without a completion event;
- automation batch sizes above configuration;
- invalid automated-delivery states;
- stale processing recipients;
- completed campaigns with unfinished recipients;
- successful-recipient records without successful outbound evidence;
- delivered messages without an unsubscribe path;
- stale consent or changed email addresses;
- counter mismatches;
- prepared-recipient limit violations;
- automation run counts that disagree with batch-start events.

Overdue schedules are reported as warnings. They usually mean the timer is disabled, the service is failing, or both delivery switches are not active.

## Database migration

Phase 9 adds:

```text
customer_campaigns.0002_scheduled_campaign_operations
```

It adds schedule fields and `CampaignAutomationEvent`.

For compatibility, existing active approved or sending campaigns receive a 48-hour approval-expiry timestamp based on their recorded approval time. Historical campaigns are not scheduled and no delivery occurs during migration.

## Production deployment

### 1. Back up

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

Stop when backup verification fails.

### 2. Pull the code

```bash
git checkout main
git pull origin main
pip install -r requirements.lock
```

### 3. Keep both switches disabled

Add or confirm in `.env`:

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

Reload:

```bash
set -a
source .env
set +a
```

Confirm:

```bash
python manage.py shell -c \
  "from django.conf import settings; print(settings.CUSTOMER_CAMPAIGN_SEND_ENABLED, settings.CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED)"
```

Expected:

```text
False False
```

### 4. Validate migration state

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py check
python manage.py check --deploy
```

The plan should include:

```text
customer_campaigns.0002_scheduled_campaign_operations
```

### 5. Run PostgreSQL tests

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
  echo "Phase 9 tests failed. Do not migrate or restart production."
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

### 6. Apply migration and validate commands

```bash
python manage.py migrate --noinput
python manage.py run_customer_campaign_scheduler --dry-run --json
python manage.py audit_customer_campaigns --strict
python manage.py audit_consent_loyalty --strict
```

### 7. Publish and restart

```bash
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager -l
curl -fsS https://leosoftug.com/healthz/
```

### 8. Verify the existing automation timer

Inspect the deployed service and timer:

```bash
sudo systemctl cat leosoft-marketing-posts.service
sudo systemctl cat leosoft-marketing-posts.timer
sudo systemctl list-timers --all | grep leosoft-marketing-posts
```

The service should invoke:

```text
python manage.py run_growth_automation
```

No new systemd unit is required because that command now includes scheduled customer-campaign processing.

Run a safe dry check:

```bash
python manage.py run_growth_automation --dry-run --limit 20
```

### 9. Verify while disabled

Use internal staff and internal customer records only.

1. Create a draft.
2. Prepare a consent-safe audience.
3. Approve using a different staff member.
4. Schedule it with the exact phrase.
5. Confirm the detail page shows the schedule and event.
6. Run `run_customer_campaign_scheduler --dry-run --json`.
7. Confirm no delivery occurs while either switch is off.
8. Pause and resume the schedule.
9. Confirm every action appears in automation history.
10. Run the strict audit.

### 10. Controlled internal scheduled test

Do not first-enable scheduled execution for real customers.

Use one or two internal mailboxes controlled by LEOSOFT staff. Record explicit matching consent through the normal portal or checkout flow.

Temporarily use:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=1
ALLTECH_CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED=1
ALLTECH_CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=2
ALLTECH_CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE=1
ALLTECH_CUSTOMER_CAMPAIGN_AUTOMATION_INTERVAL_MINUTES=15
```

Reload and restart:

```bash
set -a
source .env
set +a
sudo systemctl restart leosoft_gunicorn
```

Prepare, approve and schedule a new internal campaign. Then either wait for the timer or run:

```bash
python manage.py run_customer_campaign_scheduler --limit 1
```

Verify:

- only one internal recipient is processed per run;
- the next run is scheduled only when recipients remain;
- the email contains the unsubscribe link;
- consent withdrawal before the next run causes suppression;
- campaign counters match recipient records;
- automation history contains batch-start and batch-finish or completion events;
- the strict audit reports zero errors.

After the internal test, return both switches to zero and restart Gunicorn.

## Emergency controls

### Stop all campaign delivery

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
ALLTECH_CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED=0
```

Reload `.env` and restart Gunicorn.

### Stop only scheduled execution

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED=0
```

Manual delivery remains controlled by the Phase 8 confirmation flow only when `SEND_ENABLED=1`.

### Investigate a processing recipient

Do not retry or cancel blindly.

1. Disable both switches.
2. Open the campaign recipient evidence.
3. Inspect the linked outbound log.
4. Determine whether SMTP accepted the message.
5. Reconcile the record through a reviewed database procedure if necessary.
6. Run the strict audit.
7. Resume only when no recipient remains in uncertain processing state.

## Operational rules

- Keep both switches disabled until the internal test passes.
- Start automated batches at one recipient.
- Never schedule beyond approval expiry.
- Never treat a schedule as permanent approval.
- Never manually edit campaign state or automation events in Django admin.
- Never automatically retry an uncertain queued delivery.
- Investigate every automatic health pause before resuming.
- Run the scheduler dry-run and strict audit during deployment.
- Keep WhatsApp delivery disabled until its own approved provider, template, callback and opt-out workflow exists.
