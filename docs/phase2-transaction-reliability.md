# Phase 2 — Transaction reliability

This phase introduces durable stock reservations, checkout idempotency, payment-attempt state management, refund idempotency, webhook deduplication and stronger order audit trails.

## What is implemented

### Checkout idempotency

Every successful website checkout creates an `OrderReservation` using the random checkout submission token as a unique database idempotency key.

If the same checkout request is submitted again:

- the existing order is returned;
- no second order is created;
- stock is not deducted again;
- coupon usage is not incremented again.

Database uniqueness remains the final protection when simultaneous requests reach different Gunicorn workers.

### Stock reservations

Checkout still deducts on-hand stock atomically, but the deduction is now explicitly recorded as a reservation linked one-to-one with the order.

Reservation states:

- `reserved` — stock is held for a pending order;
- `committed` — payment or staff confirmation committed the stock;
- `released` — cancellation returned the stock;
- `expired` — the pending reservation timed out and returned the stock.

The default reservation window is 1,440 minutes, or 24 hours:

```dotenv
ALLTECH_ORDER_RESERVATION_MINUTES=1440
```

Choose this value based on the real payment-confirmation process. Do not shorten it until customers and staff can reliably confirm payments within the new period.

### Automatic reservation expiry

The management command:

```bash
python manage.py expire_order_reservations
```

cancels only due orders that are still pending. It then restores stock once and marks the reservation expired.

Orders already confirmed or further advanced are committed instead of cancelled.

Preview due reservations without changing anything:

```bash
python manage.py expire_order_reservations --dry-run
```

### Order cancellation safeguards

Order cancellation now requires a reason.

An order cannot be cancelled while it has a tracked payment in any of these states:

- paid;
- partially refunded;
- disputed.

The payment must be fully refunded before cancellation. Open payment attempts in created, pending or authorised state are automatically cancelled when an unpaid order is cancelled.

Stock restoration remains protected by the existing one-to-one `OrderStockRestoration` record, so a repeated cancellation cannot restore stock twice.

### Payment state machine

`PaymentAttempt` supports:

- created;
- pending;
- authorised;
- paid;
- failed;
- expired;
- partially refunded;
- refunded;
- disputed;
- cancelled.

Every payment attempt requires a unique idempotency key. Reusing the same key with identical details returns the existing attempt; reusing it with different order, amount, provider or currency is rejected.

A successful paid transition can confirm a pending order and commit its stock reservation.

### Refund idempotency

Every refund requires a unique idempotency key. Replayed provider callbacks return the existing refund instead of recording another refund.

The service rejects a refund that exceeds the remaining refundable amount.

### Webhook deduplication

`PaymentWebhookEvent` stores:

- provider;
- provider event ID;
- SHA-256 payload fingerprint;
- processing result;
- related payment attempt;
- failure details.

The same provider event ID and same payload is treated as a replay. Reusing an event ID with a changed payload is rejected as suspicious.

No provider-specific public webhook endpoint is enabled yet. Each future payment connector must verify its provider signature before calling the generic reliability services.

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

### 3. Set the reservation window

Add or confirm in `.env`:

```dotenv
ALLTECH_ORDER_RESERVATION_MINUTES=1440
```

A value of 1,440 is recommended for the first production release.

### 4. Validate migrations and tests

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py check
python manage.py check --deploy
python manage.py test reliability.test_transactions
```

Run the wider high-risk suite:

```bash
python manage.py test \
  reliability.test_transactions \
  core.test_phase1_security \
  catalog.test_watermarks \
  catalog.test_discovery \
  growth.test_growth \
  marketing.test_automation
```

### 5. Preview reservation processing

```bash
python manage.py expire_order_reservations --dry-run
```

Immediately after deployment, existing orders will not have reservations. Only checkouts created after this release enter the new reservation workflow.

### 6. Restart the application

```bash
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager -l
curl -fsS https://leosoftug.com/healthz/
```

### 7. Install the reservation timer

```bash
sudo cp deployment/leosoft-order-reservations.service /etc/systemd/system/
sudo cp deployment/leosoft-order-reservations.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now leosoft-order-reservations.timer
sudo systemctl start leosoft-order-reservations.service
sudo systemctl status leosoft-order-reservations.service --no-pager -l
sudo systemctl list-timers leosoft-order-reservations.timer --no-pager
```

Inspect logs:

```bash
sudo journalctl -u leosoft-order-reservations.service -n 100 --no-pager
```

### 8. Verify operational health

```bash
python manage.py check_operational_health --json
```

The health check reports an error when a reservation remains overdue for more than 30 minutes, indicating that the expiry timer may have stopped or failed.

## Production verification

Use a low-stock test item and verify:

1. Checkout creates one pending order.
2. Product stock decreases by the ordered quantity.
3. Staff order detail shows a `Reserved` stock reservation.
4. Customer receipt shows the reservation expiry time.
5. Reposting the same checkout token returns the original order.
6. Confirming the order changes the reservation to `Committed` without changing stock again.
7. Cancelling an unpaid order requires a reason and restores stock once.
8. Running cancellation again does not restore stock again.
9. An expired pending test order is automatically cancelled by the timer.
10. Operational health shows zero overdue reservations.

## Payment connector contract

A future Mobile Money or card connector must follow this order:

1. Generate or accept a unique payment idempotency key.
2. Call `create_payment_attempt()`.
3. Send the provider request without storing credentials or payment secrets in `safe_metadata`.
4. Verify the provider webhook signature using the exact raw request body.
5. Call `register_webhook_event()` with the provider event ID and raw payload.
6. Ignore a verified replay that returns `created=False`.
7. Apply the provider result with `transition_payment_attempt()`.
8. Call `finish_webhook_event()` only after the business transaction commits.
9. Use `record_payment_refund()` for provider refund callbacks.
10. Retain the provider external reference for reconciliation.

Never mark a payment paid based only on a browser redirect or customer screenshot. A verified provider response or authorised staff reconciliation must be the source of truth.

## Rollback

Before migration rollback, stop the timer:

```bash
sudo systemctl disable --now leosoft-order-reservations.timer
```

Application code can be rolled back while preserving the reliability tables. Do not reverse the reliability migration after real reservations, payments, refunds or webhook events have been recorded unless a verified database backup exists and data-loss implications are accepted.
