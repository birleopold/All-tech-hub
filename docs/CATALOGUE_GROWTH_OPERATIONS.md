# LEOSOFT catalogue growth operations

This workflow turns the technical SEO and merchandising foundation into accurate,
maintainable catalogue growth. It is designed to borrow the strongest discovery,
commercial-page and product-information patterns from successful technology stores
and marketplaces without turning LEOSOFT into an unverified multi-seller platform.

## Staff workspaces

- Catalogue quality: `/staff/catalogue-quality/`
- Bulk catalogue enrichment: `/staff/inventory/catalogue-enrichment/`
- SEO, Merchant and query opportunities: `/staff/seo/`
- Individual commercial review: `/staff/inventory/products/<id>/commercial/`
- Full product editor: `/staff/inventory/products/<id>/`

## Safe order of work

### 1. Correct repeated facts in controlled groups

Use bulk enrichment only when the selected products genuinely share the same fact.
Good examples include:

- all selected products are verified Dell products;
- all selected units were physically confirmed as refurbished;
- one documented warranty period applies to every selected product;
- one delivery note or shipping fee applies to the selected stock;
- missing internal SKUs need stable LEOSOFT stock codes;
- blank gallery alt text needs a descriptive product-based fallback.

The bulk workflow never generates GTINs or manufacturer part numbers and never
enables Merchant publication. It does not mark a condition as verified unless an
explicit condition was selected during that action.

### 2. Complete each important product individually

Open the commercial review for high-value and high-search products. Confirm:

- exact brand and model;
- internal SKU;
- manufacturer GTIN or brand-and-MPN only when genuinely assigned;
- new, refurbished or used condition;
- condition notes for refurbished and used products;
- processor and generation;
- RAM capacity and type;
- storage capacity and type;
- screen size and resolution;
- touchscreen and graphics;
- operating system;
- battery and keyboard notes;
- charger and accessories included;
- warranty period;
- actual-photo confirmation;
- price, stock and delivery verification dates;
- verified Merchant shipping price or free-shipping confirmation.

Use the full product editor for gallery images, variants and stock structure.

### 3. Review Merchant readiness

Run:

```bash
python manage.py audit_merchant
```

The SEO control center shows average readiness, common blockers and the lowest-
readiness products. Merchant approval remains separate from data completion.

A product should be intentionally Merchant-enabled only after staff confirm its
public page, price, stock, images, identifiers, condition, shipping and written
customer terms. Deployment fails when a Merchant-enabled product still has blocking
gaps.

Keep strict feed publication disabled while correcting existing catalogue data:

```dotenv
ALLTECH_MERCHANT_STRICT_READINESS=0
```

After the reviewed products are intentionally approved and the feed has been tested,
enable strict mode:

```dotenv
ALLTECH_MERCHANT_STRICT_READINESS=1
```

In strict mode, incomplete and unapproved products are excluded rather than being
published with assumed facts.

### 4. Use Search Console data to choose the next content work

In Google Search Console:

1. Open **Performance** and select the required date range.
2. Open the **Queries** table.
3. Export the table as CSV.
4. Upload it at `/staff/seo/`, optionally recording the report dates.

The application highlights queries with useful impressions and positions between 1
and 30, especially page-one and near-page-one opportunities with weak click-through
rates. This data should guide title, description, commercial-hub, product and guide
improvements; it must not lead to repetitive keyword stuffing.

The same import can be run on the server:

```bash
python manage.py import_search_console /path/to/Queries.csv \
  --date-start 2026-07-01 --date-end 2026-07-31
```

No Search Console password, API key or OAuth token is stored by this feature.

## Commercial landing pages

Commercial hubs now:

- use the cheapest active variant price rather than the base price alone;
- show live matching and available-product counts;
- paginate with stable canonical, previous and next URLs;
- include accurate ItemList and FAQ structured data;
- link to related commercial hubs and buying guides;
- link products back to relevant hubs and technical guidance.

Maintain these pages through Django administration. Keep their introductions,
buying guidance and FAQs original, specific and useful. A page should explain real
customer choices instead of repeating a phrase merely to target search traffic.

## Publication principles

- Never create a fake GTIN, MPN, review, former price, saving, warranty or stock count.
- Do not mark every second-hand computer as new.
- Do not confirm actual photos unless the displayed gallery represents the unit or
  stock being sold.
- Do not record verification dates without performing the check.
- Unpublish obsolete tracked products when they are unavailable and no enquiry or
  replacement strategy exists.
- Keep out-of-stock pages only when they retain genuine customer value, alternatives
  and a realistic restock or sourcing route.
- Use product titles that are complete and readable, not keyword lists.

## Release checks

The production deployment now runs:

```bash
python manage.py audit_seo --strict
python manage.py audit_merchant --strict
```

The Merchant audit only blocks deployment when a product was intentionally enabled
but still has missing facts. Unapproved catalogue work remains visible as an audit
priority without preventing ordinary releases.

After deployment, verify:

```bash
curl -I https://leosoftug.com/laptop-prices-in-uganda/
curl -I https://leosoftug.com/dell-laptops-uganda/
curl -I https://leosoftug.com/feeds/google-merchant.xml
python manage.py audit_merchant
```

Also open one commercial page with more than one page of products and confirm that
prices, availability, pagination and related guidance match the live catalogue.
