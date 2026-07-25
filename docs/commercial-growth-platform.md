# LEOSOFT commercial growth platform

This release implements the commercial-discovery, catalogue-quality and content-authority programme on an isolated feature branch. It does not automatically correct legacy product facts: staff must verify each physical product before strict Merchant publication is enabled.

## Included capabilities

- Twelve editable high-intent commercial hubs with live stock, price ranges, FAQs and internal links.
- An editable technology knowledge centre with author, reviewer, publication and update information plus Article structured data.
- Detailed product commerce profiles for processor, RAM, storage, screen, graphics, operating system, battery, keyboard, accessories, warranty, condition and delivery.
- Stronger product cards with decision specifications, actual-photo and warranty badges, stock freshness, quick view, compare, wishlist, cart and WhatsApp actions.
- Delivery-zone publishing.
- Search Console CSV query reporting in staff administration.
- Product identity, condition, price and stock verification timestamps.
- Merchant readiness scoring and an optional strict feed gate.
- Bulk CSV catalogue correction, media audit and catalogue-readiness audit commands.
- Commercial sitemap coverage.

## Deployment sequence

```bash
cd /home/admin/All-tech-hub
git pull --ff-only origin main
source .venv/bin/activate
set -a
source .env
set +a

python manage.py check
python manage.py migrate --noinput
python manage.py seed_commercial_growth
python manage.py create_commerce_profiles --published-only
python manage.py test merchandising
python manage.py audit_commercial_catalogue --only-published --csv var/catalogue-readiness.csv
python manage.py audit_catalog_media
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
```

Run `seed_commercial_growth --refresh` only when the standard seed copy should replace staff edits. Normal repeated runs create missing records and preserve edited content.

## Merchant safety

Keep strict readiness disabled during the first review:

```dotenv
ALLTECH_MERCHANT_STRICT_READINESS=0
```

The feed remains available in audit-only mode. A physical product becomes eligible for strict publication only after it has:

- explicit Merchant approval;
- published status and a valid price;
- a product image and useful description;
- verified brand, exact identity and condition;
- GTIN, or a genuine brand and manufacturer part number;
- actual-photo confirmation;
- condition notes for refurbished and used products;
- current stock and price verification dates;
- an explicit shipping charge or confirmed free shipping.

After staff review and a feed inspection, strict mode can be enabled:

```dotenv
ALLTECH_MERCHANT_STRICT_READINESS=1
```

Then verify the feed headers and contents before submitting it to Merchant Center:

```bash
curl -I https://leosoftug.com/feeds/google-merchant.xml
curl -s https://leosoftug.com/feeds/google-merchant.xml | head -80
```

The response exposes `X-Merchant-Eligible-Items` and `X-Merchant-Excluded-Items` in strict mode.

## Catalogue audit

```bash
python manage.py audit_commercial_catalogue --only-published
python manage.py audit_commercial_catalogue --only-published --stale-days 14 --csv var/catalogue-readiness.csv
python manage.py audit_commercial_catalogue --only-published --fail-on-incomplete
```

The report highlights missing brands, condition verification, identifiers, images, descriptions, commercial profiles, actual-photo confirmation, stock or price checks, shipping decisions, out-of-stock records and repeated watermark filename prefixes.

## Bulk product correction

Start with a dry run:

```bash
python manage.py import_product_commerce_csv docs/product-commerce-import-template.csv --dry-run
```

Apply reviewed rows and mark all four verification dates at the import time:

```bash
python manage.py import_product_commerce_csv var/reviewed-products.csv --verify-now
```

Rows are matched by SKU first and slug second. Invalid rows are rejected atomically without retaining partial updates.

## Search Console reporting

Export query or page performance from Search Console as CSV, then import it:

```bash
python manage.py import_search_console_csv exports/search-console.csv \
  --date-start 2026-07-01 \
  --date-end 2026-07-31 \
  --replace-period
```

The imported query, page, clicks, impressions, CTR and average position are available under **Commercial merchandising → Search query insights** in Django administration.

## Media review

```bash
python manage.py audit_catalog_media
python manage.py audit_catalog_media --limit 30
python manage.py audit_catalog_media --skip-hashes
```

The command is deliberately non-destructive. It reports missing files, repeated watermark prefixes and identical image content. Use the existing original-image archive and `reprocess_product_images` workflow to rebuild approved images rather than renaming or deleting media automatically.

## Staff workflow

1. Seed commercial pages and guides.
2. Create missing commerce profiles.
3. Audit published catalogue records.
4. Correct product condition, brand, identifiers, stock and price.
5. Add inspected specifications, condition notes, warranty and delivery information.
6. Confirm actual photos and verification dates.
7. Review the top products and high-intent hubs in a browser.
8. Inspect the Merchant XML in audit-only mode.
9. Enable strict readiness only after the eligible records are accurate.
10. Continue publishing and updating practical guides from real customer and technical experience.
