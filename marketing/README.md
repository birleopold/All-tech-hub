# LEOSOFT marketing automation

The Marketing Automation workspace is available to staff at:

```text
https://leosoftug.com/staff/marketing/
```

The complementary Growth & Analytics workspace is available at:

```text
https://leosoftug.com/staff/marketing/growth/
```

Detailed setup for GA4, Search Console, Clarity, Merchant Center, Google Business
Profile, saved-cart recovery, stock alerts, content generation, distribution
groups and ambassadors is documented in [`../growth/README.md`](../growth/README.md).

## Included capabilities

- Campaign planning, objectives, dates, audience notes and budgets.
- Reusable caption templates with product placeholders.
- Scheduled post queue for WhatsApp, Facebook, Instagram, TikTok, X, LinkedIn,
  YouTube, Telegram, Pinterest and email.
- Tracked campaign links with UTM parameters.
- Downloadable SVG QR codes for tracked links.
- Privacy-preserving click events; IP addresses are hashed and are not stored in
  plain text.
- Marketing lead pipeline with source, medium, campaign, product, status and
  estimated value.
- Automatic attribution of public contact-form enquiries.
- Merchant-compatible CSV, JSON and XML physical-product feeds.
- Channel click, lead and conversion summaries.

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
python manage.py seed_marketing_templates
python manage.py check --deploy
python manage.py test growth.test_growth marketing.test_automation catalog.test_social_marketing
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
curl -fsS https://leosoftug.com/healthz/
```

The regular deployment script performs the migration, role and caption-template
steps automatically:

```bash
cd /home/admin/All-tech-hub
./deployment/deploy.sh
```

## Unified scheduling automation

The application does not claim to publish directly to social networks without
their approved API credentials. Due posts move automatically from `Scheduled`
to `Ready to publish`.

The same 15-minute automation service now also processes consented saved-cart
reminders and active back-in-stock or target-price alerts.

Test manually:

```bash
python manage.py run_growth_automation --dry-run
python manage.py run_growth_automation
```

### Recommended: systemd timer

```bash
sudo cp /home/admin/All-tech-hub/deployment/leosoft-marketing-posts.service \
  /etc/systemd/system/leosoft-marketing-posts.service
sudo cp /home/admin/All-tech-hub/deployment/leosoft-marketing-posts.timer \
  /etc/systemd/system/leosoft-marketing-posts.timer
sudo systemctl daemon-reload
sudo systemctl enable --now leosoft-marketing-posts.timer
sudo systemctl restart leosoft-marketing-posts.timer
sudo systemctl status leosoft-marketing-posts.timer --no-pager
sudo systemctl list-timers --all | grep leosoft-marketing
```

Inspect a run:

```bash
sudo systemctl start leosoft-marketing-posts.service
sudo journalctl -u leosoft-marketing-posts.service -n 50 --no-pager
```

Use either the systemd timer or a cron fallback, not both.

## Caption placeholders

Reusable caption templates support:

```text
{product_name}
{price}
{currency}
{category}
{url}
{company}
{hashtags}
```

When creating a scheduled post, select a product and caption template and leave
the caption blank. The system generates the caption automatically.

## Tracked links and QR codes

Create a link under **Marketing automation → Tracked links and QR codes**.
Selecting a product automatically fills its public URL when the destination is
left blank.

The public tracked link follows this pattern:

```text
https://leosoftug.com/marketing/r/CODE/
```

The redirect records a click, stores UTM attribution in the visitor session and
forwards the visitor to the destination. QR codes point to the tracked link so
printed posters, packaging, receipts and shop displays can be measured too.

## Product feeds

```text
https://leosoftug.com/marketing/feeds/products.csv
https://leosoftug.com/marketing/feeds/products.json
https://leosoftug.com/marketing/feeds/products.xml
```

Only published physical products are included. Services are excluded. Products
with active variants are exported as separate variant rows.

## Direct platform publishing

Facebook, Instagram, TikTok, LinkedIn, YouTube and X each require separate
developer applications, permissions, tokens, review processes and account
eligibility. The scheduled-post model is the stable internal queue. Approved
platform adapters can later read `Ready to publish` posts, submit them through
official APIs, save the external post URL and mark them as published.
