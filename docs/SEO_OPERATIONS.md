# LEOSOFT SEO operations

Technical SEO makes pages understandable, crawlable and eligible for search
features. It does not guarantee a particular position. Sustainable ranking growth
comes from the combination of correct technical signals, useful original content,
accurate catalogue data, strong customer experience, brand searches and earned
links or mentions.

## Canonical production configuration

The production `.env` should include:

```dotenv
ALLTECH_PUBLIC_BASE_URL=https://leosoftug.com
ALLTECH_SEO_DEFAULT_TITLE=LEOSOFT UG LTD — Computers, technology and IT support in Uganda
ALLTECH_SEO_DEFAULT_DESCRIPTION=Shop computers and accessories, compare dependable options, request formal quotations, and book repairs, installations and business IT support in Uganda.
ALLTECH_SEO_DEFAULT_IMAGE_URL=https://leosoftug.com/static/img/leosoft-social-preview.jpg
ALLTECH_BING_SITE_VERIFICATION_TOKEN=
ALLTECH_INDEXNOW_KEY=
ALLTECH_INDEXNOW_ENABLED=0
```

Use one canonical origin consistently. Nginx or the CDN should redirect alternate
hosts such as `www.leosoftug.com` to `https://leosoftug.com` with a permanent
redirect after DNS and TLS have been verified.

## Discovery endpoints

- Sitemap index: `https://leosoftug.com/sitemap.xml`
- Product sitemap: `https://leosoftug.com/sitemaps/products.xml`
- Category sitemap: `https://leosoftug.com/sitemaps/categories.xml`
- Collection sitemap: `https://leosoftug.com/sitemaps/collections.xml`
- Brand sitemap: `https://leosoftug.com/sitemaps/brands.xml`
- Image sitemap: `https://leosoftug.com/image-sitemap.xml`
- Robots file: `https://leosoftug.com/robots.txt`
- Google Merchant feed: `https://leosoftug.com/feeds/google-merchant.xml`
- IndexNow key: `https://leosoftug.com/indexnow-key.txt`
- Staff control center: `https://leosoftug.com/staff/seo/`

The main sitemap is an index. Submit only the sitemap index to search engines unless
a diagnostic specifically requires an individual section.

## Google Search Console

1. Create or select the domain property for `leosoftug.com`.
2. Prefer DNS verification because it covers HTTPS, HTTP and all subdomains.
3. The existing HTML meta-token field remains available under Growth Settings when
   DNS verification is not being used.
4. Submit `https://leosoftug.com/sitemap.xml` under **Sitemaps**.
5. Inspect the homepage, one clean category page and several product URLs.
6. Review **Page indexing**, **Product snippets**, **Merchant listings**, **HTTPS**
   and **Core Web Vitals** after Google has processed the release.
7. Do not repeatedly request indexing for every URL. Use the sitemap and request
   indexing only for a small number of important newly launched or corrected pages.

## Bing Webmaster Tools and IndexNow

Bing Webmaster Tools can import a verified Search Console property or use the
`ALLTECH_BING_SITE_VERIFICATION_TOKEN` meta value. Submit the same sitemap index.

Create a random IndexNow key between 32 and 128 hexadecimal-style characters, add
it to the protected production `.env`, deploy, then verify that the key is returned
from `/indexnow-key.txt`.

Dry run:

```bash
python manage.py submit_indexnow --recent-hours 24 --dry-run
```

Enable and submit only after the dry run and key endpoint are correct:

```dotenv
ALLTECH_INDEXNOW_ENABLED=1
```

```bash
python manage.py submit_indexnow --recent-hours 24
```

For a controlled first submission:

```bash
python manage.py submit_indexnow --all-indexable
```

IndexNow is a change notification, not a ranking purchase or an indexing guarantee.

## Google Merchant Center

The feed contains published physical products that have a customer-visible image.
Products with active variants are emitted as separate items with a shared item group.

1. Create or verify the Merchant Center business.
2. Confirm the website ownership using the same verified domain.
3. Add `https://leosoftug.com/feeds/google-merchant.xml` as a scheduled feed.
4. Set the target country to Uganda and language to English unless the actual campaign
   uses a different market.
5. Confirm shipping, return and tax settings in Merchant Center. The feed must agree
   with the website and written business policies.
6. Review diagnostics before enabling paid campaigns or free listings.

Do not invent GTIN, MPN, brand, condition, availability, price, shipping or warranty
information. Correct the product record instead.

## Catalogue content standards

Every important physical product should have:

- a unique descriptive product name;
- a stable SKU;
- the real brand and manufacturer part number where assigned;
- GTIN only when the manufacturer assigned a valid identifier;
- an honest condition label: new, refurbished or used;
- a useful short description and a detailed original description;
- accurate price, variant price and availability;
- at least one clear actual or representative product image;
- meaningful image alt text;
- category placement and specifications customers genuinely compare;
- product-specific warranty, return, delivery and included-accessory information.

Use `/staff/catalogue-quality/` and `/staff/seo/` to find weak listings.

## Landing-page content strategy

The application now exposes clean pages for:

- `/catalog/products/`
- `/catalog/services/`
- `/catalog/category/<slug>/`
- `/catalog/collection/<slug>/`
- `/catalog/brand/<slug>/`

Search, sorting, price, condition and availability combinations remain available to
customers but are marked `noindex,follow`. This prevents a large number of thin or
duplicate parameter pages from competing with the clean landing pages.

Improve the clean pages by writing genuinely useful category descriptions. Explain:

- who the category is for;
- important specifications and compatibility questions;
- common use cases;
- condition and availability expectations;
- related installation, repair or support services;
- how quotations, delivery and after-sales support work.

Avoid copied manufacturer paragraphs and repetitive keyword lists.

## Content that can earn international traffic

Create original pages or articles around real expertise and customer questions, for
example:

- laptop buying guides by workload, not only processor name;
- refurbished-device inspection and grading methods;
- compatibility guides for RAM, SSDs, chargers and docking stations;
- repair diagnostics and common failure explanations;
- business IT setup, networking and maintenance checklists;
- school, NGO and SME procurement guides;
- transparent case studies with the customer’s permission;
- Uganda-specific delivery, power, warranty and software considerations.

A future editorial module should use stable article URLs, author information, visible
publish/update dates, Article structured data and strong links to relevant products,
services and category pages. Do not publish mass-generated thin pages merely to cover
keywords.

## Local and global authority

- Keep the Google Business Profile accurate and link it in Growth Settings.
- Keep business name, address, phone, opening hours and website consistent across
  reputable directories and social profiles.
- Ask real customers for honest reviews without incentives that violate platform rules.
- Earn links through suppliers, professional associations, schools, organisations,
  partnerships, useful research and genuinely reference-worthy guides.
- Avoid paid link networks, automated directory blasts, doorway pages and hidden text.

## Performance and accessibility

Ranking and conversion both benefit from a fast, stable and accessible experience.
Monitor:

- Largest Contentful Paint;
- Interaction to Next Paint;
- Cumulative Layout Shift;
- image dimensions and responsive formats;
- mobile navigation and form usability;
- keyboard navigation, headings, labels and contrast;
- server response time and database performance.

Validate important pages with representative mobile devices and slower connections,
not only a desktop office network.

## Monitoring cadence

Weekly:

```bash
python manage.py audit_seo
python manage.py audit_project
```

Monthly:

- compare Search Console clicks, impressions, queries and indexed pages;
- review Merchant Center diagnostics;
- review Bing crawl and IndexNow reports;
- inspect Core Web Vitals and important landing pages;
- improve categories and products with impressions but weak click-through rate;
- update inaccurate or stale products instead of changing dates without real content work;
- check that sitemap, robots, images and feeds remain publicly accessible.

Quarterly:

- complete a structured-data validation sample;
- audit redirects, broken links and duplicate titles;
- review the content roadmap against actual customer enquiries and sales;
- remove or consolidate obsolete thin pages;
- review competitors for useful customer experiences, never for copied content.

## Release verification

After deployment:

```bash
curl -I https://leosoftug.com/
curl -sS https://leosoftug.com/robots.txt
curl -sS https://leosoftug.com/sitemap.xml
curl -sS https://leosoftug.com/image-sitemap.xml
curl -sS https://leosoftug.com/feeds/google-merchant.xml
python manage.py audit_seo --strict
```

Also open one category, collection, brand, product and service page and confirm its
canonical URL, title, description and visible content match the page purpose.
