# Phase 4 — Customer experience, accessibility and growth

Phase 4 improves public catalogue performance, product discovery, search presentation and customer self-service without changing checkout totals, stock deductions or payment state.

## What is implemented

### Responsive product images

New and updated product images automatically receive proportional WebP derivatives at configured widths. The defaults are:

```text
320, 640, 960 and 1280 pixels
```

The generator:

- never enlarges a source image;
- preserves its aspect ratio;
- retains the existing watermarked original as the fallback;
- stores public derivatives next to the public product image under a `responsive` directory;
- uses explicit image dimensions to reduce layout movement;
- uses lazy loading below the first screen;
- gives the principal product-detail image eager loading and high fetch priority.

The homepage, catalogue, comparison page, recently viewed section and product-detail page use responsive images.

### Product comparison

Visitors can compare up to four physical products. The selection is stored in the visitor's session and includes:

- category;
- price;
- availability;
- number of variants;
- summary;
- direct product links.

Services are deliberately excluded because their pricing and scope are not meaningfully comparable to physical inventory.

### Recently viewed products

The latest eight viewed catalogue items are stored in the functional session. The detail page shows up to four previous products, excluding the current item. No advertising cookie is required for this first-party navigation feature.

### Catalogue SEO controls

The catalogue now:

- removes the discovery rotation seed from canonical URLs;
- keeps useful kind, category and pagination parameters in canonical URLs;
- marks free-text search and explicit sort-result pages `noindex,follow`;
- keeps stable product-detail canonical URLs;
- excludes the comparison page from indexing.

Product structured data now supports, where available:

- brand;
- GTIN;
- MPN;
- product condition;
- multiple product images;
- seller organisation;
- shipping country and price;
- return-policy URL;
- variant aggregate offers;
- service provider data;
- published aggregate ratings.

### Core Web Vitals measurement

After analytics consent, the browser reports a `web_vital` GA4 event containing:

```text
metric_name
metric_value
metric_rating
page_path
```

Measured values include LCP, INP, CLS, FCP and TTFB when the browser supports the required Performance APIs. No analytics request is sent before consent when consent is required.

### Customer order tracking

Private receipt and portal order pages now show an accessible progress sequence for:

- order placed;
- confirmed;
- processing;
- ready for dispatch or pickup;
- dispatched where relevant;
- delivered;
- completed or collected.

Cancellation status and reason are shown separately. The private order JSON API exposes the same progress steps and shipment data.

### Warranty centre

Portal customers can view serialized products linked to their customer record, including:

- product and variant;
- serial number;
- IMEI when recorded;
- sale date;
- warranty duration;
- calculated coverage end date;
- apparent active or expired state.

The display is an operational record and does not replace written warranty terms or manufacturer conditions.

### Private indexing and cache protection

HTTP headers now mark staff, administration, customer portal, account, cart, quote, payment and private order-lookup responses as:

```text
X-Robots-Tag: noindex, nofollow, noarchive
Cache-Control: private, no-store
```

The public knowledge base remains indexable.

## Environment controls

The defaults are recommended:

```dotenv
ALLTECH_PRODUCT_IMAGE_RESPONSIVE_ENABLED=1
ALLTECH_PRODUCT_IMAGE_RESPONSIVE_WIDTHS=320,640,960,1280
ALLTECH_PRODUCT_IMAGE_RESPONSIVE_QUALITY=84
```

Use only integer widths between 160 and 2400 pixels. WebP quality is constrained to 60–95.

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
python manage.py check
python manage.py check --deploy
```

No database migration is expected for Phase 4.

### 3. Run focused tests

```bash
python manage.py test \
  catalog.test_responsive_images \
  catalog.test_experience \
  commerce.test_progress \
  portal.test_warranties \
  core.test_api_experience
```

Then run the broader release suite used for Phases 1–3.

### 4. Inspect existing image work

```bash
python manage.py generate_product_image_variants --dry-run
```

Generate a small sample:

```bash
python manage.py generate_product_image_variants --limit 10
```

After checking the sample in a browser, generate the remaining derivatives:

```bash
python manage.py generate_product_image_variants
```

Use `--force` only when responsive widths or quality settings have intentionally changed.

### 5. Run the customer-experience audit

```bash
python manage.py audit_customer_experience --json
```

It reports:

- published products missing images;
- published products missing descriptions;
- missing responsive widths;
- sold serialized products missing sale dates;
- legacy non-pending orders without timeline events.

The strict release gate is:

```bash
python manage.py audit_customer_experience --strict
```

Missing sale dates on sold, customer-linked serials are blocking errors because warranty expiry cannot be calculated accurately. Other catalogue gaps are warnings to resolve progressively.

### 6. Publish static assets and restart

```bash
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager -l
curl -fsS https://leosoftug.com/healthz/
```

## Browser verification

1. Open the homepage and catalogue in a private browser window.
2. Inspect a product-card image and confirm a WebP `srcset` is present.
3. Confirm the browser downloads an appropriately sized image rather than the largest original.
4. Open a product and confirm the principal image does not stretch or change aspect ratio.
5. Select four products for comparison and confirm a fifth is rejected.
6. View two products and confirm the earlier one appears under Recently viewed.
7. Confirm search and sorted catalogue pages include `noindex,follow` and a clean canonical URL.
8. Open a customer order and confirm progress, shipment details and cancellation handling are understandable on desktop and mobile.
9. Open the warranty centre as one customer and confirm another customer's serials never appear.
10. Check private responses with `curl -I` and confirm `X-Robots-Tag` and `Cache-Control: private, no-store`.

## GA4 setup

After enough consented traffic is collected, create GA4 custom definitions for:

- `metric_name` as an event-scoped dimension;
- `metric_rating` as an event-scoped dimension;
- `metric_value` as a custom metric.

Use the `web_vital` event with `page_path` to identify slow page families. Field measurements should be interpreted over a meaningful period and visitor sample rather than from one device.

## Warranty operations

A warranty appears only when staff records a `ProductSerial` with:

- status Sold;
- the correct customer in `sold_to`;
- an accurate sale date;
- a warranty duration in months.

Before relying on the portal for warranty decisions, reconcile sold serials against receipts and written warranty terms.

## Rollback

The Phase 4 changes do not alter transaction data. To roll back application behaviour:

1. restore the previous application commit;
2. collect static files;
3. restart Gunicorn.

Responsive WebP derivatives may remain in public media after rollback. They are independent derived copies and do not replace the existing originals.
