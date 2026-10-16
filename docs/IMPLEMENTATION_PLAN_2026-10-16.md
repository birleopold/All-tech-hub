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
| P2 | Product data and inventory | Bulk editing, images, verified specifications, duplicate checks, stock movements, multi-device image workflow; staff tests | Planned |
| P3 | Checkout and fulfillment | Guest/customer orders, precise delivery fees, payment method honesty, staff fulfillment queue, cancellation, idempotent confirmation, customer tracking | Planned |
| P4 | Customer service hub | Orders, repair status, warranties, invoices, tickets, documents and messaging connected without redundant profiles; ownership tests | Planned |
| P5 | Staff command centre and CRM | Universal search, priority queues, actionable KPIs, leads-to-quotes-to-orders, role-specific landing pages | Planned |
| P6 | Finance and field operations | Supplier receiving, repair/installation workbench, expense/margin reconciliation, safe refunds, approvals and financial drill-downs | Planned |
| P7 | Marketing and integrations | Channel status, selected-channel posting, manual override, consent and failed-job recovery, merchant data quality and measured conversion | Planned |
| P8 | Production certification | Automated test gates, accessibility and responsive smoke runs, release rollback, backup restore drill, security and integration checks | Planned |

## P1 work package (first implementation)
- [x] Share one canonical display grouping for customer brand filters, search suggestions and category/brand SEO pages without changing stored brand values.
- [x] Surface published brand spelling/capitalization inconsistencies on Staff → Catalogue quality with editable-listing search links.
- [x] Do not advertise an unquoted service as a zero-price offer in product metadata or structured data.
- [x] Add regression tests for brand grouping, filters, canonical brand route, staff warning and priced/unpriced services.
- [ ] Execute focused Django tests and full regression suite in the production-like runtime.
- [ ] Verify real small-screen and keyboard use of filters, cards and service pages.
- [ ] Review stock status, results pagination, empty-state recovery and conversion actions together.
- [ ] Confirm production catalogue has no misleading zero-price representation in external previews.

## P2–P8 delivery pattern
For each phase: inspect current models, views, templates and docs → document gaps → implement backend + UI together → add focused tests → confirm permissions and mobile behavior → run full regressions and deployment checks → update this board.

## Owner-dependent verification
Payment gateway provider configuration, SMTP deliverability, Meta/Telegram credentials and approvals, policy text, off-site backup credentials, and external uptime monitoring must be confirmed against actual production services. Do not substitute a mocked success for production verification.

## Research and engineering references
- Django 5.2 queryset and aggregation docs: https://docs.djangoproject.com/en/5.2/ref/models/querysets/
- W3C WCAG 2.2 touch target, form and error guidance: https://www.w3.org/TR/wcag/
- Existing project detail: docs/PROJECT_MATURITY_ROADMAP.md, docs/STOREFRONT_POLISH.md
