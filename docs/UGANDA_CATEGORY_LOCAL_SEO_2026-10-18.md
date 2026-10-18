# LEOSOFT — Uganda category SEO and Local Search implementation

Date: 2026-10-18. This complements
[the storefront redesign roadmap](STORE_REDESIGN_IMPLEMENTATION_2026-10-18.md).

## Delivered in code (pending deployment verification)

- The homepage's default title/description now target computers, laptops,
  accessories and IT support in Uganda without promising unverified stock,
  delivery speed, pricing or manufacturer authenticity.
- All existing `/catalog/category/<slug>/` pages retain their original
  canonical URLs, item-list structured data, breadcrumb schema, sitemaps,
  pagination and the `noindex` behavior of filtered/search results.
- Six main departments get distinct keyword-relevant defaults, even when the
  existing category description is long or missing.
- Category page H1 matches the actual department, and **one short sentence**
  replaces a reading-heavy hero; detailed educational content remains in
  the dedicated buying guides.
- Admins can override title, description and H1 separately for any category:
  **Django admin → Catalog → Categories → Google Search**.
- Staff see current preview text, published item count and permitted editing
  actions under **Staff → SEO control center**.
- Staff SEO control center also provides separate Google Business Profile and
  Merchant Center readiness links and accurate reminders about verified
  physical business facts, genuine reviews and manufacturer identifiers.
- Tests assert all six titles, canonical URLs, short intros, filtering
  `noindex`, staff overrides and admin dashboard rendering.

## Proposed default category search snippets

| Category | SEO title | Search description | Short visible H1 |
| --- | --- | --- | --- |
| Laptops | Buy Laptops Online in Uganda \| Leosoft UG | Browse laptops in Uganda for students, offices and everyday work. Compare available configurations, prices and condition at Leosoft UG. | Laptops in Uganda |
| Desktops | Desktop Computers & All-in-One PCs Uganda \| Leosoft | Explore desktop computers and all-in-one PCs for home or office in Uganda. Compare recorded specifications, pricing and availability at Leosoft UG. | Desktop Computers in Uganda |
| Networking | Wi-Fi Routers & Networking Equipment Uganda \| Leosoft | Explore Wi-Fi routers, switches and networking accessories in Uganda. Compare options and ask Leosoft UG about office networking and installation. | Networking Equipment & Wi-Fi |
| Printers | Printers, Scanners & Ink Supplies Uganda \| Leosoft | Explore printers, scanners and printing accessories in Uganda. Browse available products and request a quotation for home or office at Leosoft UG. | Printers & Scanners in Uganda |
| Storage | SSD, Hard Drives & Computer Storage Uganda \| Leosoft | Shop SSDs, hard drives and storage accessories in Uganda. Compare capacity, compatibility and prices before requesting your order at Leosoft UG. | Computer Storage & SSDs |
| Accessories | Computer Accessories & Tech Gadgets Uganda \| Leosoft | Explore mice, keyboards, chargers and other computer accessories in Uganda. Check product details, price and availability at Leosoft UG. | Computer Accessories in Uganda |

These are **defaults matched to real category names and slugs**, not
data migrations that rename/delete categories. A staff SEO override takes
precedence. Unknown categories have a unique, conservative fallback.

## What is *not* possible through a code commit

- Placing an organic link ahead of paid placements or guaranteeing a rank.
  Ad positions and local pack placement vary by query, device, location and
  user context.
- Claiming/verifying Google Business Profile on behalf of the owner, creating
  or artificially incentivizing 5-star reviews, or proving the pasted address
  and phone number are presently validated.
- Making Merchant Center products eligible by inventing GTIN/MPN, brand,
  condition, product photos, stock or shipping/returns. The existing strict
  merchant-readiness workflow still controls publication.
- Forcing Google to use a particular title or meta description. Google can
  generate title links/snippets from other page signals. Title/description
  lengths are recommendations, **not fixed Google character limits**.

## Business-side checklist

1. Verify the real address, phone, hours and homepage URL in Google Business
   Profile; use the same verified facts in `CompanySettings`. Do not silently
   overwrite production company details based on a proposal or pasted copy.
2. Ask real customers for **honest** reviews; never request only 5-star ratings
   or pressure customers to insert keywords.
3. Check Merchant Center free-listing status and reconcile actual prices,
   stock, condition, images, manufacturer identifiers, shipping and returns.
4. Use Search Console to submit the existing sitemap and inspect representative
   clean category pages. Allow indexing time.
5. Validate the source HTML title, canonical, snippet and H1 in actual
   production; run the guarded release gate before deployment.

## Release status

Category metadata code and regression tests are committed, **not
production-certified** until the full VPS gate, public HTTP checks and actual
Search Console/Business Profile validations have been performed.
