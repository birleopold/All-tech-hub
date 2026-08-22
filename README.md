# LEOSOFT UG LTD

LEOSOFT UG LTD is a Django platform for technology retail orders, inventory,
purchasing, billing, repair jobs, customer support, reporting, and a customer
portal.

It includes an append-only stock movement ledger, customer and supplier
returns, payment reconciliation, refunds with credit notes, invoice aging,
Mobile Money payment recording, and authenticator-app two-factor security.

The project retains the existing `ALLTECH_` environment-variable names for
backward compatibility.

## Production target

The current production deployment is configured for:

```text
Company:            LEOSOFT UG LTD
Domain:             leosoftug.com
Domain registrar:   Namecheap
Ubuntu user:        admin
Application path:   /home/admin/All-tech-hub
Virtual environment:/home/admin/All-tech-hub/.venv
Environment file:   /home/admin/All-tech-hub/.env
Gunicorn service:   leosoft_gunicorn
Gunicorn address:   127.0.0.1:8010
PostgreSQL database:leosoft_prod
PostgreSQL user:    leosoft_user
Deployment branch:  origin/main
```

Future VPS updates use:

```bash
cd /home/admin/All-tech-hub
git checkout main
git pull origin main
```

The complete server setup guide is in
[`deployment/README.md`](deployment/README.md).

## Namecheap DNS setup

In Namecheap:

1. Sign in and open **Domain List**.
2. Click **Manage** beside `leosoftug.com`.
3. Open **Advanced DNS**.
4. Under **Host Records**, add these records using the VPS public IPv4 address:

```text
Type       Host    Value             TTL
A Record   @       VPS_PUBLIC_IP     Automatic
A Record   www     VPS_PUBLIC_IP     Automatic
```

5. Save each record using the green checkmark.
6. Remove conflicting `A`, `CNAME`, URL Redirect, Masked Redirect, or Permanent
   Redirect records for `@` or `www`.

The domain must be using Namecheap BasicDNS, PremiumDNS, or FreeDNS for Host
Records to be managed from the Advanced DNS page.

Check DNS after saving:

```bash
getent hosts leosoftug.com
getent hosts www.leosoftug.com
```

Both names should resolve to the VPS public IP before running Certbot.

## Local setup

Python 3.12 is the supported development and CI runtime. Version managers can
read the repository's `.python-version` file automatically.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py bootstrap_roles
python manage.py runserver
```

For an exactly reproducible environment, install `requirements.lock` instead.

Django does not load `.env` automatically. Set the variables in your shell,
service manager, container platform, or deployment environment.

## Staff roles

Create or refresh the standard roles:

```powershell
python manage.py bootstrap_roles
python manage.py bootstrap_roles --assign alice --role Manager
```

The standard roles are Technician, Sales, Inventory, Finance, and Manager.
Production always enforces these permissions. For local rollout testing, set
`ALLTECH_ENFORCE_STAFF_ROLES=1`.

Production also requires staff 2FA by default. Set
`ALLTECH_REQUIRE_STAFF_2FA=0` only for a controlled recovery window. Staff
enroll from **Staff → Two-factor security**.

## Customer identity, delivery, and market growth

Customer portal registration sends an email-verification link before an existing
customer's orders, repairs, or invoices can be linked to a new account. Set up a
working SMTP provider and a real `ALLTECH_DEFAULT_FROM_EMAIL` before offering
self-service registration or password recovery. Verification links expire after
24 hours by default; `ALLTECH_PORTAL_EMAIL_VERIFICATION_MAX_AGE` controls the
lifetime in seconds. Staff cannot sign in or reset passwords through the customer
portal.

Staff can manage customer profiles, search purchase and repair history, identify
repeat or dormant buyers, and review outstanding invoice balances under
**Customers → Customer directory**. Enable the appropriate Sales, Finance, or
Manager role before using this workspace with production role enforcement.

Configure active delivery zones in the Django administration area. Checkout then
requires a delivery area for delivered orders, displays its charge and applicable
tax before purchase, and carries the charge through to the resulting invoice.
Store pickup remains free. Apply the delivery migration before restarting an
updated production release:

```bash
python manage.py migrate
python manage.py bootstrap_roles
```

Use **Reports & growth → Market readiness** to review catalogue completeness,
configured social profiles, unanswered leads, tracked links, campaigns, recent
orders, and a practical Uganda-focused content plan. Social profile links do not
automatically grant API publishing access, and recording Mobile Money payments
does not connect a live payment gateway; those integrations require their own
provider accounts, credentials, and production verification.

Consent-safe customer campaigns now support both bounded email delivery and a
manual WhatsApp click-to-chat queue. WhatsApp recipients must have current
WhatsApp and topic consent plus a usable phone number. Staff open each prepared
message, send it through WhatsApp, and separately confirm delivery so the system
keeps an auditable record without claiming an unconfigured WhatsApp Business API
integration. Include a tracked campaign link in the message when measuring
traffic and leads.

Marketing leads record the first response, next promised follow-up, overdue
follow-ups, and the time a lead was won. The Market Readiness screen shows
overdue work and average recorded response time; use these figures to enforce a
fast sales-response routine.

The same screen now audits the full commercial journey across seven phases:
Discovery, Trust, Acquisition, Conversion, Fulfillment, Retention, and Advocacy.
Each phase has measurable operating checks and direct actions. It also exposes
abandoned-cart value, aging orders, shipment exceptions, repeat customers,
reviews, loyalty adoption, and ambassador activity. The phase score reports
configured and observed readiness only; it does not promise sales or viral reach.

Tracked marketing links now use first-party last-click order attribution. A
successful checkout snapshots the verified campaign link, source, medium,
campaign, content, and click time onto its order, then clears the consumed
session attribution. Clicks expire after 30 days by default; configure
`ALLTECH_MARKETING_ATTRIBUTION_WINDOW_DAYS` for a different 1–365 day window.
The marketing dashboard, campaign/link lists, order details, CSV export, and
conversion lifecycle report show attributable orders and revenue. Channel
reporting compares period-matched clicks, leads, and non-cancelled orders;
campaign budget return compares attributed revenue with the configured campaign
budget and must not be mistaken for verified advertising spend or profit.

Purchase orders support both **Receive remaining** and per-line partial shipment
receiving. Each receiving event continues to create a stock receipt and update
inventory inside one transaction.

## Company profile

Configure the production company identity after migrations:

```bash
python manage.py configure_company \
  --company-name "LEOSOFT" \
  --legal-name "LEOSOFT UG LTD" \
  --website "https://leosoftug.com" \
  --country "Uganda" \
  --currency "UGX"
```

## Social marketing and search discovery

Every published product and service page includes:

- WhatsApp, Facebook, X, LinkedIn, Telegram, Pinterest, and email sharing.
- Copy-link and native mobile sharing for installed apps such as Instagram,
  TikTok, messaging apps, and other supported destinations.
- Open Graph and X/Twitter preview metadata using the product name,
  description, price, currency, and main image.
- UTM campaign parameters identifying the sharing source.
- Canonical URLs and Product or Service structured data.
- Automatic inclusion in `/sitemap.xml`.

The public site also exposes `/robots.txt` and social-profile links in the
footer.

After migration, sign in to Django Admin and open:

```text
Marketing → Social media settings
```

Enter the official Facebook, Instagram, TikTok, X, LinkedIn, and YouTube URLs.
For WhatsApp, enter digits with the country code, for example:

```text
256700000000
```

You can also set a short default sharing message that will be included whenever
a visitor shares a product or service.

Run the marketing regression tests with:

```bash
python manage.py test catalog.test_social_marketing
```

## Production commands

Set `ALLTECH_ENV=production`, provide a random `ALLTECH_SECRET_KEY` of at least
50 characters, configure `ALLTECH_ALLOWED_HOSTS`, use PostgreSQL, and terminate
HTTPS through Nginx.

```bash
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py bootstrap_roles
sudo systemctl restart leosoft_gunicorn
```

Uploaded media must be stored on persistent storage or object storage. Do not
serve production media directly through Django.

## Health check

Use `/healthz/` for uptime monitoring and deployment checks. It returns a small
JSON response, confirms database connectivity, and does not expose private
settings.

```bash
curl -fsS https://leosoftug.com/healthz/
```

## Quality checks

```powershell
python manage.py makemigrations --check --dry-run
python manage.py check
python manage.py test
ruff check .
```

## Backups

Create a timestamped database and media backup:

```powershell
python manage.py backup_alltech --output backups
```

For PostgreSQL, `pg_dump` must be installed and available on `PATH`. Schedule
the command through cron or the hosting platform, copy the result to off-site
storage, and test restoration regularly.

## Deployment checklist

- Point Namecheap `@` and `www` A records to the VPS public IPv4 address.
- Use PostgreSQL and persistent media storage.
- Run migrations, `bootstrap_roles`, and `configure_company`.
- Configure official social-profile links in Django Admin.
- Test a product share on WhatsApp and the native mobile share panel.
- Verify `/robots.txt` and `/sitemap.xml`.
- Run `check --deploy`.
- Configure SMTP and verify delivery.
- Check `/healthz/` after deployment.
- Schedule backups and due-reminder commands.
- Keep secrets outside the repository.
- Monitor application and reverse-proxy logs.
