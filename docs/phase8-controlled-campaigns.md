# Phase 8 — Controlled customer email campaigns

Phase 8 turns the Phase 7 consent-safe audience data into a controlled email campaign workflow. It prevents accidental bulk delivery, stale-consent sends, permission bypasses and automatic duplicate delivery after interrupted requests.

Phase 8 supports customer email only. It does not send WhatsApp messages. WhatsApp remains audience-preview only until LEOSOFT has an approved provider, verified sender, template process, delivery callbacks and opt-out handling.

## Safety position

Production delivery is disabled by default:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
```

With the switch disabled, authorised staff can create, prepare, review, approve and cancel campaigns, but the server cannot release customer email.

The disabled HTML button is only a visual aid. The server checks the environment switch for every send request.

## Permission requirement

Campaign pages and actions always require:

```text
marketing.change_marketingcampaign
```

This permission is enforced even when the broader optional staff-role middleware is disabled. A staff account without the permission receives an access-denied response.

## Staff location

```text
/staff/reports/customer-campaigns/
```

The workflow appears in desktop and mobile staff navigation as **Customer email campaigns**.

## Lifecycle

### 1. Draft

A staff member defines:

- campaign name;
- optional reporting link to an existing marketing campaign;
- topic: product updates or special offers;
- segment: all, repeat, recent or dormant;
- subject;
- body;
- maximum recipients.

Supported placeholders:

```text
{customer_name}
{first_name}
{company}
{unsubscribe_url}
```

When the body omits `{unsubscribe_url}`, LEOSOFT appends the customer-specific preference link automatically.

Saving a draft sends nothing.

### 2. Prepare audience

Preparation creates a fixed recipient snapshot from customers who currently have:

- active email marketing consent;
- active consent for the selected topic;
- a current consent event supporting those choices;
- a recorded email address;
- the selected business segment.

A customer with only a Boolean preference flag and no consent event is excluded.

The snapshot records the customer, normalised email address, consent event and preparation time.

Preparation sends nothing. A prepared campaign can be rebuilt only before delivery activity begins.

### 3. Independent approval

The default control is:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER=1
```

The approver must be different from both the creator and preparer. Approval records the reviewer, time and optional note. Approval sends nothing.

### 4. Confirmed bounded delivery

The sender must enter:

```text
SEND <campaign ID>
```

One action releases no more than:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_BATCH_SIZE=10
```

A larger form value is reduced to the configured maximum.

The campaign preparation ceiling is:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=100
```

The application caps this setting at 500.

### 5. Final consent recheck

Immediately before each delivery LEOSOFT confirms:

- the customer still exists;
- the email still exists and matches the prepared snapshot;
- email consent remains active;
- selected-topic consent remains active;
- consent was not withdrawn;
- the latest consent event still supports the channel and topic.

A failed check suppresses the recipient instead of sending.

Typical suppression reasons:

```text
email_consent_withdrawn
topic_consent_withdrawn
email_changed_reprepare_required
active_consent_event_missing
preference_missing
customer_removed
campaign_cancelled
```

### 6. Delivery evidence and duplicate protection

Before SMTP submission, LEOSOFT creates and links an `OutboundEmail` record:

1. recipient is claimed;
2. current consent is checked;
3. queued outbound record is created and linked;
4. SMTP submission occurs;
5. sent or failed result is written back.

If SMTP may have accepted the message but the application stops before the final result is known, the linked queued record remains in `processing`. It is not automatically resent.

Sent or failed linked logs are safely reconciled later. A processing recipient with no outbound log and no activity for 30 minutes may return to pending because no registered SMTP attempt exists.

The generic email-log retry action refuses to retry campaign-linked messages. This prevents bypassing the campaign consent and approval controls.

### 7. Cancellation

Cancellation suppresses pending recipients and records the staff member.

A campaign cannot be cancelled while a recipient is `processing`. Staff must first:

1. set the send switch to `0`;
2. inspect the outbound log and campaign evidence;
3. reconcile the uncertain delivery state;
4. cancel only after no recipient remains processing.

Already-sent messages cannot be recalled.

## Recipient states

```text
pending
processing
sent
suppressed
failed
```

`processing` is a duplicate-prevention state. Do not edit or automatically retry stale processing records.

## Read-only administration

Django admin exposes campaigns and recipients for inspection only. Staff cannot manually change campaign state, approval evidence, counters, recipient status, consent evidence, outbound links or suppression reasons.

## Strict audit

```bash
python manage.py audit_customer_campaigns --json
python manage.py audit_customer_campaigns --strict
```

The audit checks for:

- approved or completed campaigns without approval evidence;
- creator or preparer self-approval;
- stale processing recipients;
- completed campaigns with unfinished recipients;
- sent recipients without a successful outbound log;
- sent messages without an unsubscribe path;
- pending recipients whose consent or email changed;
- counters that disagree with recipient records;
- campaign or recipient limits above configuration.

A normal completed internal campaign should report zero errors.

## Initial production settings

```dotenv
ALLTECH_PUBLIC_BASE_URL=https://leosoftug.com
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
ALLTECH_CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER=1
ALLTECH_CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=10
ALLTECH_CUSTOMER_CAMPAIGN_BATCH_SIZE=2
```

Use these small limits for internal testing. Increase them only after reviewing SMTP delivery, suppression records and strict audits.

## Database changes

Phase 8 adds:

```text
customer_campaigns.0001_initial
```

It creates:

- `CustomerCampaign`;
- `CustomerCampaignRecipient`.

The migration sends no messages, creates no campaigns or snapshots, changes no consent and does not enable delivery.

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

### 2. Pull

```bash
git checkout main
git pull origin main
pip install -r requirements.lock
```

### 3. Confirm safe settings

Add or confirm:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
ALLTECH_PUBLIC_BASE_URL=https://leosoftug.com
ALLTECH_CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER=1
ALLTECH_CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=10
ALLTECH_CUSTOMER_CAMPAIGN_BATCH_SIZE=2
```

```bash
set -a
source .env
set +a

python manage.py shell -c \
  "from django.conf import settings; print(settings.CUSTOMER_CAMPAIGN_SEND_ENABLED)"
```

Expected:

```text
False
```

### 4. Validate

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py check
python manage.py check --deploy
```

The plan should include `customer_campaigns.0001_initial`, and migration drift should report no changes.

### 5. Run PostgreSQL tests

```bash
sudo -u postgres psql -c \
  "ALTER ROLE leosoft_user CREATEDB;"

set +e
python manage.py test \
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
  echo "Phase 8 tests failed. Do not migrate or restart production."
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

### 6. Apply migration and audit

```bash
python manage.py migrate --noinput
python manage.py audit_customer_campaigns --json
python manage.py audit_consent_loyalty --strict
```

Initial campaign and recipient counts should be zero.

### 7. Publish and restart

```bash
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager -l
curl -fsS https://leosoftug.com/healthz/
```

### 8. Verify with sending disabled

Use two internal staff accounts with `marketing.change_marketingcampaign` and internal customers only.

1. Create a draft.
2. Prepare an audience.
3. Confirm customers without matching consent are excluded.
4. Confirm a different user is required to approve.
5. Approve.
6. Enter the exact send phrase.
7. Confirm the server blocks delivery while the switch is off.
8. Confirm no campaign outbound email is created.
9. Run the strict audit.

### 9. Controlled internal send

Do not first-enable against a real customer audience.

Create one or two internal customer records using mailboxes controlled by LEOSOFT staff. Record explicit product-update consent through checkout or the portal.

Set:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=1
ALLTECH_CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=2
ALLTECH_CUSTOMER_CAMPAIGN_BATCH_SIZE=1
```

```bash
set -a
source .env
set +a
sudo systemctl restart leosoft_gunicorn
```

Prepare a new internal campaign after consent is recorded. Use different staff members to prepare and approve. Send one recipient at a time.

Verify:

- the internal mailbox receives the expected message;
- placeholders render correctly;
- the unsubscribe link is correct;
- opening the unsubscribe page with GET changes nothing;
- confirming withdrawal suppresses the customer from a later campaign;
- outbound and recipient states are `sent`;
- strict campaign and consent audits pass.

### 10. Disable after the internal test

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
```

```bash
set -a
source .env
set +a
sudo systemctl restart leosoft_gunicorn
```

## Emergency stop

Set:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
```

Reload `.env` and restart Gunicorn. This blocks future batch requests but cannot recall email already accepted by SMTP.

When a recipient is processing, do not cancel or retry. Inspect the linked outbound log and run:

```bash
python manage.py audit_customer_campaigns --json
```

Cancel remaining pending delivery only after processing records are resolved.

## Operational rules

- Never treat purchase history, loyalty tier, review activity or dormancy as consent.
- Never use product-update-only consent for special offers.
- Keep independent approval enabled.
- Do not exceed two internal recipients during the first live test.
- Do not edit campaign records through Django admin.
- Do not retry campaign emails through the generic email log.
- Do not automatically retry uncertain queued delivery.
- Investigate stale processing before another batch.
- Run campaign and consent strict audits before broader use.
- Keep WhatsApp delivery disabled until its own approved provider workflow exists.
