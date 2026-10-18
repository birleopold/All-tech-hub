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
| P1 | Trustworthy storefront catalogue | Stable search/facets, correct prices and stock, consistent brand/category labels, mobile filters, intuitive product actions, public-page tests | **Code implemented — verification deferred** |
| P2 | Product data and inventory | Bulk editing, images, verified specifications, duplicate checks, stock movements, multi-device image workflow; staff tests | **Code implemented — verification deferred** |
| P3 | Checkout and fulfillment | Guest/customer orders, precise delivery fees, payment method honesty, staff fulfillment queue, cancellation, idempotent confirmation, customer tracking | **Code implemented — verification deferred** |
| P4 | Customer service hub | Orders, repair status, warranties, invoices, tickets, documents and messaging connected without redundant profiles; ownership tests | **Code implemented — verification deferred** |
| P5 | Staff command centre and CRM | Universal search, priority queues, actionable KPIs, leads-to-quotes-to-orders, role-specific landing pages | **Code implemented — verification deferred** |
| P6 | Finance and field operations | Supplier receiving, repair/installation workbench, expense/margin reconciliation, safe refunds, approvals and financial drill-downs | **Code implemented — verification deferred** |
| P7 | Marketing and integrations | Channel status, selected-channel posting, manual override, consent and failed-job recovery, merchant data quality and measured conversion | **Code implemented — verification deferred** |
| P8 | Production certification | Automated test gates, accessibility and responsive smoke runs, release rollback, backup restore drill, security and integration checks | **Active — certification pending** |

## Strict sequential phase policy (2026-10-17)
**Active phase: P8 (production certification).** P1–P7 code is staged. A full 754-test isolated Django suite passed on the VPS for release `c0737f0` on 2026-10-18, with PostgreSQL backup, migrations and public readiness successful. This proves the automated release check for that SHA, **not** the pending browser, external-provider or production PostgreSQL restore acceptance. The subsequently committed catalogue search, repair handover and homepage work has **not yet passed** a VPS gate.
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
The GitHub-connected editing environment cannot start or inspect the Ubuntu
production process or create a complete isolated copy of this private repo.
Never deploy these changes on a live sales site as a substitute for testing.

## P1 work package (first implementation)
- [x] Share one canonical display grouping for customer brand filters, search suggestions, homepage brand collections and category/brand SEO pages without changing stored brand values.
- [x] Surface published brand spelling/capitalization inconsistencies on Staff → Catalogue quality with editable-listing search links.
- [x] Do not advertise an unquoted service as a zero-price offer in product metadata or structured data.
- [x] Add regression tests for brand grouping, filters, canonical brand route, staff warning and priced/unpriced services.
- [ ] Execute focused Django tests and full regression suite in the production-like runtime (GitHub-hosted runner currently unavailable).
- [ ] Confirm GitHub Actions runners start and report real step logs; repair baseline lint and test failures.
- [x] Wire the new Phase 1 regression modules and catalogue/mobile JavaScript syntax checks into the existing Django CI workflow.
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
- [x] Add conservative typo-recovery suggestions only when a corrected search produces results under the same filters, with customer navigation regression tests.

## P3 first customer-to-staff order protection
- [x] Disable delivery at checkout when no priced delivery area exists, instead of silently charging zero; pickup remains usable.
- [x] Exclude configured delivery areas with missing prices and give customers a visible quote-enquiry path.
- [x] Allow staff returns only for delivered/collected orders; protect backend and provide a helpful UI state.
- [x] Restrict inventory returns to physical goods; direct service adjustments to credit notes.
- [x] Lock the order row when staff generate an invoice so double submissions cannot create competing invoices.
- [x] Preserve the selected delivery amount in checkout error re-renders and keep pickup shipping fields blank.
- [x] Prevent shipment status regression after delivery and completed-order shipment progress changes at the backend, preserving pending, transit and exception states.
- [x] Restrict pickup and delivery orders to appropriate next statuses, reusing the existing transition engine.
- [x] Show staff only actionable next steps; hide final-order status actions and pickup shipment forms.
- [x] Block shipment updates for pickup and cancelled orders in the backend, not only templates.
- [x] Quote-only services go to the linked quotation request form rather than free checkout.
- [x] Product detail, sticky mobile action and service enquiry prefill reflect the quotation-required state.
- [x] Reject direct attempts to add zero-priced services or service options through the cart endpoint.
- [x] Remove old quote-only service entries from customer sessions before showing cart or processing checkout.
- [x] Protect issued quotation revision history so accepted or internally approved quotation terms must be approved again after a revision; revoke the earlier private acceptance token, snapshot former acceptance evidence, and stop revisions of paid, cancelled, posted-inventory or receipt documents. Regression tests added.
- [x] Harden completed-order verified-purchase reviews against accidental unpublication on duplicate submissions, concurrent duplicate submissions for one customer, and silent review truncation; published reviews cannot be overwritten from the private link.
- [ ] Run the new quote/review regression tests on the VPS and exercise revision acceptance links and review moderation in desktop/mobile browsers.
- [ ] Run service/checkout regression tests and validate the quotation-to-lead handoff in staging.
- [x] Code-stage the checkout-to-fulfillment journey: guest/customer checkout, priced delivery or pickup, tax totals, reserved stock, idempotent submissions, customer tracking, staff status/shipments, cancellation/refund checks and return restrictions. Reuse existing payment and outbound-message integrations rather than creating duplicate gateways.
- [x] Add focused exception-path coverage for unpriced delivery, shipment regression, cancellation and invalid inventory returns.
- [ ] Run integrated checkout/fulfillment and payment-provider tests during final verification; production providers remain unverified.

## P4 customer service hub implementation
- [x] Reuse the existing customer account, records and helpdesk conversation; no parallel CRM or support database.
- [x] Link support tickets to owned repair jobs and commercial documents, with nullable relations and migration.
- [x] Restrict customer support form selections to owned jobs, documents, orders and serials; validate ownership at the model boundary.
- [x] Add linked support shortcuts to repair pages and customer documents, and prefill the original record safely.
- [x] Show related repair/document links on customer and staff ticket details and associate repair support replies with the job.
- [x] Display recent customer-visible order, repair, invoice and support activity on the account overview, with privacy-safe links, clear dates and an empty state.
- [x] Add support-request search by ticket, repair, order or invoice, status/category filters, linked references, honest empty states and mobile-friendly pagination.
- [x] Add regression tests covering job/invoice contextual help, account isolation, forged IDs, staff form ownership, and filtering internal customer messages.
- [x] Include the customer-service-hub regression module in both existing Django CI test jobs.
- [x] Code-stage linked support, recent activity, navigation, search, secure document links and customer-ownership checks.
- [ ] Run Django migration checks, portal tests, permission scans, keyboard/mobile UI and production email verification during final integration; not certified.

## P5 staff command centre and CRM implementation
- [x] Extend permission-aware global search to leads, incoming enquiries, invoices and linked order references.
- [x] Include repair and support activity alongside orders, quotes, leads and enquiries in existing CRM timeline.
- [x] Wire verified customer prefill into existing quote/invoice, job-card and support-ticket creation forms; invalid IDs cannot select a customer.
- [x] Add permission-aware dashboard work-area shortcuts, accurate personal lead counts and preexisting personal assigned work.
- [x] Combine overdue follow-ups and unanswered first-contact alerts into one lead attention filter matching dashboard counts.
- [x] Add lead search (name, phone, product, quote and order) and retain status/owner/follow-up filters across pages.
- [x] Link a sales enquiry to an existing CRM customer only when its email matches exactly one customer; ambiguous matches are never merged or assigned automatically.
- [x] Block quotation conversion on duplicate customer email matches instead of selecting an arbitrary CRM identity; staff receives an actionable review message.
- [x] Flag duplicate customer emails in the staff CRM profile and suppress speculative unlinked lead/contact attribution without affecting truly customer-owned orders or jobs.
- [x] Restrict topbar creation menu to actual add permissions, with clear accessible control labeling.
- [x] Add focused tests for permission-aware search, customer form prefill, CRM timelines, lead queues and pagination, and role-aware dashboard.
- [x] Code-stage Phase 5: global search, permission-aware staff dashboard, CRM customer timelines and contextual creation, lead response/follow-up queues, and an existing lead → quotation → order handoff.
- [x] Add focused regression tests and wire them into both existing Django CI suites.
- [ ] Final verification: run Django suite/CI, role permissions, migrated database, staff navigation, responsive browser workflows and sales-to-payment integration. Not yet run or certified.

## P6 finance and field operations implementation
- [x] Separate purchase-order gross receipts, supplier returns and net goods value, using immutable receipt quantities and original purchase unit costs.
- [x] Make the value reconciliation visible to staff on the purchase order without claiming a supplier refund was issued.
- [x] Protect the product identity, variant, unit cost and supplier on already-received purchase lines, preventing historical valuation drift.
- [x] Prevent applying a stock adjustment twice using existing unique movement linkage and row locks.
- [x] Disallow new parts consumption for completed/cancelled jobs in both the UI and backend.
- [x] Make job status changes, cancellation part returns and history entries atomic to avoid half-written stock/job states.
- [x] Create a direct job expense ledger for actual, receipt-backed parts, labour, transport and subcontractor costs, without inventing rates or profits.
- [x] Restrict cost entry/view to explicit expense permissions; Finance and Manager roles receive these permissions after bootstrap.
- [x] Expose receipt-backed expenses and actual cost totals in the job detail screen, only to users with job expense permissions.
- [x] Add focused expense-entry, duplicate-reference, nonpositive cost and cost-data confidentiality regression tests.
- [x] Restrict payment refunds and reconciliation to finance permissions in backend and payment-history UI.
- [x] Require refund adjustment references, reject historical reference duplicates at the application layer, and enforce unique keys for all new refund adjustments.
- [x] Keep existing historical refunds untouched during migration (nullable unique idempotency key), avoiding destructive cleanup or failed constraints on legacy duplicates.
- [x] Ensure repeat reconciliation does not rewrite history; clarify that recording an adjustment is not proof of actual money disbursement.
- [x] Expose the job cost ledger read-only in Django admin, without editable historical transactions.
- [x] Separate operational reports from sensitive cost, profit and partner-payable reports by the existing billing margin permission.
- [x] Restrict sensitive reports CSV exports to finance permissions, including payment reconciliation exceptions.
- [x] Add a finance-only job-expense summary and per-job drill-down to existing business reports, explicitly excluding uncosted items and financial profit claims.
- [x] Add protected job-to-invoice comparison with customer ownership checks, one-to-one allocation rule, issued document validation, and explicit warnings about overlapping cost sources.
- [x] Enforce quote approval permission and atomic quote approval; protect cancelled/expired documents from approval.
- [x] Require payment verification permissions in the backend and review UI; allow read-only finance review without write access.
- [x] Add and stage approval, customer ownership and shared-invoice exception regression tests in the focused Django CI workflow.
- [x] Code-stage the full Phase 6 supplier, inventory, field-cost, refund, approval and finance-reporting workflow; integrations and access certification deferred.
- [x] Stage expense report access and finance CSV confidentiality tests in the focused CI suite.
- [ ] Run finance, stock-ledger and field-workflow integration tests at final verification.
- [x] Add immutable, permission-controlled customer pickup/delivery handover records with staff confirmation, READY-to-COMPLETED transition, portal visibility and duplicate protection; VPS migration and acceptance verification pending.

## P7 marketing and integrations implementation
- [x] Separate configured credentials from verified connections, and test only selected channels with an explicit empty-selection message.
- [x] Restrict Autopilot queue controls to Autopilot and priority posts, rather than unrelated marketing content.
- [x] Show recent failed/manual channel deliveries with the original error and review links; keep uncertain external posts blocked from automatic replay.
- [x] Make Publish Now feedback truthful: worker queued, not a guaranteed platform publication time.
- [x] Reject Publish Now for unselected channels or unrelated manually created posts, preserving queued-worker idempotency.
- [x] Require explicit, permission-controlled, single-channel manual publication confirmation and block marking active automatic deliveries as published.
- [x] Align canonical Merchant Center and multi-format feeds: omit physical listings lacking real images or positive prices; preserve the existing variant-specific price and availability rules.
- [x] Keep analytics opt-in when local storage is unavailable; resetting consent reloads to stop previously loaded tags before asking again.
- [x] Add focused social operator tests for selected-channel connection checks, Autopilot-only queue controls and failed-delivery review.
- [x] Avoid closing the wrong sales enquiry after an order: match tracked campaign links and avoid ambiguous same-email leads.
- [x] Label the attribution report's placed-order value separately from cash received, and cover it in regression tests.
- [x] Keep failed external-post outcomes in the manual review queue; prohibit blind worker replay while making confirmed manual status consistent with channel delivery records.
- [x] Test the manual override end-to-end, including permission checks, multi-channel rejection and duplicate prevention.
- [x] Complete Phase 7 conversion and consent code handoff; test coverage staged in the focused CI suite.
- [x] Mark Phase 7 coding complete; external API behavior, live conversion telemetry and browser consent remain pending certification.

## P8 production certification
- [x] Stage an isolated Phase 8 release-candidate gate that migrates a throwaway SQLite database and runs Django tests without accessing production.
- [x] Connect the candidate gate to the existing full CI workflow; include the strict Merchant Center fail-closed regression in focused CI.
- [ ] Confirm the GitHub Actions runner/workflow-start issue is resolved and **all checks pass** for the final commit.
- [ ] Run migration drift and upgrade rehearsal against a production-like database snapshot.
- [x] Add an optional read-only Playwright browser smoke script for Chromium/Firefox/WebKit at 320–1440px, covering public navigation, catalogue filters, product-page Merchant confidentiality, keyboard focus and horizontal overflow. Keep Playwright out of production Python dependencies.
- [ ] Execute complete Django suite, browser smoke on the final staging/production SHA, and manual real-device/mobile/keyboard checks; no passing browser results are claimed yet.
- [ ] Check payment, email, social-provider and Merchant Center sandbox/external-service outcomes.
- [ ] Validate backups, restore rehearsal, release rollback, monitoring and VPS readiness before production certification.
- [x] Add Phase 7 focused regression modules to the existing CI test gate.
- [x] Extend the PostgreSQL transaction test gate across purchasing, job-cost, refund and marketing-attribution workflows; successful execution still required.
- [x] Correct the public-media storage override in shared settings and enforce temporary database, media and backup locations inside the isolated Phase 8 gate.
- [x] Add isolated checksummed SQLite backup and restore verification to the offline candidate gate, separate from the required production-like PostgreSQL restore drill.
- [x] Verify archive readability and SQLite database integrity (not only hashes), reject unsafe manifest entries, and stage backup verifier tests in both CI jobs.
- [x] Record actual failing-to-start GitHub Actions run IDs; no runner, zero steps and no unsupported claim of a code test failure.
- [x] Clarify backup-health labels: manifest/file-size checks are monitoring signals, not verified restores.
- [x] Add an isolated local-only PostgreSQL restore rehearsal which independently checks SHA-256, restores a custom PostgreSQL dump into a disposable server, extracts normal public/private media and rejects unsafe archive paths and links; include focused tests in CI.
- [ ] Execute the isolated PostgreSQL + media restore rehearsal on the VPS or separate staging host against a real checksummed backup. Record the command's successful output, migration count, table count and restored media count. The code alone does not certify an actual restore.
- [ ] Verify staff quotation revision history and approved-quote conversion from the relevant forms, with mobile/role tests (DocumentRevision code is present).
- [x] Implement signed recipient handover capture using touch/mouse pad or image upload, server-side image rewrite, explicit recipient consent, protected staff/customer file access, duplicate protection and clear handling of legacy unsigned handovers.
- [ ] Verify signed handover on actual phones/tablets and exercise migration and focused/full tests on the VPS; signed handover is code-implemented but not device-certified.
- [x] Add manually reviewed offline INTERNAL technician note drafts on the existing staff job and technician bench pages, with per-account IndexedDB queue, 7-day expiry, unique client operation tokens and CSRF-protected server replay. Closed and changed jobs cannot silently receive stale data; no automatic background replay.
- [ ] Run desktop and mobile device tests for offline notes, logout/login account separation, browser storage permissions and server conflict handling. This is not yet production-certified.
- [ ] Implement or explicitly defer offline photo, inventory, time, status and payment writes; high-risk writes are intentionally online-only until their independent conflict/reconciliation designs are accepted.
- [x] Bind completed-order reviews to their exact originating order and enforce one review per order/product at database level; keep older unbound reviews without inventing order attribution. Preserve approval locks, moderation and idempotent replays; cover separate purchases and private-link access with regression tests.
- [ ] Run production-like migration, complete Django suite and real-device review/moderation acceptance; live SMTP and external-provider checks remain open.

## P6 coding handoff
The existing purchasing, stock, billing and operations subsystems remain the source of truth. Received purchase costs and suppliers are protected from historical edits. Job expenses are documented separately from invoice costs; job-to-invoice comparison refuses speculative allocation for shared invoices and cross-customer records. Refund adjustment references and reconciliation are protected against duplicates, and finance approvals and sensitive reports require existing permissions. Supplier returns and recorded refunds do not falsely imply a supplier payout or money movement. New migrations and regression modules are staged, **not deployed or integration-tested**. Final verification must cover database migrations, transactional concurrency, accounting reconciliation, account permissions and responsive screens.

## P5 coding handoff
Core workflows reuse `dashboard/overview.py`, `core/staff_views.py`,
`crm/views.py`, `marketing/views.py` and
`marketing/services.py`; there is no competing CRM data model.
Existing customer IDs are used to prefill new quotes, jobs and tickets.
Leads and unhandled enquiries are searchable with separate permissions.
Customer activity includes known orders, jobs, tickets, documents and
explicitly matched enquiry records. Legacy duplicate emails are flagged
for staff review, not merged or silently assigned. Queue filters now
correspond to the warning counts on the dashboard.
The normal order-to-lead conversion service and commercial document
workflow remain the canonical paths; they have not been duplicated.
**Remaining final certification:** Django migration check, role-by-role
end-to-end permissions, full CI suite, quote/order/payment provider
sandbox, keyboard/mobile browser runs and production verification.

## P4 coding handoff
Existing `crm.Customer` continues to own the portal data; no shadow CRM or
messaging database was introduced. A support ticket can attach to a customer-owned
order, repair, invoice, device or product, and both customers and staff can open
the linked records. The overview merges customer-visible events without showing
private staff notes; support requests are searchable/filterable with pagination.
Formal migrations, full tests, browser/mobile and SMTP checks are intentionally
deferred and are not certified as successful.

## P3 coding handoff
Coding coverage is in `commerce/views.py`, `commerce/forms.py`,
`commerce/fulfillment.py`, `commerce/staff_views.py`,
`commerce/customer_messages.py` and the existing `reliability/`
transaction and payment modules. Delivery fees are accepted only from priced
zones; an unpriced area requires staff quotation. Stock reservations, refund
checks, order status history and idempotent confirmation exist in the
underlying engines. Backend shipment and inventory-return safety restrictions
have been reinforced. **Not certified:** provider sandbox, shipping quote
rules, billing reconciliation, Django tests, and real-browser/mobile tests.
Do not claim a successful payment or delivery integration before validation.

## P2 initial staff catalogue-governance improvements
- [x] Show existing exact-name suggestions and duplicate SKU warnings on the product form, desktop and mobile.
- [x] Reject newly conflicting product and variant SKUs in server form validation without blocking unrelated legacy edits.
- [x] Apply the same SKU validation to the separate commercial product review editor, preventing a bypass through another staff screen.
- [x] Surface variant SKU validation errors beside the relevant fields.
- [x] Reuse existing product-quality issue codes for staff-side direct issue filtering.
- [x] Make the common-issue counts clickable and retain filters across pages.
- [x] Preserve the selected issue when a search or other filter has zero matches.
- [ ] Run staff UI and permission regression tests and verify real screen-size behavior.
- [x] Make iPhone HEIC/HEIF uploads browser-compatible by decoding, validating and converting to JPEG.
- [x] Use an atomic product gallery save with per-product upload ordering and cleanup of new files on failure.
- [x] Filter inventory product register by kind and publication; search verified brand and manufacturer part identifiers.
- [x] Make product/service metrics and quality-check navigation actionable from the staff product register.
- [x] Code-stage inventory workflows complete: existing bulk enrichment, product/media/specification editing, stock ledger and cycle counts, plus identity and mobile-HEIC fixes. Integrated verification and live-provider checks are deferred.

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
