# Leosoft Google Organic Readiness — live account audit (2026-10-18)

Scope: existing https://leosoftug.com only. No paid Google Ads, fabricated inventory, fabricated reviews, or duplicate Business Profile.

## Verified integrations (Windsor.ai)
- Google Analytics 4 property: leosoft ug (545512966)
- Google Ads: Leosoft Ug Google Ads account (118-187-9242); no recent campaign-performance rows in the queried seven-day window.
- Google Search Console: sc-domain:leosoftug.com and https://leosoftug.com/
- Merchant Center: Leosoft Ug (5836415711)
- Google Business Profile: Leosoft Uganda (locations/6295907081872526970)

## Confirmed Merchant Center diagnostics
- 179 product rows returned; all are associated with source accounts/5836415711/dataSources/10735812404.
- Availability: 169 OUT_OF_STOCK; 10 IN_STOCK.
- Missing brand on 116; GTIN field absent on all 179; no complete brand+MPN pair; 4 missing displayed currency code.
- Google reported country-specific statuses: Uganda 0 active, 27 pending, 0 disapproved; US 82 disapproved, India 37 disapproved. These are country-item status records, not distinct products. Do not sum them as unique inventory.
- **First action:** inspect the source 10735812404 and its fetch/automatic additions mechanism. Existing approved feed is /feeds/google-approved.xml (see GOOGLE_MERCHANT_EXISTING_SITE_SETUP.md); do NOT add an extra overlapping primary source before reconciling existing source and duplicate product IDs.
- Inspect Merchant Center Products > Needs attention for specific item/account policy reasons; Windsor.ai fields available here don't expose item-level issue descriptions.
- Confirm approved merchant feed actually deployed, 200 status, XML well formed, strict-readiness headers and actual approved item count on VPS; then review primary data source URL/fetch status. This verification has NOT yet been performed.
- Review actual stock item-by-item. Out-of-stock must remain out-of-stock if accurate. Correct stock in the Leosoft inventory source of truth, never fake feed availability.
- Verify actual brand and manufacturer identifiers using packaging/specs: GTIN if genuinely assigned, otherwise authentic brand+MPN where applicable. Do not invent identifiers.
- Fill missing prices/currency only where valid and ensure feed page price and structured data agree. Validate merchant shipping and returns against actual published business policies.
- Confirm country targets: serve Uganda first; disable accidental extra-country targets only if no real delivery service/policy covers them. Uganda is a Google beta target country for listings; eligibility depends on product and account policy.
- Verify free listings are enabled and no Ads spend begins during readiness work.

## Search Console
- Search queries from last 30 days show actual visibility, including 'gaming laptop price in uganda', 'used gaming laptops', 'hp elitebook vpro', and 'motherboard price'. Low-click data is not evidence of a technical penalty.
- Check indexing/coverage, sitemaps, canonical URLs, Product snippets/Merchant listing enhancements and rich-result warnings in Search Console. Separate valid crawled product detail pages from staff/login routes.
- Existing robots template disallows /staff/, /admin/, /accounts/, /portal/, /cart/ and links sitemap.xml. Confirm production response; do not block public catalog pages.

## Analytics
- On 2026-10-12 through 2026-10-18 (partial last day), GA4 recorded 48 sessions, 356 page views and 0 ecommerce purchases. Also observed 95 form_start, 95 form_submit, 26 view_item, 137 view_item_list, and 1 select_item.
- Significant /staff/ traffic means analysis should separate internal staff/admin users from prospective customer sessions. Set and verify internal-traffic and referral exclusions according to actual business environment; don't globally exclude all Kampala or all authenticated customer traffic.
- Verify consent-aware event tracking on public pages: view_item, view_item_list, select_item, search, click_to_call, whatsapp_order_click, lead_submit; attach product IDs and source attribution without collecting phone numbers or sensitive messages as event labels.
- Event count is not purchase count. Do not treat WhatsApp click as successful sale. Deduplicate outbound click tracking and ensure conversions reflect verified business outcomes.

## Existing Google Business Profile
- Leosoft Uganda; website https://leosoftug.com/; category Computer service; Kampala Plaza, Kampala Road, Kampala; phone 0706 488229; Mon–Sat 09:00–18:00; rating 5 from one review.
- Confirm operational truth for address, contact, hours, verified status, photos, services, customer-support routes, and whether walk-in retail is eligible. Add genuinely applicable extra categories; do not keyword-stuff profile name or create duplicates.
- Ask actual customers for reviews without incentives and respond factually. Never create fake reviews.

## Implementation acceptance checks
1. Existing URL, no replacement website or duplicate business listings.
2. Approved feed deployed and fetched by the *correct current data source*; 0 erroneous stock claims; item IDs stable; no overlapping primary sources.
3. Uganda active product count rises only for products Google actually approves (not by local code assumption); pending/disapproved investigated by actual issue text.
4. Public product schema and feed match stock, currency, identifiers, price and image; Search Console sitemap/indexing checked.
5. GA4 staff traffic isolated and verified WhatsApp/call/lead events available without duplicate triggering.
6. Business Profile address, category, hours, website, service area and contact verified; more genuine photos/reviews over time.
7. Recheck a 7/30-day baseline after changes before considering any paid Google Ads.

## Permissions / limitations
Windsor.ai currently offers READ access for Search Console, Merchant Center and Google Business Profile; no write actions appeared for these connectors. Merchant account settings, reviews, feeds and profile edits cannot be claimed as changed through Windsor.ai. Repository preparation is distinct from VPS deployment and Google's own approval.
