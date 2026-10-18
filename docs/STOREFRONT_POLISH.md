# Storefront and customer-page polish

This release extends the established Leosoft navy, blue and cyan design across
the public catalogue and customer journeys.

- Product pages show the gallery and purchase panel before specifications and
  long descriptions. Existing variant selection, stock checks, gallery controls,
  Call and WhatsApp actions remain connected to their original routes.
- Shop and category pages have calmer filters, consistent photo framing and more
  orderly card titles and prices. Services have their own visual cues, concise
  summaries and a scope-confirmation panel. Services without a published price
  invite an estimate.
- About uses the configured company identity and photographs from published
  catalogue items. It does not invent shop or installation photography.
- Contact places Call, WhatsApp and directions before the request form, using
  the existing company and social-profile settings.
- Cart and checkout show item thumbnails with gallery fallback. Quantity fields,
  variant prices, coupons, delivery calculations and checkout tokens are retained.
  Prefetched gallery images can supply thumbnails without extra database queries.
- Customer pages share account navigation, cleaner status cards and consistent
  tables, forms, saved-item photographs and empty states. Customer access controls
  and ownership checks are unchanged.
- Shared refinements cover keyboard focus, touch controls, responsive spacing and
  reduced motion. The comparison page receives matching styling.

## Validation

The release adds 14 regression tests for purchase-panel ordering, service
estimates, published-photo visibility, contact context, gallery query behavior,
variant cart totals and customer ownership. The focused storefront, cart,
checkout, tracking and warranty checks contain 100 tests.

The full suite ran 652 tests. Its 34 failures and 7 errors have exactly the same
test names as the deployed `4cab1a7` baseline; no additional failing tests were
introduced. The full suite is therefore not green. Production Django checks,
migration-drift checks, static collection and the hashed stylesheet lookup pass.
Local verification used the available Django 5.2.13 runtime; the VPS continues
to install the repository's locked dependencies, including Django 5.2.15.

Browser visual verification could not be completed: the cloud browser could not
reach the isolated local server, and its policy blocked local-file previews.
Review mobile and desktop presentation after deployment.

The VPS wrapper was checked with isolated command stubs for the successful
release sequence, wrong branch, failed pull, failed dependency installation,
failed release, stale public revision and concurrent-release locking.

## Existing VPS deployment

Run as `admin`:

```bash
bash <<'DEPLOY'
set -Eeuo pipefail
cd /home/admin/All-tech-hub
git pull --ff-only origin main
bash scripts/update_vps.sh
DEPLOY
```

`scripts/update_vps.sh` uses the existing `.venv`, `.env`, production directory
and `scripts/deploy_production.sh`. It preserves local tracked edits, installs
the durable marketing units, invokes the existing release checks and backup,
and requires the public readiness response to match the checked-out revision.
It also prevents two manual wrapper runs from deploying simultaneously.

The locally modified `scripts/deploy_production.sh` and
`scripts/manage_production.sh` shown in the VPS logs are not changed by this
release. An overlapping Git change stops the pull for review; the wrapper never
resets or discards local files.

After the first pull, routine deployments can use:

```bash
bash /home/admin/All-tech-hub/scripts/update_vps.sh
```

The marketing timer continues to run growth automation. The wrapper does not
install a Git deployment watcher or change the separate hotspot watcher.

## 2026-10-18 — Short, shopping-first homepage

The homepage now consists of only **welcome/search → featured products →
deals (when available) → featured services → four brief trust links**.
Educational sections, buyer journeys, repeated purpose/brand/budget
collections, refurbished/new-arrival repeats and the long expandable guidance
story have been removed from the homepage. Their existing catalogue, filters,
collections and buying-guide destinations remain available elsewhere.
The mobile navigation now uses one collapsible category list instead of
immediately repeating each category in the top-level menu.

No product was hidden from the catalogue and no SEO buying-guide URL was
deleted. Product pages, dedicated buying guides and sitemap content remain
distinct from the lean homepage. Actual mobile/desktop acceptance and VPS
release-gate verification remain pending.
