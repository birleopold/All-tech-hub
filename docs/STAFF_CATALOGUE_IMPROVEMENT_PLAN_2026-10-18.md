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
