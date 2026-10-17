# LEOSOFT full-journey implementation plan
Date: 2026-10-16
Repository: birleopold/All-tech-hub · target branch: main
Scope: customer storefront, staff operations, admin configuration, production reliability

## Rules for every phase
- Extend existing Django modules and routes. Before adding a feature, find and reuse its current implementation.
- Every feature must have a reachable customer/staff UI, permission-safe backend, helpful empty/error states, accessible responsive layout, tests, and documented operation.
- Do not silently rewrite customer data or supplier specifications. Staff approve catalogue facts.
- Production payment integration is gated by provider credentials, signed callback verification, idempotency and sandbox reconciliation. Manual payments must remain explicitly manual until then.
- Do not state that tests, production workflows or external accounts are verified unless they have actually been tested.
- A phase is **complete** only when the acceptance checks below are satisfied; code merged alone is not sufficient.

## Progress board

| Phase | Goal | Acceptance checks | Status |
|---|---|---|---|
| P1 | Trustworthy storefront catalogue | Stable search/facets, correct prices and stock, consistent brand/category labels, mobile filters, intuitive product actions, public-page tests | **In progress** |
| P2 | Product data and inventory | Bulk editing, images, verified specifications, duplicate checks, stock movements, multi-device image workflow; staff tests | Queued (early fixes committed; phase not started) |
| P3 | Checkout and fulfillment | Guest/customer orders, precise delivery fees, payment method honesty, staff fulfillment queue, cancellation, idempotent confirmation, customer tracking | Queued (early safeguards committed; phase not started) |
| P4 | Customer service hub | Orders, repair status, warranties, invoices, tickets, documents and messaging connected without redundant profiles; ownership tests | Planned |
| P5 | Staff command centre and CRM | Universal search, priority queues, actionable KPIs, leads-to-quotes-to-orders, role-specific landing pages | Planned |
| P6 | Finance and field operations | Supplier receiving, repair/installation workbench, expense/margin reconciliation, safe refunds, approvals and financial drill-downs | Planned |
| P7 | Marketing and integrations | Channel status, selected-channel posting, manual override, consent and failed-job recovery, merchant data quality and measured conversion | Queued (early fixes committed; phase not started) |
| P8 | Production certification | Automated test gates, accessibility and responsive smoke runs, release rollback, backup restore drill, security and integration checks | Planned |

## Strict sequential phase policy (2026-10-17)
**Active phase: P1 only.** Do not advance to P2 until P1 is accepted.
Code already merged in later-phase areas is early work only and does not imply
those phases have started or passed acceptance.

A phase is done only when:
1. Customer/staff journey is usable from the relevant navigation on both mobile and desktop.
2. Backend validation prevents bypasses and handles empty, failed and duplicate requests.
3. Focused regression tests pass, the full suite passes, and database migration checks pass.
4. UI touch targets/keyboard interaction and the 320px–large-screen layout are checked.
5. Production or staging verifies the feature against the running Django app.
6. The roadmap lists actual evidence and remaining exceptions.

Current blocker: GitHub-hosted Actions jobs fail about 2 seconds after job
creation, with no runner allocated (runner_id=0 and no steps). Earlier runs
also had real lint/test failures. This is *not* evidence that the latest
tests passed or failed in Python. Check Actions account/billing and hosted
runner availability; run the same gates in an isolated staging environment.

## P1 work package (first implementation)
- [x] Share one canonical display grouping for customer brand filters, search suggestions, homepage brand collections and category/brand SEO pages without changing stored brand values.
- [x] Surface published brand spelling/capitalization inconsistencies on Staff → Catalogue quality with editable-listing search links.
- [x] Do not advertise an unquoted service as a zero-price offer in product metadata or structured data.
- [x] Add regression tests for brand grouping, filters, canonical brand route, staff warning and priced/unpriced services.
- [ ] Execute focused Django tests and full regression suite in the production-like runtime (GitHub-hosted runner currently unavailable).
- [ ] Confirm GitHub Actions runners start and report real step logs; repair baseline lint and test failures.
- [ ] Verify real small-screen and keyboard use of filters, cards and service pages.
- [x] Add clear sellability/status labels to catalogue cards without inventing exact stock promises.
- [x] Use the cheapest purchasable active configuration for "From" prices and sort/filter consistency; disable unavailable or unquoted options in the selector.
- [x] Correct search autocomplete so unpriced services say "Request an estimate" instead of UGX 0.
- [x] Keep service structured offer pricing consistent with paid variants on product pages.
- [x] Exclude unpriced services from numeric budget filters and available-now listings; sort unknown prices last in both price orders.
- [x] Cover empty-result recovery, labeled mobile/desktop filter controls and catalogue variations in regression tests.
- [x] Add accessible numbered pagination and explicitly carry the validated discovery seed in customer page links while leaving canonical URLs seed-free.
- [x] Preserve generic catalogue query-string category/brand/collection filters when paginating.
- [x] Make mobile and desktop filter forms submit to the universal catalogue URL so category, brand, collection and kind controls work from SEO landing pages too.
- [x] Keep a selected uncommon brand visible in the brand dropdown even when it falls outside the top 18 popular brands.
- [x] Send hero searches from SEO landing pages to the universal catalogue rather than silently restricting results to the previous landing URL.
- [ ] Validate real inventory states and mobile accessibility on a running server.
- [ ] Review stock status, results pagination, empty-state recovery and conversion actions together.
- [ ] Browser-verify routed category/brand changes, cross-tab discovery pagination, and search filters.
- [ ] Confirm production catalogue has no misleading zero-price representation in external previews.

## P3 first customer-to-staff order protection
- [x] Quote-only services go to the linked quotation request form rather than free checkout.
- [x] Product detail, sticky mobile action and service enquiry prefill reflect the quotation-required state.
- [x] Reject direct attempts to add zero-priced services or service options through the cart endpoint.
- [x] Remove old quote-only service entries from customer sessions before showing cart or processing checkout.
- [ ] Run service/checkout regression tests and validate the quotation-to-lead handoff in staging.
- [ ] Complete remaining checkout and fulfillment lifecycle, payment and exception-path tests.

## P2 initial staff catalogue-governance improvements
- [x] Reuse existing product-quality issue codes for staff-side direct issue filtering.
- [x] Make the common-issue counts clickable and retain filters across pages.
- [x] Preserve the selected issue when a search or other filter has zero matches.
- [ ] Run staff UI and permission regression tests and verify real screen-size behavior.
- [ ] Proceed with remaining inventory editing, image handoff and duplicate detection.

## P7 initial fixes
- [x] Restore the existing marketing image renderer as a staff-only, validated square/story PNG download route.
- [x] Expose artwork downloads directly on generated content cards.
- [x] Add anonymous/unpublished access checks to the existing PNG tests.
- [ ] Run growth image tests successfully in CI; the previous baseline reported a missing URL name and current hosted runners have no available step logs.
- [ ] Verify the staff content-generator UI, artwork and print/download files in a real browser.

## P2–P8 delivery pattern
For each phase: inspect current models, views, templates and docs → document gaps → implement backend + UI together → add focused tests → confirm permissions and mobile behavior → run full regressions and deployment checks → update this board.

## Owner-dependent verification
Payment gateway provider configuration, SMTP deliverability, Meta/Telegram credentials and approvals, policy text, off-site backup credentials, and external uptime monitoring must be confirmed against actual production services. Do not substitute a mocked success for production verification.

## Research and engineering references
- Django 5.2 queryset and aggregation docs: https://docs.djangoproject.com/en/5.2/ref/models/querysets/
- W3C WCAG 2.2 touch target, form and error guidance: https://www.w3.org/TR/wcag/
- Existing project detail: docs/PROJECT_MATURITY_ROADMAP.md, docs/STOREFRONT_POLISH.md
