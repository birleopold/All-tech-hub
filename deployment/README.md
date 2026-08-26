# LEOSOFT UG LTD — Ubuntu VPS deployment runbook

This runbook deploys **LEOSOFT UG LTD** at **https://leosoftug.com** alongside Django projects already running on the same Ubuntu VPS.

The VPS account is **`admin`**. The server already has Python, PostgreSQL, Nginx, Git and Certbot, so this guide does not reinstall the existing stack. This project currently needs Django, PostgreSQL, Gunicorn and Nginx only; it does not use Celery or Redis.

The production checkout stays on **`main`**. Future updates use:

```bash
git pull origin main
```

The existing `ALLTECH_` environment-variable prefix is retained for compatibility, while the public company identity is LEOSOFT UG LTD.

## Deployment layout

```text
Ubuntu user:      admin
Application:      /home/admin/All-tech-hub
Virtualenv:       /home/admin/All-tech-hub/.venv
Environment:      /home/admin/All-tech-hub/.env
Gunicorn:         127.0.0.1:8010
Systemd service:  leosoft_gunicorn
Nginx site:       leosoftug.com
PostgreSQL DB:    leosoft_prod
PostgreSQL user:  leosoft_user
Git branch:       origin/main
Domain registrar: Namecheap
```

Confirm port `8010` is free before deployment:

```bash
sudo ss -ltnp | grep ':8010' || echo 'Port 8010 is available'
```

## 1. Point `leosoftug.com` from Namecheap to the VPS

The domain must use Namecheap **BasicDNS**, **PremiumDNS**, or **FreeDNS** for Host Records to be editable from Namecheap's Advanced DNS page.

### 1.1 Confirm the Namecheap nameservers

1. Sign in to Namecheap.
2. Open **Domain List**.
3. Click **Manage** beside `leosoftug.com`.
4. Under **Nameservers**, select **Namecheap BasicDNS** unless you intentionally use PremiumDNS or FreeDNS.
5. Save the setting when it changes.

Do not change the nameservers when the domain deliberately uses another DNS provider. In that case, create the records at that provider instead.

### 1.2 Add the Namecheap Host Records

1. From **Domain List**, click **Manage** beside `leosoftug.com`.
2. Open the **Advanced DNS** tab.
3. Find **Host Records**.
4. Click **Add New Record** and add:

```text
Type       Host    Value             TTL
A Record   @       VPS_PUBLIC_IP     Automatic
A Record   www     VPS_PUBLIC_IP     Automatic
```

Replace `VPS_PUBLIC_IP` with the public IPv4 address of the Ubuntu VPS.

5. Save each record using Namecheap's green checkmark.
6. Remove conflicting records for `@` or `www`, including old A records, CNAME records, URL Redirect records, Masked Redirects, and Permanent Redirects.

Namecheap states that newly created records normally take about 30 minutes to take effect, although cached DNS information can sometimes take longer.

### 1.3 Verify DNS

Run from the VPS:

```bash
getent hosts leosoftug.com
getent hosts www.leosoftug.com
```

You can also use:

```bash
dig +short leosoftug.com A
dig +short www.leosoftug.com A
```

Both names must return the VPS public IPv4 address before running Certbot.

## 2. Clone the private repository on `main`

Log in to the VPS as `admin`, then run:

```bash
cd /home/admin
git clone git@github.com:birleopold/All-tech-hub.git
cd /home/admin/All-tech-hub
git checkout main
git pull origin main
```

The `admin` account must have GitHub access through its SSH key or a repository deploy key.

When the repository already exists, use:

```bash
cd /home/admin/All-tech-hub
git checkout main
git pull origin main
```

Allow Nginx to traverse the home directory and read collected static and uploaded media files:

```bash
sudo chmod 711 /home/admin
sudo find /home/admin/All-tech-hub -type d -exec chmod 755 {} \;
```

Do not make `.env` world-readable; it must remain mode `600`.

## 3. Create the PostgreSQL database and user

PostgreSQL is already installed, so create only a dedicated database and role:

```bash
sudo -u postgres psql
```

Run inside PostgreSQL:

```sql
CREATE USER leosoft_user WITH PASSWORD 'CHANGE_ME_STRONG_PASSWORD';
CREATE DATABASE leosoft_prod OWNER leosoft_user;
ALTER ROLE leosoft_user SET client_encoding TO 'utf8';
ALTER ROLE leosoft_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE leosoft_user SET timezone TO 'Africa/Kampala';
GRANT ALL PRIVILEGES ON DATABASE leosoft_prod TO leosoft_user;
\q
```

Test the new role:

```bash
psql -h 127.0.0.1 -U leosoft_user -d leosoft_prod
```

Enter the password and run `\q` after a successful connection.

## 4. Create the virtual environment

```bash
cd /home/admin/All-tech-hub
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 5. Create the production `.env`

```bash
cd /home/admin/All-tech-hub
cp deployment/leosoft.env.example .env
chmod 600 .env
nano .env
```

Generate a Django secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Replace at least:

```text
ALLTECH_SECRET_KEY
ALLTECH_DB_PASSWORD
```

Confirm these production values remain present:

```text
ALLTECH_ENV=production
ALLTECH_ALLOWED_HOSTS=leosoftug.com,www.leosoftug.com
ALLTECH_CSRF_TRUSTED_ORIGINS=https://leosoftug.com,https://www.leosoftug.com
ALLTECH_TIME_ZONE=Africa/Kampala
ALLTECH_DB_NAME=leosoft_prod
ALLTECH_DB_USER=leosoft_user
ALLTECH_DB_HOST=127.0.0.1
ALLTECH_DB_PORT=5432
```

SMTP is disabled by default. Add the real email host and credentials later when email delivery is required.

## 6. Run the first Django setup

```bash
cd /home/admin/All-tech-hub
source .venv/bin/activate
set -a
source .env
set +a

python manage.py check
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py bootstrap_roles
python manage.py configure_company \
  --company-name "LEOSOFT" \
  --legal-name "LEOSOFT UG LTD" \
  --website "https://leosoftug.com" \
  --country "Uganda" \
  --currency "UGX"
python manage.py createsuperuser
```

## 7. Create the Gunicorn systemd service

The tracked service file already uses:

```text
User=admin
WorkingDirectory=/home/admin/All-tech-hub
EnvironmentFile=/home/admin/All-tech-hub/.env
ExecStart=/home/admin/All-tech-hub/.venv/bin/gunicorn
Bind address=127.0.0.1:8010
```

Install and start it:

```bash
sudo cp /home/admin/All-tech-hub/deployment/leosoft-gunicorn.service \
  /etc/systemd/system/leosoft_gunicorn.service

sudo systemctl daemon-reload
sudo systemctl enable --now leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager
```

Validate Gunicorn directly while supplying the production host and HTTPS proxy scheme expected by Django:

```bash
curl -fsS \
  -H 'Host: leosoftug.com' \
  -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8010/healthz/

sudo journalctl -u leosoft_gunicorn -n 100 --no-pager
```

## 8. Add the Nginx site

The tracked Nginx file already serves static and media files from `/home/admin/All-tech-hub` and proxies Django to `127.0.0.1:8010`.

Install it:

```bash
sudo cp /home/admin/All-tech-hub/deployment/nginx-leosoftug.com.conf \
  /etc/nginx/sites-available/leosoftug.com

sudo ln -sfn /etc/nginx/sites-available/leosoftug.com \
  /etc/nginx/sites-enabled/leosoftug.com

sudo nginx -t
sudo systemctl reload nginx
```

Validate HTTP before requesting the certificate. Django may redirect HTTP to HTTPS because production SSL redirection is enabled:

```bash
curl -I http://leosoftug.com/healthz/
```

This Nginx server block uses its own domain, internal port, logs, static directory and media directory, so it does not replace existing projects' configurations.

## 9. Enable HTTPS after Namecheap DNS resolves

Do not run Certbot until both Namecheap records resolve to the VPS.

```bash
sudo certbot --nginx \
  -d leosoftug.com \
  -d www.leosoftug.com \
  --redirect

sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
curl -fsS https://leosoftug.com/healthz/
```

If Certbot fails validation, recheck the Namecheap `@` and `www` records, remove conflicting redirects, and confirm ports 80 and 443 reach the VPS.

## 10. Routine deployment from `origin/main`

For future updates:

```bash
cd /home/admin/All-tech-hub
git checkout main
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
scripts/manage_production.sh check --deploy
scripts/manage_production.sh migrate
scripts/manage_production.sh collectstatic --noinput
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager
curl -fsS https://leosoftug.com/healthz/
```

Alternatively, after the one-time setup:

```bash
cd /home/admin/All-tech-hub
chmod +x deployment/deploy.sh
./deployment/deploy.sh
```

The script pulls `origin/main`, installs requirements, checks production settings, migrates, collects static files, refreshes roles, applies the LEOSOFT company profile, restarts Gunicorn and checks `/healthz/`.

## 11. Backups

Create `/home/admin/.pgpass`:

```text
127.0.0.1:5432:leosoft_prod:leosoft_user:CHANGE_ME_STRONG_PASSWORD
```

Secure it:

```bash
sudo chown admin:admin /home/admin/.pgpass
chmod 600 /home/admin/.pgpass
```

Create a database and media backup:

```bash
cd /home/admin/All-tech-hub
source .venv/bin/activate
set -a
source .env
set +a
python manage.py backup_alltech --output backups
```

The guarded wrapper prints the selected PostgreSQL database before executing a
management command. Add `ALLTECH_EXPECTED_DB_NAME=leosoft_prod` to `.env` so
an accidental database-name change is rejected. Do not use a bare
`python manage.py migrate` for production administration.

The readiness endpoint checks both database connectivity and migration state.
A response with `"migrations": "pending"` is deliberately HTTP 503 and lists
the unapplied migration names.

## 12. Troubleshooting

```bash
sudo nginx -t
sudo systemctl status leosoft_gunicorn --no-pager
sudo journalctl -u leosoft_gunicorn -n 200 --no-pager
sudo journalctl -u nginx -n 200 --no-pager
sudo ss -ltnp | grep ':8010'
curl -v -H 'Host: leosoftug.com' -H 'X-Forwarded-Proto: https' http://127.0.0.1:8010/healthz/
curl -v https://leosoftug.com/healthz/
```

Common checks:

- `DisallowedHost`: verify `ALLTECH_ALLOWED_HOSTS` in `.env`.
- CSRF failure: verify both HTTPS entries in `ALLTECH_CSRF_TRUSTED_ORIGINS`.
- 502 Bad Gateway: check `leosoft_gunicorn` and port `8010`.
- Missing CSS: run `collectstatic` and verify the Nginx static alias and `/home/admin` traversal permission.
- Database authentication failure: verify the role, database, password and `.env` values.
- Redirect loop after HTTPS: ensure Nginx forwards `X-Forwarded-Proto` and Django uses the production settings.
- Domain not resolving: check Namecheap **Advanced DNS**, verify `@` and `www` A records, and remove conflicting redirect or CNAME records.
