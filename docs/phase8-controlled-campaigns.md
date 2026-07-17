# Phase 8 — Controlled customer email campaigns

Phase 8 turns the Phase 7 consent-safe audience data into a controlled email campaign workflow. It is designed to prevent accidental bulk delivery, stale-consent sends and duplicate delivery after interrupted requests.

Phase 8 supports customer email only. It does not send WhatsApp messages. WhatsApp must remain audience-preview only until LEOSOFT has an approved provider, verified sender, message-template process, delivery callbacks and opt-out handling.

## Safety position

Production customer campaign sending is disabled by default:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
```

With the switch disabled, staff can:

- create drafts;
- prepare consent-safe audiences;
- review recipient evidence;
- approve campaigns;
- cancel campaigns.

They cannot release any email.

The server checks the switch again for every send request. A disabled HTML button is not the security control; the server-side setting is.

## Staff location

Authorised staff can open:

```text
/staff/reports/customer-campaigns/
```

The workflow appears in both desktop and mobile staff navigation as **Customer email campaigns**.

## Campaign lifecycle

### 1. Draft

A staff member defines:

- campaign name;
- optional link to an existing marketing campaign;
- consent topic: product updates or special offers;
- customer segment: all, repeat, recent or dormant;
- subject;
- message body;
- maximum recipients.

Supported placeholders are:

```text
{customer_name}
{first_name}
{company}
{unsubscribe_url}
```

When `{unsubscribe_url}` is omitted from the body, LEOSOFT appends the customer-specific preference link automatically.

Saving a draft sends nothing.

### 2. Prepare audience

Preparation builds a fixed recipient snapshot from customers who currently have:

- active email marketing consent;
- active consent for the selected topic;
- a current consent event that supports those choices;
- a recorded email address;
- the selected business segment.

A customer with only a Boolean preference flag but no consent event is excluded.

The snapshot records:

- customer;
- normalised email address at preparation time;
- consent event used during preparation;
- preparation time.

Preparation sends nothing.

A prepared campaign may be rebuilt only before delivery activity begins. Once a recipient has entered processing, failed or sent state, the campaign cannot silently replace its audience.

### 3. Independent approval

By default, the approver must be different from both:

- the campaign creator;
- the staff member who prepared the audience.

Controlled by:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER=1
```

The approver confirms that they reviewed:

- audience and consent topic;
- subject;
- message body;
- unsubscribe control;
- recipient limit.

Approval records the staff member, date, time and optional review note. Approval does not send anything.

### 4. Confirmed bounded delivery

An approved campaign requires the exact phrase:

```text
SEND <campaign ID>
```

One action releases no more than the configured batch size:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_BATCH_SIZE=10
```

A larger number entered in the form is automatically reduced to the configured maximum.

The campaign-wide preparation ceiling is:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=100
```

The application limits this setting to a maximum of 500.

### 5. Final consent recheck

Immediately before preparing each delivery, LEOSOFT checks again that:

- the customer still exists;
- the email address is still present;
- the email address still matches the prepared snapshot;
- email consent remains active;
- selected-topic consent remains active;
- consent has not been withdrawn;
- the latest consent event still supports the channel and topic.

A failed check suppresses the recipient instead of sending.

Common suppression reasons include:

```text
email_consent_withdrawn
topic_consent_withdrawn
email_changed_reprepare_required
active_consent_event_missing
preference_missing
customer_removed
campaign_cancelled
```

### 6. Delivery evidence

Before SMTP submission, LEOSOFT creates an `OutboundEmail` record and links it to the campaign recipient.

This ordering prevents automatic duplicate sends after an interrupted server request:

1. recipient is claimed;
2. current consent is checked;
3. queued outbound record is created and linked;
4. SMTP submission occurs;
5. sent or failed result is written back to the recipient.

If the process stops after SMTP may have accepted the message but before the final state is known, the linked queued record remains in processing state for manual review. It is not automatically resent.

Completed sent or failed outbound records are safely reconciled on the next batch request.

Processing records with no outbound log and no activity for 30 minutes may safely return to pending because SMTP submission had not yet been registered.

### 7. Cancellation

Cancellation suppresses every pending or processing recipient and records the cancelling staff member.

Already-sent messages cannot be recalled.

## Recipient states

```text
pending
processing
sent
suppressed
failed
```

`processing` is an important duplicate-prevention state. Staff should investigate stale processing recipients rather than recreating or manually editing records.

## Read-only administration

Django admin exposes customer campaigns and recipients for inspection only.

Staff cannot use Django admin to manually change:

- campaign status;
- approval evidence;
- counters;
- recipient status;
- consent evidence;
- outbound-email links;
- suppression reasons.

Operational changes must use the controlled application services.

## Strict audit

Run:

```bash
python manage.py audit_customer_campaigns --json
```

Strict release gate:

```bash
python manage.py audit_customer_campaigns --strict
```

The audit checks for:

- approved or completed campaigns without approval evidence;
- creator or preparer self-approval where separation is required;
- stale processing recipients;
- completed campaigns with unfinished recipients;
- sent recipients without a successful outbound log;
- sent messages without an unsubscribe path;
- pending recipients whose current consent no longer matches;
- email-address changes after preparation;
- campaign counters that do not match recipient records;
- campaign or prepared-recipient limits above configured controls.

A normal completed internal test campaign should report zero integrity errors.

## Environment settings

Recommended initial production values:

```dotenv
ALLTECH_PUBLIC_BASE_URL=https://leosoftug.com
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
ALLTECH_CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER=1
ALLTECH_CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=10
ALLTECH_CUSTOMER_CAMPAIGN_BATCH_SIZE=2
```

Use the smaller limits for the first controlled internal tests. Increase them only after reviewing SMTP delivery, suppression records and the strict audit.

## Database changes

Phase 8 adds:

```text
customer_campaigns.0001_initial
```

It creates:

- `CustomerCampaign`;
- `CustomerCampaignRecipient`.

The migration:

- sends no messages;
- creates no campaigns;
- creates no recipient snapshots;
- changes no customer consent;
- does not enable delivery.

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

Do not continue when backup verification fails.

### 2. Pull the phase

```bash
git checkout main
git pull origin main
pip install -r requirements.lock
```

### 3. Confirm the kill switch

Before migration, confirm `.env` contains:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
ALLTECH_PUBLIC_BASE_URL=https://leosoftug.com
ALLTECH_CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER=1
ALLTECH_CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=10
ALLTECH_CUSTOMER_CAMPAIGN_BATCH_SIZE=2
```

Reload it:

```bash
set -a
source .env
set +a
```

Confirm Django sees sending as disabled:

```bash
python manage.py shell -c \
  "from django.conf import settings; print(settings.CUSTOMER_CAMPAIGN_SEND_ENABLED)"
```

Expected:

```text
False
```

### 4. Validate code and migration state

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py check
python manage.py check --deploy
```

The migration plan should include:

```text
customer_campaigns.0001_initial
```

Migration drift must report no changes.

### 5. Run PostgreSQL tests

Temporarily allow the application role to create its test database:

```bash
sudo -u postgres psql -c \
  "ALTER ROLE leosoft_user CREATEDB;"
```

Run the release suite:

```bash
set +e

python manage.py test \
  customer_campaigns.test_campaigns \
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

### 6. Apply migration

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

### 8. Verify while sending remains disabled

Use two internal staff accounts and internal customer accounts only.

1. Create a draft.
2. Prepare an audience.
3. Confirm customers without matching consent do not appear.
4. Confirm a different staff member is required for approval.
5. Approve the campaign.
6. Enter the exact send phrase.
7. Confirm the server blocks delivery because the kill switch is off.
8. Confirm no new campaign `OutboundEmail` was created.
9. Run the strict audit.

### 9. Controlled internal send test

Do not first-enable this feature against a real customer audience.

Create one or two internal customer records with email addresses controlled by LEOSOFT staff. Record explicit product-update consent through the portal or checkout consent workflow.

Change only:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=1
ALLTECH_CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=2
ALLTECH_CUSTOMER_CAMPAIGN_BATCH_SIZE=1
```

Reload and restart:

```bash
set -a
source .env
set +a
sudo systemctl restart leosoft_gunicorn
```

Prepare a new internal campaign after setting the internal consent records. Do not reuse an old snapshot when email addresses or consent changed.

Use separate staff members to prepare and approve it. Send one recipient at a time.

Verify:

- the expected internal mailbox receives the message;
- the subject placeholders render correctly;
- the message contains the correct unsubscribe URL;
- opening the URL with GET changes nothing;
- confirming withdrawal suppresses the customer from a later campaign;
- the outbound log is `sent`;
- the recipient evidence is `sent`;
- the strict audit reports zero errors.

### 10. Disable after the internal test

Return the kill switch to off while the operational review is completed:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
```

```bash
set -a
source .env
set +a
sudo systemctl restart leosoft_gunicorn
```

## Emergency kill switch

At any time, stop new campaign delivery by setting:

```dotenv
ALLTECH_CUSTOMER_CAMPAIGN_SEND_ENABLED=0
```

Then reload and restart Gunicorn.

The switch blocks future batch requests. It does not recall email already accepted by SMTP.

Cancel active campaigns in the staff interface to suppress their remaining recipients.

## Operational rules

- Do not import historical customers as consented without reliable evidence.
- Do not use purchase history, loyalty tier, review activity or dormant status as permission.
- Never prepare a special-offer campaign from product-update-only consent.
- Always use a different approver while separation is enabled.
- Do not increase the first production batch above two internal recipients.
- Do not manually change campaign or recipient records in Django admin.
- Do not automatically retry an uncertain queued delivery.
- Investigate stale processing records before another batch.
- Run both campaign and consent strict audits before broader use.
- Keep WhatsApp delivery disabled until its own approved provider workflow exists.
