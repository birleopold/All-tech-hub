# Leosoft staff and catalogue improvement plan — 2026-10-18

Evidence: authenticated TinyFish walkthrough of /staff/, /staff/seo/, /staff/catalogue-quality/, product editor, bulk enrichment, reports and marketing. The 2026-10-18 release log shows 864/864 offline tests passed on 39b674b; deployment aborted when origin/main advanced to 42f1451. The abort is an intentional revision-consistency protection, not a test failure.

## Delivery rules
- All code changes must be usable from the staff UI, mobile and desktop; protect permissions and CSRF.
- Never invent stock, GTIN, MPN, actual item condition, warranty or sales; manufacturer marketing descriptions are not proof of a particular unit's configuration.
- Never bypass the release guard. Stop changes to main while final_release_closeout.sh tests and deploys a fixed revision.
- Validate with isolated test rehearsal before the protected production deploy; audit actual live workflows afterward.

## Phases and current status
- [x] P0: Investigate release log and identify source-race abort. **Confirmed**; no deployment of 39b674b occurred in that log.
- [x] P1a: Make Google review queue variant-stock-aware. **Committed** at 42f1451; pending guarded VPS verification.
- [x] P1b-partial: Implement explicit per-product Merchant approval/revocation with staff permission, freshness, tracked stock and completeness guards; regression tests added.
- [x] P1c-code: Exclude untracked and sold-out variants from the approved Merchant feed; reject stale or future-dated stock confirmation.
- [ ] P1d: Review real stocked products: matching physical inventory, condition, identification, shipping, photos, price and variants; selectively approve only verified records. Human inspection required; cannot be performed by metadata guessing.
- [x] P2a: Immediate identical unread notification retry suppression with regression tests. Historical inbox cleanup and priority triage remain open.
- [x] P2b-partial: Add read/unread inbox filters with pagination, while preserving all history. Historical noise triage and producer audit remain open.
- [x] P2c-partial: Non-destructive, staff-owned age-scoped notification acknowledgement with UI and tests.
- [x] P2d-diagnostics: Add read-only grouped notification noise command and regression test.
- [ ] P2e: Notifications: assess producers and distinguish repeated non-actionable noise, add bounded duplicate protection and safe inbox triage; ensure distinct alerts are retained.
- [x] P3a: Add explicit product verification guidance to staff editor.
- [x] P3b-partial: Add one-click commercial review link and explicit variant price/stock guidance on product editor.
- [x] P3c-code: Require product, growth and commerce-profile change permissions for commercial-review saves; test unauthorized edit attempts.
- [ ] P3d: Product editor: improve field-level guidance for warranties, condition, GTIN/MPN, actual photos, variant-specific price and stock; add direct review navigation where missing.
- [x] P4a: Label manual CSV opportunity counters separately from daily Windsor account metrics.
- [ ] P4b: SEO: clarify live Windsor queries vs manual CSV imports; tie opportunity guidance to real search records; improve consistency between source-specific metrics.
- [x] P5a: Explain differences between online order sales and document finance metrics in the staff reporting UI.
- [x] P5b-code: Add staff finance-only, source-separated online order versus issued document reconciliation page, largest-document review and permission tests.
- [ ] P5c: Sales & reporting: document online-order revenue vs document profit basis; inspect extraordinary profit lines and number gaps; add reconciliation drilldowns and safeguards, not arbitrary accounting changes.
- [x] P6a: Bounded 25-per-action transaction-safe claim for unassigned overdue leads, exposed on the staff list and covered by tests.
- [x] P6b-diagnostics: Add factual lead-source, campaign-link, overdue and ownership report and regression test.
- [ ] P6c: Leads: review 49 overdue leads and attribution; improve assign/claim, bulk actions, priority and tracking while preserving audit history.
- [x] P7a-code: Add narrow-screen constraints for the product editor, horizontally scrollable variant table, explicit table headers and unsaved-change warning. TinyFish inspected desktop only; mobile viewport resizing unsupported.
- [ ] P7b: Accessibility and mobile browser review: staff navigation, touch actions, forms, responsive tables and multi-device save flows.
- [ ] P8: Release verification: isolated tests, guarded deploy, public health, Google timer, permission checks and authenticated TinyFish regression.

## Already available; do not duplicate
- Staff product register already has a **New product** action and **Previous** pagination.
- Bulk enrichment already has **Clear** and **Reset** controls.
- Leads already have **Claim**, **Contacted** and assignment filters.
These were not fully visible during the automated browser walkthrough and should be tested rather than rebuilt.

## Measurable acceptance
- No unauthorized catalogue mutation from enrichment; no fake identifiers.
- Product review priorities include inventory-managed variants with positive recorded stock and exclude unverified availability from the available-only view.
- Google live status is explicitly labelled and missing or stale data cannot appear current.
- Staff can find core workflows without Django admin where a first-party editor exists.
- Test gate on exact origin/main SHA succeeds; deploy and health check match that SHA.

## Evidence required before closing all phases
- Physical product checks: photograph model labels, verify stock per variant, confirm warranty/price/condition from actual inventory; record checked-by and dates in staff forms. Never bulk-approve unknown details.
- Reports: compare online order lines against independently issued invoice documents using the same date basis; investigate unsupported gross profit and document sequence gaps before adjusting accounting logic.
- Notification noise: inventory alert producers and group repeat messages by recipient, message and destination; preserve actionable distinct alerts and original history.
- Attribution: inspect captured campaign links/UTM evidence; retain `direct` when referral provenance is missing rather than guessing.
- Release: full tests and live external integration checks are still pending on the VPS; code commit alone does not prove a deployed feature.

## Final four-item status (do not conflate code with real-world verification)
- Financial reconciliation: code-backed comparison page and permission tests committed; extraordinary accounting numbers still require comparing actual posted documents, payments and source costs.
- Product enrichment: existing staff verification fields, review queue and guarded approval are implemented; physical SKU/variant/condition/price verification is not possible from website images alone and no unverified product data was applied.
- Responsive workflows: desktop staff editor inspected with TinyFish; improved narrow-width CSS and unsaved-form protection committed. The browser could not resize to 390px; live mobile validation remains.
- Production: requires the user's guarded VPS deployment and successful current-revision release log; not certified by GitHub commits or public read-only inspection.

## Production inspection closeout evidence — 2026-10-18
- The public readiness endpoint `/health/ready/` responded `status=ok`, `database=ok`, `migrations=ok`, `pending_migrations=[]`, deployed revision `c91010b`. This confirms the last reported deployment revision, not any commits made afterward.
- Authenticated TinyFish revisited `/staff/reports/reconciliation/`, `/staff/seo/`, and `/staff/inventory/products/1/commercial/`; all rendered successfully, including financial source comparison, saved Windsor metrics, and Merchant approval controls. Those actions were read-only.
- Authenticated TinyFish separately inspected `/staff/marketing/leads/`: overdue triage action and six filters are visible. It reported 49 overdue first responses but zero currently eligible unassigned-overdue records when it used the batch claim. The two counts measure different subsets.
- `/static/images/products/149/small.jpg` returned HTTP 404. Do not invent or replace the image with a different product. Inspect media provenance, asset references and originals; use the existing `python manage.py audit_catalog_media --skip-hashes` to inspect storage-backed product photos. The audit alone does not validate every static legacy URL.
- Saved Windsor snapshot reported 13 GA4 active users, 27 Uganda pending free listings, and 0 Uganda active free listings. Account data and local catalogue quality are not Google approval.
- TinyFish could not resize its browser to 390px, so mobile layout is still not empirically verified. It did inspect the desktop form and variants.

## TinyFish chapter closeout boundary
Software workflow implementation and deployed page smoke inspection may be considered complete for the features listed above **at revision c91010b**, but the following must not be marked completed without further evidence:
1. In-person product/variant stock, condition, warranty and model verification; do not enable Merchant publication for unverified products.
2. Investigating accounting figures against real commercial documents, payments, posted costs and customer credits; the aggregate total is not itself proof of profit.
3. Mobile-device editing and save/validation checks across actual screen widths.
4. Repairing the confirmed broken image URL from the authentic source.
5. A successful guarded release and browser check for any commits later than c91010b.

No background tasks or automatic product approvals have been initiated by this document.

## Follow-on delivery — 2026-10-18 evening
- [x] Staff media audit now accepts `--product-id` and identifies missing media records with their product IDs. Product media is not deleted or replaced, and the 404 `/static/images/products/149/small.jpg` still needs provenance and original assets.
- [x] Finance-only reconciliation now highlights issued lines with non-positive recorded unit costs and documents worth at least UGX 100 million. These are review flags, not recalculated profit or evidence that any given record is wrong.
- [x] Lead triage explains why first-response overdue totals can exceed the unassigned-overdue claim count.
- [x] Tests added for new financial review metrics and non-destructive media targeting.
- [ ] Physical SKU-level inspection, precise product descriptions from confirmed model facts, and original-photo restoration remain dependent on source evidence.
- [ ] Live mobile device verification, Google Merchant external approval, and current-commit VPS deployment/release gate remain external verification items.

### Suggested verification after pushing these changes
```bash
cd /home/admin/All-tech-hub
.venv/bin/python manage.py audit_catalog_media --product-id 149 --skip-hashes
.venv/bin/python manage.py test merchandising.test_media_audit_targeting reports.test_financial_reconciliation
bash scripts/final_release_closeout.sh
curl -fsS https://leosoftug.com/health/ready/
```
Do not push new commits to main while the guarded release is running.

## Continuation: ongoing feed eligibility (2026-10-18)
- [x] Change approved Merchant feed eligibility so even previously approved SKUs are omitted when stock confirmation is absent, older than 30 days, or dated in the future; continue omitting zero-stock/untracked variants.
- [x] Add regression test covering expiry and maintain valid-stock variant coverage.
- [x] Display the stale-stock block on commercial review so staff understand why an approved product is not in the feed.
- [ ] Verify these latest commits with the guarded VPS test/deploy and Google Merchant feed URL. No live product records were updated.

## Continuation — Merchant review queue consistency
- [x] Explicitly separate past Merchant approval (`merchant_approved`) from eligibility for the current approved feed (`feed_eligible_now`) in CLI and staff CSV downloads.
- [x] Flag expired stock verification on already-approved products so staff can renew inspections before expecting Google publication.
- [x] Add regression coverage for approved-but-stale catalogue entries.
- [ ] Run the current revision through the guarded VPS release and compare the review CSV with `/feeds/google-approved.xml`.
- [ ] Recover authentic images and inspect real product units before modifying missing identifiers, conditions or stock.
