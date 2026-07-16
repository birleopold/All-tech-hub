# Phase 5 — Conversion, payment guidance and customer lifecycle

Phase 5 improves the path from cart to completed order while preserving the existing stock, checkout, accounting, payment and document controls.

## What is implemented

### Transaction-safe order confirmation emails

After a new checkout transaction commits successfully, LEOSOFT attempts to send an order confirmation email containing:

- the order reference;
- ordered items and quantities;
- the order total;
- delivery or pickup method;
- current order status;
- the secure private order-tracking URL;
- official payment guidance from Company Settings, where configured;
- LEOSOFT contact information.

The email attempt is written to the existing `OutboundEmail` log. SMTP failure does not roll back checkout, stock reservation or the order record.

A queued or sent email with the same recipient and subject is reused so refreshing or retrying the checkout response cannot send duplicate confirmation messages.

### Customer-visible order status emails

A newly created `OrderStatusEvent` sends an email only when `visible_to_customer=True`.

Internal notes and internal status events remain private. The notification is registered with `transaction.on_commit`, so an event that is rolled back cannot generate a customer message.

### Retry command

Failed order confirmation and status messages can be retried with:

```bash
python manage.py retry_order_emails
```

Limit a run with:

```bash
python manage.py retry_order_emails --limit 50
```

The command changes a message to `sent` only after the mail backend accepts it. A repeated failure remains logged with the latest error.

### Payment guidance

Checkout, private order confirmation and customer portal order pages now explain that:

- placing an order does not confirm payment;
- payment is confirmed only after LEOSOFT verifies it;
- the customer should use the order reference;
- the customer should retain the transaction proof;
- only official LEOSOFT payment details should be used.

`CompanySettings.bank_details` is displayed when configured. This feature does not record payment, issue a receipt or change an invoice balance.

### Contextual product recommendations

The cart and post-order pages recommend up to four products. Recommendations:

- include only published physical products;
- exclude products already in the cart or order;
- exclude services;
- exclude products that are not available to sell;
- prioritise products from the same categories;
- then consider featured status, real non-cancelled order popularity and recency.

Recommendations do not change cart contents automatically.

### Conversion and lifecycle dashboard

Staff can open:

```text
/staff/reports/conversion/
```

The dashboard supports 7-, 30- and 90-day windows and reports:

- non-cancelled orders;
- cancelled orders;
- online order revenue;
- average order value;
- coupon-order rate;
- saved carts;
- recovered, active and expired saved carts;
- saved-cart recovery rate;
- recovered-cart revenue;
- a clearly labelled checkout conversion proxy;
- failed order emails;
- orders without a sent confirmation record;
- customer status emails sent;
- pending orders older than 24 hours;
- order status distribution.

The checkout conversion proxy is:

```text
orders / (orders + active, expired or unsubscribed saved carts)
```

It is not a complete website conversion rate because visitors who neither save a cart nor order are not included.

### Conversion audit command

Run:

```bash
python manage.py audit_conversion_funnel --days 30
```

Machine-readable output:

```bash
python manage.py audit_conversion_funnel --days 30 --json
```

Strict customer-email release gate:

```bash
python manage.py audit_conversion_funnel --days 30 --strict
```

Strict mode fails only when failed customer order emails remain. Older orders without Phase 5 confirmation records are reported as warnings because they may predate this release.

## Environment controls

Recommended production values:

```dotenv
ALLTECH_ORDER_CUSTOMER_EMAILS_ENABLED=1
ALLTECH_ORDER_STATUS_EMAILS_ENABLED=1
```

These settings require a working SMTP configuration. Before enabling them, verify:

```dotenv
ALLTECH_EMAIL_HOST=
ALLTECH_EMAIL_PORT=587
ALLTECH_EMAIL_USER=
ALLTECH_EMAIL_PASSWORD=
ALLTECH_DEFAULT_FROM_EMAIL=
ALLTECH_EMAIL_USE_TLS=1
```

Do not put SMTP passwords in Git or deployment documentation.

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

### 2. Pull and validate

```bash
git checkout main
git pull origin main
pip install -r requirements.lock

python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py check
python manage.py check --deploy
```

Phase 5 adds no database model fields and no Phase 5 migration is expected. Apply any older pending migrations normally:

```bash
python manage.py migrate --noinput
```

### 3. Test SMTP before enabling production emails

Use a real internal address controlled by LEOSOFT:

```bash
python manage.py shell -c "from django.core.mail import send_mail; from django.conf import settings; print(send_mail('LEOSOFT SMTP test','Phase 5 SMTP is working.',settings.DEFAULT_FROM_EMAIL,['YOUR_INTERNAL_EMAIL'],fail_silently=False))"
```

Replace `YOUR_INTERNAL_EMAIL` locally. Do not commit it.

### 4. Run focused tests

```bash
python manage.py test \
  commerce.test_customer_messages \
  commerce.test_recommendations \
  commerce.test_progress \
  reports.test_conversion
```

Then run the broader release suite used by earlier phases.

### 5. Run lifecycle audits

```bash
python manage.py audit_conversion_funnel --days 30 --json
python manage.py audit_customer_experience --json
```

Do not use strict conversion mode as a first historical baseline because older orders may predate confirmation-email logging. Strict mode blocks only active failed order emails.

### 6. Publish and restart

```bash
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager -l
curl -fsS https://leosoftug.com/healthz/
```

## Production verification

1. Place one low-risk test order using an internal LEOSOFT email address.
2. Confirm that exactly one confirmation email arrives.
3. Refresh the private order page and confirm no duplicate email is sent.
4. Confirm the email’s private tracking link opens the correct order.
5. Confirm bank or Mobile Money guidance matches Company Settings.
6. Create one customer-visible status event and confirm one update email arrives.
7. Create or inspect an internal-only status event and confirm no customer email is sent.
8. Confirm the cart excludes its current products from recommendations.
9. Confirm unavailable products and services do not appear in recommendations.
10. Open `/staff/reports/conversion/` and check the selected reporting window.
11. Review outbound email failures in the existing email log.
12. Run `python manage.py retry_order_emails` only after fixing SMTP errors.

## Operational cautions

- Customer emails are informational. They do not prove payment.
- Never mark payment as verified from an email reply alone.
- Keep `CompanySettings.bank_details` current and authorised.
- Order tracking URLs contain private UUID keys and must not be published.
- Email deliverability depends on SPF, DKIM, DMARC, sender reputation and correct SMTP credentials.
- Recommendations are contextual ranking, not personalised profiling or an automated purchasing decision.
