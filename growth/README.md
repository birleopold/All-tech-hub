# LEOSOFT growth marketing setup

The Growth workspace is available to authorised staff at:

```text
https://leosoftug.com/staff/marketing/growth/
```

It extends the existing Marketing Automation workspace with GA4 ecommerce events,
Search Console verification, Microsoft Clarity consent controls, Google Business
Profile data, Merchant Center feeds, saved-cart recovery, product alerts, content
packs, distribution groups and ambassador attribution.

## First deployment

```bash
cd /home/admin/All-tech-hub
git checkout main
git pull origin main
source .venv/bin/activate
pip install -r requirements.lock
set -a
source .env
set +a
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py bootstrap_roles
python manage.py check --deploy
python manage.py test growth.test_growth marketing.test_automation catalog.test_social_marketing
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
curl -fsS https://leosoftug.com/healthz/
```

The production PostgreSQL role may need `CREATEDB` temporarily while tests run.
Remove that permission immediately afterwards.

## Refresh the 15-minute automation service

The existing timer name is retained, but its service now runs the unified growth
command.

```bash
sudo cp /home/admin/All-tech-hub/deployment/leosoft-marketing-posts.service \
  /etc/systemd/system/leosoft-marketing-posts.service
sudo cp /home/admin/All-tech-hub/deployment/leosoft-marketing-posts.timer \
  /etc/systemd/system/leosoft-marketing-posts.timer
sudo systemctl daemon-reload
sudo systemctl restart leosoft-marketing-posts.timer
sudo systemctl start leosoft-marketing-posts.service
sudo journalctl -u leosoft-marketing-posts.service -n 50 --no-pager
```

Manual dry run:

```bash
python manage.py run_growth_automation --dry-run
```

The command:

- moves due scheduled posts to `Ready to publish`;
- sends the first saved-cart reminder after the configured inactivity delay;
- sends the second reminder only after its configured interval from the first;
- evaluates active back-in-stock and price-drop subscriptions.

SMTP must be configured before public reminder and alert emails can be delivered.

## Google Analytics 4

1. Create a GA4 property and web data stream for `https://leosoftug.com`.
2. Copy only the Measurement ID, which has the form `G-XXXXXXXXXX`.
3. Open **Staff → Marketing automation → Growth & analytics → Integration settings**.
4. Paste it into **GA4 measurement ID**.
5. Keep analytics consent enabled unless a reviewed privacy approach says otherwise.
6. Use GA4 DebugView or Realtime to verify events.

Implemented events:

```text
page_view
view_item_list
select_item
view_item
add_to_cart
view_cart
begin_checkout
generate_lead
purchase
```

Purchase is emitted once for the newly completed order and includes transaction
ID, item data, value, tax, currency and coupon.

## Google Search Console

1. Add `https://leosoftug.com/` as a URL-prefix property.
2. Choose the HTML tag verification method.
3. Google supplies a tag like:

```html
<meta name="google-site-verification" content="TOKEN_VALUE">
```

4. Enter only `TOKEN_VALUE` in **Search Console verification token**.
5. Deploy and open the website source to confirm the tag exists.
6. Complete verification in Search Console.
7. Submit:

```text
https://leosoftug.com/sitemap.xml
```

Do not remove the verification token after successful verification.

## Google Business Profile

External profile creation and verification must be completed inside the Google
account that owns LEOSOFT UG LTD. Then enter:

- the public Google Business Profile or Maps URL;
- the review-request URL;
- the Google Place ID, when available.

Optimisation checklist:

- use the exact real-world business name;
- use `Computer store` as primary category when accurate;
- add only categories matching genuine services;
- complete address or service area, phone, website and opening hours;
- upload logo, storefront, team, product and service photographs;
- add products and services;
- reply to customer reviews;
- keep website and profile contact details consistent.

The website uses these settings in local-business structured data.

## Microsoft Clarity

1. Create a Clarity project for `leosoftug.com`.
2. Copy the Project ID from the tracking code or project settings.
3. Enter only that ID in **Clarity project ID**.
4. Clarity loads only after the visitor grants analytics consent when consent is
   required.

## Merchant Center feed

Feed addresses remain stable:

```text
https://leosoftug.com/marketing/feeds/products.xml
https://leosoftug.com/marketing/feeds/products.csv
https://leosoftug.com/marketing/feeds/products.json
```

The Merchant feed exports only published physical products. Services are
excluded. Products with active variants are exported as variant rows using an
`item_group_id`.

Manage product metadata at:

```text
Staff → Marketing automation → Growth & analytics → Merchant feed metadata
```

Complete genuine data where available:

- brand;
- GTIN;
- manufacturer part number;
- condition;
- Google product category;
- custom campaign label;
- shipping label.

Never invent GTINs or manufacturer part numbers. When no valid identifier exists,
the feed sets `identifier_exists` to `no`.

Before connecting Merchant Center, verify and claim the website, configure the
real delivery charge and publish a return-policy page. Enter those values in
Growth settings.

## Saved-cart recovery

Cart recovery is explicit opt-in. Customers enter their email and tick a consent
box from the cart page. The system sends:

1. an immediate saved-cart link;
2. a first reminder after the configured inactivity period;
3. a second and final reminder after the configured interval from the first.

Each email contains an unsubscribe link. Completed orders mark matching saved
carts as recovered.

## Back-in-stock and price-drop alerts

Published physical-product pages include an alert form. Customers can request:

- a notification when an unavailable item returns; or
- a notification when the current price reaches their target.

Subscriptions are evaluated by the unified automation command. Triggered alerts
are marked inactive after successful delivery and contain an unsubscribe link.

## Content-asset generator

One product can generate six editable drafts:

- WhatsApp or Status copy;
- Facebook and Instagram caption;
- TikTok, Reels or Shorts script;
- LinkedIn business post;
- promotional email;
- poster copy.

Generated text must be reviewed for current price, availability, warranty,
delivery and platform rules before publishing.

## Distribution groups

The directory stores community channels separately from official business
profiles. Save Facebook groups, WhatsApp communities, Telegram channels,
LinkedIn groups and other relevant platforms with:

- audience description;
- group rules;
- best posting times;
- last posting date;
- an optional tracked campaign link.

Do not use group invitation links as the company profile links shown in the
website footer.

## Referral ambassadors

Each ambassador receives a public URL:

```text
https://leosoftug.com/marketing/ref/AMBASSADOR_CODE/
```

The system records referral clicks, attributed contact leads, completed orders,
revenue and calculated commission. Downloadable SVG QR codes are available for
printed materials.

Commission records begin as `Pending`. Staff should approve and mark them paid
only after confirming the order payment and return/cancellation status.

## Content Security Policy

The default policy now permits the official GA4 and Clarity hosts. If the
production `.env` defines `ALLTECH_CONTENT_SECURITY_POLICY`, that environment
value overrides the code default and must be updated manually to permit:

```text
https://www.googletagmanager.com
https://www.google-analytics.com
https://*.google-analytics.com
https://www.clarity.ms
https://*.clarity.ms
https://c.bing.com
```

Keep CSP in report-only mode during verification, inspect browser console reports,
then enforce it after confirming all required resources are allowed.
