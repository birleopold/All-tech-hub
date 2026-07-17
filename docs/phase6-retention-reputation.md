# Phase 6 — Customer retention, verified reviews and repeat sales

Phase 6 strengthens the customer relationship after a successful order. It builds on the existing order, review, warranty, portal, email-log and reporting structures without changing payment, accounting or stock records.

## What is implemented

### Secure verified-purchase reviews

Delivered and fulfilled orders expose a private review action for each purchased, published physical product.

The review route contains:

- the order reference;
- the order's private UUID view key;
- the purchased product ID.

The server verifies that the product belongs to that order and that the order is delivered or fulfilled before accepting a review.

Submitted reviews:

- are linked to the CRM customer;
- are marked `is_verified_purchase=True`;
- start unpublished;
- require moderation before appearing publicly;
- return to moderation when the customer edits them.

The current review model stores one current verified review per customer and product through the Phase 6 service. A later purchase of the same product updates that customer's existing verified review rather than creating a public review for every order.

### Completed-order review requests

When staff creates a customer-visible order status event for `Delivered` or `Fulfilled`, Phase 6 can send one feedback request containing private verified-review links.

Review requests:

- are registered only after the order-status transaction commits;
- use the existing `OutboundEmail` delivery log;
- are deduplicated by recipient and subject;
- do not affect order status, stock, payment or accounting;
- optionally include the official Google review URL;
- refuse the non-delivering Django console email backend.

Automatic review requests are disabled by default. Enable them only after SMTP has been tested:

```dotenv
ALLTECH_ORDER_REVIEW_EMAILS_ENABLED=1
```

The setting is read safely from the production environment even when a dedicated Django setting has not been added.

### Buy-again / reorder

Completed orders provide an **Add available items to cart** action on both:

- the secure public order page;
- the authenticated customer portal order page.

Reorder processing:

- includes only published physical products;
- excludes services;
- skips deleted, unpublished or unavailable products;
- skips inactive or unavailable variants;
- caps requested quantities to current stock;
- uses current catalog prices at checkout;
- does not copy the old coupon;
- does not create an order until normal checkout is completed.

### Retention and reputation dashboard

Staff can open:

```text
/staff/reports/retention/
```

The dashboard supports 30-, 90- and 180-day views and reports:

- non-cancelled orders and revenue;
- unique customers;
- repeat customers;
- repeat-customer rate;
- returning orders and returning-order rate;
- repeat-customer revenue and share of revenue;
- completed orders;
- review requests sent and failed;
- review-request coverage;
- verified reviews received and published;
- average verified rating;
- warranties expiring in the next 30 days;
- top active customers by lifetime value;
- customers with no non-cancelled order for 90 or more days.

A repeat customer means a customer active in the selected period who has at least two lifetime non-cancelled orders. Repeat-customer revenue includes orders in the selected period from those customers. Returning-order rate separately measures orders that occurred after a customer's first order.

### Customer consent boundary

Phase 6 does not treat a purchase, review or dormant-customer status as permission to receive promotional campaigns.

The dormant-customer list is for staff-led account review, warranty support, service checks and lawful customer care. Do not bulk-send promotions from that list without an appropriate permission and unsubscribe process.

Review requests are directly connected to a completed transaction. They must not be expanded into unrelated marketing content.

### Warranty follow-up

The dashboard identifies serialized products whose recorded warranty expires within the next 30 days. It uses the existing `ProductSerial` sale date and warranty-month fields.

This is an operational follow-up list. Staff should verify the serial record, sale date and customer details before contacting the customer.

## Retention audit command

Run a 90-day audit:

```bash
python manage.py audit_customer_retention --days 90
```

Machine-readable output:

```bash
python manage.py audit_customer_retention --days 90 --json
```

Strict release gate:

```bash
python manage.py audit_customer_retention --days 90 --strict
```

Strict mode fails when:

- a review-request email remains failed; or
- review emails are enabled while the configured email backend cannot deliver.

## Failed customer-email retry

The existing command now retries order confirmations, customer-visible status messages and verified-review requests:

```bash
python manage.py retry_order_emails --limit 100
```

It exits with an error while the console email backend is active.

## Database changes

Phase 6 adds no model fields and requires no Phase 6 migration. It reuses:

- `commerce.Order` and `OrderLine`;
- `commerce.OrderStatusEvent`;
- `catalog.ProductReview`;
- `catalog.ProductSerial`;
- `messaging.OutboundEmail`;
- the session cart.

`python manage.py makemigrations --check --dry-run` should report no Phase 6 migration drift.

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
python manage.py migrate --noinput
```

### 3. Run Phase 6 tests

```bash
python manage.py test \
  commerce.test_retention \
  commerce.test_customer_messages \
  reports.test_retention \
  reports.test_conversion
```

Run the wider release suite before restarting production.

### 4. Establish the retention baseline

```bash
python manage.py audit_customer_retention --days 90 --json
python manage.py audit_conversion_funnel --days 30 --json
```

The first baseline may show completed historical orders without review requests because those orders predate Phase 6.

### 5. Test review email delivery

Keep this disabled initially:

```dotenv
ALLTECH_ORDER_REVIEW_EMAILS_ENABLED=0
```

Confirm that Phase 5 order email delivery works to an internal LEOSOFT address. Then temporarily enable review emails and create one controlled customer-visible `Fulfilled` or `Delivered` event on a low-risk internal test order.

Confirm that:

- exactly one review request arrives;
- every link opens the correct purchased product form;
- the link contains the private order UUID;
- refreshing or repeating the same terminal status does not send a duplicate subject;
- the submitted review remains unpublished until moderated.

After validation, keep the flag enabled only when LEOSOFT wants transactional review requests:

```dotenv
ALLTECH_ORDER_REVIEW_EMAILS_ENABLED=1
```

### 6. Publish and restart

```bash
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager -l
curl -fsS https://leosoftug.com/healthz/
```

### 7. Run strict audits

```bash
python manage.py audit_customer_retention --days 90 --strict
python manage.py audit_conversion_funnel --days 30 --strict
```

## Production verification

1. Open a delivered or fulfilled order through its private link.
2. Confirm Review buttons appear only for purchased physical products.
3. Submit a review and confirm it is marked verified but unpublished.
4. Moderate the test review and confirm it appears on the product page.
5. Use **Add available items to cart** and confirm current availability and quantities are respected.
6. Confirm unavailable items are skipped with a clear message.
7. Repeat the checks from an authenticated customer portal order page.
8. Open `/staff/reports/retention/` and compare 30-, 90- and 180-day results.
9. Inspect warranties expiring within 30 days against the serial records.
10. Confirm the staff-role permission blocks unauthorised staff when role enforcement is active.
11. Run the retention audit and review any failed messages.
12. Do not use dormant-customer data for unsolicited bulk promotions.

## Operational cautions

- Review links contain private order keys and must not be published.
- Reviews may contain personal information; moderate before publishing.
- Never reward only positive reviews or suppress genuine negative reviews.
- Reorder uses current stock and prices, not the historic order price.
- Review-request delivery does not prove that the customer opened the email.
- Repeat-sales metrics exclude cancelled orders but do not represent gross profit.
- Warranty reminders do not extend or alter the recorded warranty.
