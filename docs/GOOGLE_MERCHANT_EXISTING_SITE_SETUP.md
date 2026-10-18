# LEOSOFT — Google Merchant Center and Business Profile, existing website

Last updated 2026-10-18. This guide prepares **leosoftug.com**, not a
Google-created store. No Google accounts have been accessed or linked by a
repository commit. Google must authorize the website owner or delegated user.

## 1. Product source — new fail-closed feed

- **Google scheduled-fetch URL**:
  `https://leosoftug.com/feeds/google-approved.xml`
- The feed is RSS/XML and updates from the existing LEOSOFT catalogue each
  time Google fetches it; it does **not** require exporting a spreadsheet or
  a VPS cron job.
- This URL always applies staff Merchant readiness approval regardless of
  the old `MERCHANT_STRICT_READINESS` feature flag.
- Existing `/feeds/google-merchant.xml` is left untouched for compatibility.
  **Do not add both as primary sources** or duplicate the same products.
- If no products have completed the merchant approval workflow, Google gets
  valid XML with **zero products**. This is intentional to avoid false
  prices, stock, manufacturer details and shipping claims.
- Staff can inspect the feed URL, published count and blockers under:
  `/staff/seo/`; inspect individual items through the existing catalogue
  quality/commercial review tools.
- Debug an installed release on VPS:
  `/home/admin/All-tech-hub/.venv/bin/python manage.py audit_google_feed`
  (prints export count and validates contents). Add `--require-items` if
  this should fail when the approved feed is empty.
- The release must pass `scripts/final_release_closeout.sh` before the
  generated URL is considered live.

## 2. The only Google-account actions that require the owner

1. Open https://merchants.google.com/ and select or create the **existing
   LEOSOFT Merchant Center**. Use the real registered business facts.
2. Verify/claim the **existing** website `https://leosoftug.com/` under
   business/online-store information. Google may recognize existing Search
   Console/Analytics ownership automatically. If Google gives an HTML tag,
   file or DNS verification record, install that exact token and re-check.
   Never paste a password or recovery code into source code or chat.
3. Under **Settings → Data sources → Add product source → Add products from
   a file → Enter a link to your file**, enter
   `https://leosoftug.com/feeds/google-approved.xml`.
   Choose the appropriate destination/country (Uganda) and language,
   schedule daily fetching, and review Google's Diagnostics/Needs Attention.
4. Enter accurate shipping charges, delivery coverage, return/refund policy,
   business information and support contacts. Google acceptance is not
   automatic. Avoid duplicating products in an existing primary data source.
5. In Google Business Manager → Stores → Add profile, **link the existing,
   verified LEOSOFT Business Profile**. Do not create a second location
   merely to connect products; use actual store address and opening hours.
   Store-level local inventory visibility requires separate current
   stock/location evidence and may differ by Google surface and country.

## 3. Data must be checked by staff, not fabricated by a data feed

For each physical product: real gallery photo, exact title and description,
correct brand and GTIN or brand/MPN, verified condition, price, stock record,
shipping/cost and policy; only then enable Merchant publication. The approved
feed refuses to export anything that has not passed these checks.

## 4. Google visibility limitations

Uganda (UGX) is supported by Google Merchant Center's target-country/currency
table, but **Uganda is not marked as a country with a dedicated Shopping tab**
in that table. Search, Maps, free listing, local inventory and ad placements
are distinct, eligibility-specific surfaces. No website code guarantees an
organic position above sponsored placements, a Maps carousel or an account
approval. Google may also rewrite organic search snippets.

An HTML tag supplied by Google can be added to the LEOSOFT base template,
but the token must come from an authenticated Google ownership flow.

## 5. Verification evidence to capture

- Deployed commit SHA from `/health/ready/`.
- XML endpoint GET 200 with `X-Merchant-Readiness: strict`, a parseable
  `<rss>` document and approved/omitted counts.
- `audit_google_feed` output on production database (read-only).
- Merchant Center verified website, data source fetch timestamp, item count,
  and actual Diagnostics statuses.
- Link status for existing Business Profile; verified physical store
  information; real current local inventory eligibility.

**Status:** Repository preparation only. Google account connection,
production deployment, live feed checks, and product approval remain
unverified until observed in their respective systems.
