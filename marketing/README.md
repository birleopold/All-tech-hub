# LEOSOFT marketing automation

The marketing workspace is available to staff at:

```text
https://leosoftug.com/staff/marketing/
```

## Included capabilities

- Campaign planning, objectives, dates, audience notes and budgets.
- Reusable caption templates with product placeholders.
- Scheduled post queue for WhatsApp, Facebook, Instagram, TikTok, X, LinkedIn, YouTube, Telegram, Pinterest and email.
- Tracked campaign links with UTM parameters.
- Downloadable SVG QR codes for tracked links.
- Privacy-preserving click events; IP addresses are hashed and are not stored in plain text.
- Marketing lead pipeline with source, medium, campaign, product, status and estimated value.
- Automatic attribution of public contact-form enquiries.
- Continuously updated CSV, JSON and Google/Meta-style XML product feeds.
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
python manage.py migrate --noinput
python manage.py seed_marketing_templates
python manage.py check --deploy
python manage.py test marketing.test_automation marketing.test_social_marketing
python manage.py collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
curl -fsS https://leosoftug.com/healthz/
```

## Scheduling automation

The application does not claim to publish directly to social networks without their approved API credentials. Instead, due posts move automatically from `Scheduled` to `Ready to publish`.

Test manually:

```bash
python manage.py prepare_due_marketing_posts --dry-run
python manage.py prepare_due_marketing_posts
```

Run every 15 minutes with cron:

```bash
crontab -e
```

Add:

```cron
*/15 * * * * cd /home/admin/All-tech-hub && /home/admin/All-tech-hub/.venv/bin/python manage.py prepare_due_marketing_posts >> /home/admin/All-tech-hub/marketing-automation.log 2>&1
```

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

When creating a scheduled post, select a product and caption template and leave the caption blank. The system generates the caption automatically.

## Tracked links and QR codes

Create a link under **Marketing automation → Tracked links and QR codes**. Selecting a product automatically fills its public URL when the destination is left blank.

The public tracked link follows this pattern:

```text
https://leosoftug.com/marketing/r/CODE/
```

The redirect records a click, stores UTM attribution in the visitor session and forwards the visitor to the destination. QR codes point to the tracked link so printed posters, packaging, receipts and shop displays can be measured too.

## Product feeds

```text
https://leosoftug.com/marketing/feeds/products.csv
https://leosoftug.com/marketing/feeds/products.json
https://leosoftug.com/marketing/feeds/products.xml
```

Only published products and services are included. Feeds update from the database whenever they are requested.

## Direct platform publishing

Facebook, Instagram, TikTok, LinkedIn, YouTube and X each require separate developer applications, permissions, tokens, review processes and account eligibility. The scheduled-post model is designed as the stable internal queue. Approved platform adapters can later read `Ready to publish` posts, submit them through official APIs, save the external post URL and mark them as published.
