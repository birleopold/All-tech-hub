# LEOSOFT project maturity roadmap

This roadmap keeps LEOSOFT aligned with the strongest patterns borrowed from
category-led marketplaces, organised electronics retailers, specification-heavy
technology catalogues and condition-transparent refurbished platforms, while
retaining LEOSOFT as the accountable seller and service provider.

## Implemented foundations

- Category-first navigation, large catalogue search and purpose-based collections.
- Brand, condition, price, stock and curated-collection filters.
- Relevant token-based search with accessible live suggestions.
- Product comparison, recently viewed items, related alternatives and quick cart actions.
- Product-aware enquiries, formal quotations, repairs and customer support routes.
- Clear product condition labels and a permanent technology buying guide.
- Product image gallery safeguards and deliberate missing-image fallbacks.
- Catalogue completeness scoring for images, descriptions, SKUs, brands, stock,
  variants, comparison prices, category copy and image alt text.
- Staff catalogue-quality workspace and dashboard warnings.
- Fail-fast production deployment with environment checks, migration drift detection,
  verified database backup, static manifest validation, systemd restart and revision-aware readiness.
- SQLite and PostgreSQL backup support with manifests, file sizes, SHA-256 checksums,
  retention and optional rclone off-site copies.
- Liveness, readiness, request correlation, customer-safe errors and private-page cache controls.
- Contact-form honeypot protection without a third-party dependency.
- Sitemap discovery for products, services and the buying guide.

## Operational gates requiring owner action

### 1. Production environment correction

The protected `.env` must permanently use:

```dotenv
DJANGO_SETTINGS_MODULE=config.settings
ALLTECH_ENV=production
```

The release script overrides an invalid value inside its own shell, but the source
configuration must still be corrected.

### 2. Payment provider activation

Do not merge or activate payment-provider code until all of the following are confirmed:

- the exact provider and merchant account;
- test and live credentials;
- webhook signing or verification method;
- retry and idempotency rules;
- refund and reconciliation workflow;
- customer-facing payment terms;
- a sandbox end-to-end test covering success, failure, cancellation and duplicate callbacks.

Cash, bank, mobile-money instructions or payment requests should remain explicit and
human-verifiable until that gate is complete.

### 3. SMTP and deliverability

Configure a verified sending domain and production SMTP provider before enabling
customer campaigns or relying on automatic order notifications. Confirm SPF, DKIM,
DMARC, bounce handling, suppression rules and a monitored reply address.

### 4. Off-site backups and restore drills

Set `ALLTECH_BACKUP_RCLONE_DEST` to a tested encrypted remote, enable off-site release
backups, and schedule periodic full backups with `--include-media --offsite`.
A separate test restoration must be completed and recorded; file creation alone is
not proof of recoverability.

### 5. Catalogue data completion

Use `/staff/catalogue-quality/` to correct real product data. Priority order:

1. Published products with no customer-visible image.
2. Products with no detailed description or specifications.
3. Missing brand, condition or SKU metadata.
4. Out-of-stock listings that still appear published without a clear enquiry strategy.
5. Missing variant SKUs, stock or valid comparison prices.
6. Gallery images without meaningful alt text.

The catalogue-quality score is an operational signal, not a replacement for staff
verification of the actual unit and written sales terms.

### 6. Policies and customer terms

Approve and publish business-specific privacy, delivery, warranty, return, repair,
data-retention and payment policies. Product pages and quotations should link to the
applicable approved terms rather than making broad promises that may not fit every
condition or service.

### 7. Content Security Policy enforcement

Keep CSP in report-only mode while reviewing violations from real public and staff
journeys. Enforce it only after required scripts, styles, images, analytics, payment
and support integrations are fully represented in the policy.

### 8. External monitoring

Configure an independent uptime service to check:

- `/health/ready/` for application and database readiness;
- `/catalog/` for a real public customer journey;
- TLS certificate expiry;
- domain and DNS resolution;
- backup age and storage capacity through a server-side monitor.

Internal health endpoints cannot detect a full VPS, network or DNS outage from outside.

### 9. Accessibility and performance validation

Run periodic mobile and desktop checks using representative low-bandwidth conditions,
keyboard-only navigation, screen-reader landmarks, contrast checks and realistic
catalogue volumes. Prioritise checkout, product detail, contact, repair intake and
staff order workflows.

## Release discipline

All future production releases should use:

```bash
cd /home/admin/All-tech-hub
git pull --ff-only origin main
bash scripts/deploy_production.sh
```

A failed preflight is a stopped release, not a reason to restart the service manually.
