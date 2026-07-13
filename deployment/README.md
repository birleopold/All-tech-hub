# LEOSOFT UG LTD — Ubuntu VPS deployment runbook

This runbook deploys **LEOSOFT UG LTD** at **https://leosoftug.com** alongside Django projects already running on the same Ubuntu VPS.

It assumes the VPS already has Python, PostgreSQL, Nginx, Git and Certbot. This project currently needs **Django, PostgreSQL, Gunicorn and Nginx only**; it does not use Celery or Redis.

The production checkout stays on **`main`**, and future updates use:

```bash
git pull origin main
```

The existing `ALLTECH_` environment-variable prefix is retained for compatibility, while the public company identity is LEOSOFT UG LTD.

## Deployment layout

```text
Ubuntu user:     admin
Application:     /home/admin/All-tech-hub
Virtualenv:      /home/admin/All-tech-hub/.venv
Environment:     /home/admin/All-tech-hub/.env
Gunicorn:        127.0.0.1:8010
Systemd service: leosoft_gunicorn
Nginx site:      leosoftug.com
PostgreSQL DB:   leosoft_prod
PostgreSQL user: leosoft_user
```

Confirm port `8010` is free before deployment:

```bash
sudo ss -ltnp | grep ':8010' || echo 'Port 8010 is available'
```

## 1. Point the domain to the VPS

At the domain DNS provider, create:

```text
A   leosoftug.com       VPS_PUBLIC_IP
A   www.leosoftug.com   VPS_PUBLIC_IP
```

Confirm resolution:

```bash
getent hosts leosoftug.com
getent hosts www.leosoftug.com
```

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

Allow Nginx to traverse the home directory and read collected static and uploaded media files:

```bash
sudo chmod 711 /home/admin
sudo find /home/admin/All-tech-hub -type d -exec chmod 755 {} \;
```

Do not make `.env` world-readable; it will remain mode `600`.

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

```bash
sudo cp /home/admin/All-tech-hub/deployment/nginx-leosoftug.com.conf \
  /etc/nginx/sites-available/leosoftug.com

sudo ln -sfn /etc/nginx/sites-available/leosoftug.com \
  /etc/nginx/sites-enabled/leosoftug.com

sudo nginx -t
sudo systemctl reload nginx
```

Validate HTTP before requesting the certificate. A redirect to HTTPS is expected because production SSL redirection is enabled:

```bash
curl -I http://leosoftug.com/healthz/
```

This Nginx server block uses its own domain, internal port, logs, static directory and media directory, so it does not replace existing projects' configurations.

## 9. Enable HTTPS

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

## 10. Routine deployment from `origin/main`

For future updates:

```bash
cd /home/admin/All-tech-hub
git checkout main
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
set -a
source .env
set +a
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
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
