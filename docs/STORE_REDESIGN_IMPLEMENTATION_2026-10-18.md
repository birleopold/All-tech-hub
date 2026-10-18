# LEOSOFT storefront transformation — complete implementation tracker
Started: 2026-10-18 · Repository: birleopold/All-tech-hub

## Non-negotiable design principles

- Make the homepage a **shop**, not a reading page: campaigns, visual departments,
  product grids, genuine deals, three service cards and short trust links.
- Use authentic product/technician images, not invented stock, reviews,
  countdowns, savings or Merchant approvals.
- Complete the staff workflow as well as the customer screen; a feature that
  cannot be configured, previewed, audited or reached in navigation is not done.
- Preserve repairs, quotations, guest checkout, permissions, existing URLs,
  GA/Clarity consent and SEO buying guides. Move education to its own pages.
- Accept 320px phones, tablets, laptops, desktop and larger screens; keyboard,
  screen reader, reduced-motion and poor-network journeys count.
- Commit each phase independently; run the full guarded release gate before
  deploying production. Committed code is not the same as a passing VPS run.

## Phases and acceptance criteria

| Phase | Scope | Implementation | Deployment / acceptance |
| --- | --- | --- | --- |
| P0 | Baseline, cache and release SHA | Existing release gate and SHA health checks; roadmap established | Must confirm newest HTML and static assets in uncached mobile/desktop browser |
| P1 | Product-first homepage, one authentic visual hero, two promo tiles, visual category shortcuts and compact trust section | **Code staged on main:** campaign template, category tile rail, CSS, graceful default if no campaigns, no auto-rotating carousel | Django tests, mobile screenshots, staging visual and performance verification pending |
| P2 | Truthful price/stock, product card hierarchy, laptop decision specs, discounts and fast enquiry/cart CTAs | **Code staged:** recently stock-confirmed available products first; recorded processor/RAM/SSD summaries; savings badges; one dominant card CTA; product-detail highlights | Test exact-stock validity with actual inventory; no false availability or manufacturer IDs |
| P3 | Product details: gallery, mobile sticky cart/contact, verified condition/warranty, comparison and related products; longer details below buying decisions | **Code staged:** compact specs, gallery swipe hint, variant-aware mobile sticky purchase button, live selected-variant price synchronization, honest availability text; underlying cart logic preserved | Full gallery/variant/cart/enquiry journey and accessible specs on iPhone/Android/browser pending |
| P4 | Mobile catalogue: tappable category shortcuts, focused search/filter, simpler guest checkout, delivery and total clarity | **Code staged:** guest checkout explanations, optional consent controls, responsive purchase CTA and live delivery-dependent total; unselected delivery area no longer falsely appears to have final zero shipping | End-to-end checkout/pickup/delivery/WhatsApp/mobile keyboard checks pending |
| P5 | Staff campaign controls: create/edit/disable, media and real product, priority, dates, safe destinations, audit log and navigation | **Code staged:** `HomepagePromotion`, migration, staff workspace, permissions, desktop/phone text preview and newly uploaded image preview before saving | Run Django/device tests and inspect visual fidelity; full-page staging preview remains pending |
| P6 | Trust/marketing: verified reviews, genuine savings, delivery/warranty facts, promotion/category clicks, GA4/Clarity consent, campaign effectiveness | **Code staged:** event metadata for the 3 campaign placements and category shortcuts, wired to existing opt-in GA4; product reviews/consent code already present | Verify attribution, GA4 debug events, conversion follow-through and real consent on Android/iPhone; controlled A/B experiments remain pending |
| P7 | Accessibility, speed, real devices, external providers, merchant data and release certification | Existing guarded Phase 8 suite, browser smoke and restore rehearsal | Execute final full VPS suite and restore; fix GitHub runner; test iOS/Android; verify provider settlement and truthful SKU/stock |
| P8 | Uganda/local SEO: category metadata, compact headings, clean canonicals, staff controls, GBP/Merchant eligibility checks | **Code staged:** six department presets, staff SEO preview/overrides, home defaults, tests and provider checklist in [Uganda SEO handover](UGANDA_CATEGORY_LOCAL_SEO_2026-10-18.md) | Deploy, inspect live category HTML, verify true business address in GBP, Merchant readiness, Search Console crawl/indexing |

## Phase P1/P2/P5 code included in initial package

- `merchandising.HomepagePromotion`: optional local-path CTA, published
  product or approved photo, real start/end schedule, per-slot priority and
  publication toggle. **Do not use countdown timers for unscheduled offers.**
- Staff: **Reports & growth → Homepage campaigns**; marketers with existing
  scheduled-post management permission or owners with campaign permission
  can edit, and edits create audit events. No staff-only readiness details
  are exposed on the public homepage.
- Homepage: visual hero, two support tiles, six image-first category chips,
  concise listings/deals/services/trust. Real product photo replaces generic
  artwork when available. No education walls or repetitive brand blocks.
- Featured products: bounded candidate pool, stock physically checked within
  30 days favored, then recorded availability and featured flag. **Stock
  records are not silently modified**, no new product is marked verified.
- Cards and product details: processor, RAM and storage shown *only when
  recorded*. Genuine comparison-price savings only when higher than current
  price; actions and mobile touch targets simplified.
- Empty/missing/expired creative uses a safe, product-oriented fallback.

## Owner-dependent facts that code must never manufacture

Real stock quantities; manufacturer GTIN/MPN; model/brand inspection; actual
condition and charger; shipping fees and service availability; payment-provider
callback, refund and settlement evidence; real reviews and Merchant Center
approval. Staff must fill the underlying records truthfully.

## Testing sequence

1. In the repository: targeted campaign tests, template compilation, migration
   drift check, accessibility-lint and full Django test suite.
2. On the VPS: `bash scripts/final_release_closeout.sh` (guarded and logged).
3. After the tested SHA is deployed: uncached HTML/style on real phone/tablet;
   product card and variant actions; iPhone/Android search/filter, checkout,
   actual stock; staff campaign dates, permissions and opt-in analytics.
4. Real isolated PostgreSQL + private media restore and external providers.
5. Mark **VERIFIED** only for tests observed passing. Until then all newly
   committed phases remain **candidate code**.

## Rollout rules

Staff should populate the hero and two secondary slots with genuine creative
and confirm availability before promoting a product. An inactive campaign
falls back to the existing LEOSOFT shopping page; campaign end dates should
automatically remove promotional copy. Never replace a healthy live release
with an untested candidate or bypass failing Django tests.

## Next implementation package — staff preview and guest checkout

- The marketing editor now includes preview controls for desktop and phone
  proportions. Campaign headline, eyebrow, supporting text and action label
  update before save. Product and creative image previews use the last
  saved media to avoid uploading unsaved customer-facing creative.
- Guest checkout now clearly states **no account required** and explains
  email purpose. Optional promotional consent is grouped into a disclosure,
  while delivery charges and the existing final amount remain server-backed.
- The early gate compiles checkout and staff campaign templates and checks
  the preview JavaScript syntax before running full tests.
- **Pending:** true full-page staging campaign preview, real device journey
  acceptance, live payment, delivery provider and client-approved creatives.

## Next product and service refinement package

- Service tiles use authentic product/service photography when present; clear
  pictograms remain the fallback. The homepage stays compact, with no extra
  long educational sections.
- Supplementary buying hubs on product detail pages remain crawlable and
  accessible through a keyboard-operable disclosure rather than dominating
  the purchasing screen.
- Product card and detail regression tests now cover recorded RAM/storage,
  processor and warranty highlights. No claim is generated for an unset fact.
- Browser and full deployment test evidence are still pending.

## Uganda search visibility, category pages and staff controls

Six high-intent department types now have concise searchable titles, descriptions
and H1s, with manual staff overrides and no homepage reading walls. Existing
URLs, filters, `noindex`, structured breadcrumbs and sitemap remain intact.
See [SEO implementation details](UGANDA_CATEGORY_LOCAL_SEO_2026-10-18.md).
Google Business Profile verification, truthful product/stock data, Merchant
approval and ranking improvements remain independent operational steps.

## Homepage campaign measurement (consent-aware)

Campaign hero and both support tiles emit GA4 `select_promotion` with
nonpersonal promotion ID/name and placement. Visual categories emit
`select_content`. Events reuse `static/js/marketing_analytics.js`, so they
only send when the existing integration has loaded under the site's consent
rules. This does **not** enable tracking on decline, create a new cookie,
or replace first-party checkout/order evidence. Analytics conversion
dashboards should be validated on real mobile visits before claiming gains.

## Competitor-inspired customer journey — latest continuation

The latest source changes prioritize the mobile product decision flow rather
than adding more text to the homepage:

1. An available, single-configuration product uses its **existing cart form**
   from the mobile sticky bar. Unavailable items use **Enquire**, not a
   misleading cart action. Unpriced services use **Request quote**.
2. Variant-based products show **Choose option** until a valid option is
   selected. Selecting one updates the visible purchase-panel and sticky
   price, while the existing server-side cart rules still validate choice,
   quantity and inventory. The URL query `?variant=<id>` remains supported.
3. A short gallery swipe hint appears for multi-image products. Existing zoom,
   arrow navigation, reduced-motion handling and responsive loading remain.
4. Delivery checkout no longer presents a merchandise-only number as the
   final delivery total: the preview explicitly asks for a delivery area,
   calculates the corresponding fee when chosen and identifies pickup.
5. Staff campaign editing now previews newly selected local creative before
   uploading or publishing, with blob URLs revoked when replaced or leaving.
6. New regression tests cover shopping states, gallery, campaign previews,
   mobile checkout pricing text and client-side synchronization. JS syntax
   has been checked independently; full Django/VPS/device certification has
   **not** been observed.

No automatic stock assertion, artificial countdown, fake deal, injected
Google rating or marketing-consent bypass is introduced.

## Google Merchant Center — existing website automatic product feed

Staff now have a separate, always-strict data source URL:
`https://leosoftug.com/feeds/google-approved.xml`. Google can fetch
this regularly without extra manual exports once an account owner links
this URL in Merchant Center. Existing `/feeds/google-merchant.xml` remains
for backward compatibility. The new source exports only expressly enabled,
fully merchant-ready listings; an empty source is expected until genuine
photos, brand/identifiers, stock/price, condition and shipping are approved.
The SEO control center shows the feed and available controls. The read-only
`audit_google_feed` command checks the exact generated feed contents.
Full details and the owner-only Google linking steps:
[Google Merchant existing-site setup](GOOGLE_MERCHANT_EXISTING_SITE_SETUP.md).

**Account connection was not performed:** login/ownership confirmation
requires explicit access and verification in Google, and site code cannot
claim that these steps have already succeeded. Deployment and feed checks
are pending the full production release gate.
