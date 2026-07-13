# LEOSOFT UG LTD — Ubuntu VPS deployment runbook

This runbook deploys **LEOSOFT UG LTD** at **https://leosoftug.com** alongside Django projects that are already running on the same Ubuntu VPS.

It assumes Python, PostgreSQL, Nginx, Git and Certbot are already installed. This project currently needs **Django, PostgreSQL, Gunicorn and Nginx only**; it does not use Celery or Redis.

The production checkout remains on **`main`**. Future updates use:

```bash
git pull origin main
```

The code keeps the existing `ALLTECH_` environment-variable prefix for compatibility, while the public company identity is configured as LEOSOFT UG LTD.

## Deployment layout

```text
Linux user:      leosoft
Application:     /home/leosoft/All-tech-hub
Virtualenv:      /home/leosoft/All-tech-hub/.venv
Environment:     /home/leosoft/All-tech-hub/.env
Gunicorn:        127.0.0.1:8010
Systemd service: leosoft_gunicorn
Nginx site:      leosoftug.com
PostgreSQL DB:   leosoft_prod
PostgreSQL user: leosoft_user
```

Before using port `8010`, confirm that another project is not using it:

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

## 2. Create the deployment user

Skip this section when the `leosoft` user already exists.

```bash
sudo adduser leosoft
sudo usermod -aG sudo,www-data leosoft
```

The `sudo` membership allows the deployment script to restart only after you authenticate. For tighter production control, replace this later with a limited sudoers rule for `systemctl restart leosoft_gunicorn`.

## 3. Clone the private repository on `main`

```bash
sudo -i -u leosoft
cd ~
git clone git@github.com:birleopold/All-tech-hub.git
cd All-tech-hub
git checkout main
git pull origin main
```

The VPS must have GitHub access through an SSH key or deploy key.

Allow Nginx to traverse the deployment user's home directory and read collected static and uploaded media files:

```bash
exit
sudo chmod 711 /home/leosoft
sudo find /home/leosoft/All-tech-hub -type d -exec chmod 755 {} \;
```

Do not make `.env` world-readable; it will be secured separately with mode `600`.

## 4. Create the PostgreSQL database and user

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

## 5. Create the virtual environment

```bash
sudo -i -u leosoft
cd /home/leosoft/All-tech-hub
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 6. Create the production `.env`

```bash
cp deployment/leosoft.env.example .env
chmod 600 .env
nano .env
```

Generate the Django secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

At minimum, replace:

```text
ALLTECH_SECRET_KEY
ALLTECH_DB_PASSWORD
ALLTECH_EMAIL_HOST and related SMTP values
```

The production hostname, HTTPS origins, Africa/Kampala timezone, PostgreSQL database and secure cookie settings are already represented in the template.

## 7. Run the first Django setup

```bash
cd /home/leosoft/All-tech-hub
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

## 8. Create the Gunicorn systemd service

```bash
exit
sudo cp /home/leosoft/All-tech-hub/deployment/leosoft-gunicorn.service \
  /etc/systemd/system/leosoft_gunicorn.service

sudo systemctl daemon-reload
sudo systemctl enable --now leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager
```

Validate Gunicorn directly while supplying the production host and proxy scheme expected by Django:

```bash
curl -fsS \
  -H 'Host: leosoftug.com' \
  -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8010/healthz/

sudo journalctl -u leosoft_gunicorn -n 100 --no-pager
```

## 9. Add the Nginx site

```bash
sudo cp /home/leosoft/All-tech-hub/deployment/nginx-leosoftug.com.conf \
  /etc/nginx/sites-available/leosoftug.com

sudo ln -sfn /etc/nginx/sites-available/leosoftug.com \
  /etc/nginx/sites-enabled/leosoftug.com

sudo nginx -t
sudo systemctl reload nginx
```

Validate HTTP before requesting a certificate. A redirect to HTTPS is expected because production SSL redirection is enabled:

```bash
curl -I http://leosoftug.com/healthz/
```

This Nginx server block uses its own domain, internal port, logs, static directory and media directory, so it does not replace the existing projects' configurations.

## 10. Enable HTTPS

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

## 11. Routine deployment from `origin/main`

Every future deployment stays on `main`:

```bash
sudo -i -u leosoft
cd /home/leosoft/All-tech-hub
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
exit
sudo systemctl restart leosoft_gunicorn
sudo systemctl status leosoft_gunicorn --no-pager
curl -fsS https://leosoftug.com/healthz/
```

Alternatively, after the one-time server setup:

```bash
sudo -i -u leosoft
cd /home/leosoft/All-tech-hub
chmod +x deployment/deploy.sh
./deployment/deploy.sh
```

The deployment script performs `git pull --ff-only origin main`, installs requirements, validates production settings, migrates, collects static files, refreshes staff roles, applies the LEOSOFT company profile, restarts Gunicorn and checks `/healthz/`.

## 12. Backups

Configure `/home/leosoft/.pgpass` so `pg_dump` can run without exposing the database password in commands:

```text
127.0.0.1:5432:leosoft_prod:leosoft_user:CHANGE_ME_STRONG_PASSWORD
```

```bash
sudo chown leosoft:leosoft /home/leosoft/.pgpass
sudo chmod 600 /home/leosoft/.pgpass
```

Create a database and media backup:

```bash
sudo -i -u leosoft
cd /home/leosoft/All-tech-hub
source .venv/bin/activate
set -a
source .env
set +a
python manage.py backup_alltech --output backups
```

## 13. Troubleshooting

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
- Missing CSS: run `collectstatic` and verify the Nginx static alias and `/home/leosoft` traversal permission.
- Database authentication failure: verify the role, database, password and `.env` values.
- Redirect loop after HTTPS: ensure Nginx forwards `X-Forwarded-Proto` and Django uses the provided production settings.
