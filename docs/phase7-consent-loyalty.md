# Phase 7 — Consent-based customer growth and loyalty operations

Phase 7 adds explicit optional-marketing consent, customer-controlled preferences, an append-only consent history, loyalty-point tracking and consent-safe audience reporting. It does not send bulk promotional campaigns and does not change payments, invoices, refunds, stock or accounting.

## What is implemented

### Explicit channel consent

Checkout contains separate optional checkboxes for:

- marketing email;
- marketing WhatsApp.

Both boxes are unchecked by default. Leaving them unchecked does not create consent, withdraw an existing preference or affect checkout.

A customer who opts in at checkout currently selects both supported topics:

- product and service updates;
- special offers and promotions.

Portal customers can later control each channel and each topic separately.

### Customer preference centre

Authenticated customers can open:

```text
/portal/preferences/
```

They can enable or disable:

- email marketing;
- WhatsApp marketing;
- product updates;
- special offers.

Turning off both channels also turns off both optional topics. Transactional communications connected to an order, payment, delivery, warranty, support request or another requested service remain separate.

### Safe unsubscribe confirmation

Each preference record receives a random UUID token. The public route is:

```text
/preferences/unsubscribe/<token>/
```

A GET request only displays a confirmation page. It does not change consent, protecting customers from email-link scanners and preview bots. Withdrawal requires a CSRF-protected POST confirmation.

The page:

- masks the customer email address;
- is noindex and noarchive;
- uses private no-store caching;
- withdraws email and WhatsApp marketing together;
- preserves the historical withdrawal record.

Future promotional email must include the customer-specific unsubscribe link. Phase 7 itself does not send a promotional campaign.

### Append-only consent events

Every real grant, update or withdrawal performed through the approved services creates `MarketingConsentEvent` containing:

- customer;
- action;
- source;
- channel choices;
- topic choices;
- consent-text version;
- event time.

The current preference record describes the latest state; consent events preserve the sequence of changes. Django administration exposes these records as read-only to prevent bypassing the event log.

Historical customers are not automatically opted in. A purchase, customer account, wishlist, review, repeat-order status or dormant status is not consent.

### Consent-safe customer audiences

Authorised staff can open:

```text
/staff/reports/customer-growth/
```

The page filters by:

- channel: email or WhatsApp;
- topic: product updates or special offers;
- segment: all, repeat, recent or dormant.

A customer appears only when the selected channel and selected topic are both active on the current preference record. Business segmentation never overrides consent.

The dashboard shows a maximum of 100 customer records and sends no messages. It is an audience preview for approved future campaign workflows.

### Loyalty points and tiers

Phase 7 creates:

- `LoyaltyAccount`;
- `LoyaltyTransaction`;
- member, silver, gold and platinum tiers.

Points are disabled by default:

```dotenv
ALLTECH_LOYALTY_POINTS_ENABLED=0
```

When enabled, eligible delivered or fulfilled orders earn:

```text
floor(order total / configured spend per point)
```

Default example:

```dotenv
ALLTECH_LOYALTY_SPEND_PER_POINT=10000
```

This means UGX 1,200,000 earns 120 points.

Tier defaults are:

```dotenv
ALLTECH_LOYALTY_SILVER_POINTS=100
ALLTECH_LOYALTY_GOLD_POINTS=500
ALLTECH_LOYALTY_PLATINUM_POINTS=1500
```

Each completed order uses a unique idempotency key and can award points once. The loyalty account is row-locked while awarding points.

Orders with a recorded customer return do not receive new points. If a return is recorded after an award, the strict audit flags the order for manual review. Phase 7 does not automatically reverse points and does not allow points to be redeemed.

### Customer loyalty page

Authenticated customers can open:

```text
/portal/loyalty/
```

The page shows:

- current tier;
- available points;
- lifetime points;
- points history;
- whether earning is currently active.

Points are not cash, payment, credit, a discount, an invoice settlement or a transferable balance. Redemption must not be introduced until return reversals, expiry, financial treatment and approved programme terms are implemented.

## Integrity audit

Run:

```bash
python manage.py audit_consent_loyalty --json
```

Filter the audience being inspected:

```bash
python manage.py audit_consent_loyalty \
  --channel email \
  --topic product_updates \
  --segment repeat \
  --json
```

Strict gate:

```bash
python manage.py audit_consent_loyalty --strict
```

Strict mode fails for:

- active consent without a consent time;
- active consent without a grant/update event;
- topic consent without an active channel;
- a withdrawn record still marked active;
- WhatsApp consent without a recorded customer phone;
- loyalty balance not matching transaction history;
- awarded orders that now have customer returns.

## Historical loyalty backfill

Preview completed, non-returned historical orders:

```bash
python manage.py backfill_loyalty_points --dry-run
```

After programme rules are approved and points are enabled, process a small sample:

```bash
python manage.py backfill_loyalty_points --limit 10
```

Inspect those customer accounts before processing the remaining eligible orders:

```bash
python manage.py backfill_loyalty_points
```

The command and service both use idempotency protection.

## Database changes

Phase 7 adds migration:

```text
loyalty.0001_initial
```

It creates:

- `CustomerMarketingPreference`;
- `MarketingConsentEvent`;
- `LoyaltyAccount`;
- `LoyaltyTransaction`.

The migration does not opt in historical customers and does not award historical points.

## Production deployment

### 1. Back up

```bash
cd /home/admin/All-tech-hub
source .venv/bin/activate
set -a
source .env
set +a

python manage.py backup_alltech --output /home/admin/All-tech-hub/backups
python manage.py verify_alltech_backup
```

### 2. Pull and keep loyalty disabled

```bash
git checkout main
git pull origin main
pip install -r requirements.lock
```

Confirm in `.env`:

```dotenv
ALLTECH_LOYALTY_POINTS_ENABLED=0
```

### 3. Validate

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py check
python manage.py check --deploy
```

The migration plan should include `loyalty.0001_initial`. Migration drift should report no uncommitted model changes.

### 4. Test on PostgreSQL

```bash
sudo -u postgres psql -c "ALTER ROLE leosoft_user CREATEDB;"

set +e
python manage.py test \
  loyalty \
  commerce.test_retention \
  commerce.test_customer_messages \
  reports.test_retention \
  reports.test_conversion
TEST_EXIT=$?
set -e

sudo -u postgres psql -c "ALTER ROLE leosoft_user NOCREATEDB;"

if [ "$TEST_EXIT" -ne 0 ]; then
  echo "Phase 7 tests failed. Do not migrate or restart production."
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

### 5. Apply migration

```bash
python manage.py migrate --noinput
python manage.py audit_consent_loyalty --json
```

The initial audience counts should normally be zero because historical customers are not opted in automatically.

### 6. Publish and restart

```bash
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager -l
curl -fsS https://leosoftug.com/healthz/
```

### 7. Verify consent controls

Use an internal customer account and verify:

1. Checkout consent boxes start unchecked.
2. Unchecked checkout does not create or change consent.
3. Selecting email consent creates a preference and grant event.
4. Portal preferences can disable special offers while retaining product updates.
5. The special-offer audience excludes that customer.
6. Opening an unsubscribe URL with GET changes nothing.
7. Confirming withdrawal with POST disables all optional marketing.
8. The full email address is not exposed on the unsubscribe page.
9. The staff dashboard sends no messages.
10. Private pages use no-store and noindex headers.

### 8. Approve loyalty rules before enabling

Document and approve:

- earning rate;
- tier thresholds;
- which orders qualify;
- treatment of returns and refunds;
- expiry policy, if any;
- whether points will ever become redeemable;
- customer-facing programme terms.

Then configure the approved values and enable earning:

```dotenv
ALLTECH_LOYALTY_POINTS_ENABLED=1
ALLTECH_LOYALTY_SPEND_PER_POINT=10000
ALLTECH_LOYALTY_SILVER_POINTS=100
ALLTECH_LOYALTY_GOLD_POINTS=500
ALLTECH_LOYALTY_PLATINUM_POINTS=1500
```

Reload `.env`, restart Gunicorn and test one internal completed order before considering a historical backfill.

### 9. Final strict gate

```bash
python manage.py audit_consent_loyalty --strict
python manage.py audit_customer_retention --days 90 --strict
python manage.py audit_conversion_funnel --days 30 --strict
```

## Operational cautions

- Do not import contacts as consented without reliable evidence.
- Do not use a purchase, dormant status, review or loyalty membership as marketing consent.
- Do not send WhatsApp marketing where the phone is missing or the WhatsApp topic/channel is not active.
- Every future promotional campaign must re-evaluate consent immediately before delivery.
- A customer withdrawal must suppress future queued marketing work.
- Loyalty points currently have no cash or redemption value.
- Do not manually edit loyalty balances or consent states in Django admin.
- Returns recorded after points were awarded require review until automated reversal rules are implemented.
