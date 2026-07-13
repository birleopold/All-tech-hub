# LEOSOFT UG LTD deployment

This guide deploys the Django application at **leosoftug.com** on an Ubuntu VPS that already has PostgreSQL, Nginx, Python and other Django projects. It does not reinstall or replace the existing server stack.

The application keeps the existing `ALLTECH_` environment-variable prefix for compatibility, but the public company identity is configured as **LEOSOFT UG LTD**.

## Intended layout

Replace the example values with the existing VPS user and preferred application path.

```text
Application: /home/<deploy-user>/All-tech-hub
Virtualenv:  /home/<deploy-user>/All-tech-hub/.venv
Environment: /home/<deploy-user>/All-tech-hub/.env
Gunicorn:    /run/leosoft/gunicorn.sock
Systemd:     leosoft-gunicorn.service
Nginx site:  leosoftug.com
Database:    leosoft_prod
DB role:     leosoft_user
```

## 1. Point the domain to the existing VPS

Create DNS `A` records for:

```text
leosoftug.com      -> VPS public IPv4 address
www.leosoftug.com  -> VPS public IPv4 address
```

Use an `AAAA` record only when the VPS is correctly configured for IPv6.

## 2. Prepare the application checkout

Use the existing deployment user. Clone the private repository through an SSH deploy key or update the existing checkout.

```bash
cd /home/<deploy-user>
git clone git@github.com:birleopold/All-tech-hub.git
cd All-tech-hub
cp deployment/leosoft.env.example .env
chmod 600 .env
chmod +x deployment/deploy.sh
```

Generate a Django secret key and place it in `.env`:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Replace the database password and SMTP placeholders before deployment. The `.env` file must never be committed.

## 3. Create only the new PostgreSQL database and role

PostgreSQL is already installed, so only add a dedicated database and least-privilege role:

```bash
sudo -u postgres psql
```

```sql
CREATE USER leosoft_user WITH PASSWORD 'REPLACE_WITH_A_STRONG_PASSWORD';
CREATE DATABASE leosoft_prod OWNER leosoft_user;
ALTER ROLE leosoft_user SET client_encoding TO 'utf8';
ALTER ROLE leosoft_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE leosoft_user SET timezone TO 'Africa/Kampala';
\q
```

Use the same password in `.env` as `ALLTECH_DB_PASSWORD`.

## 4. Install the Gunicorn service

Render the template with the real deployment user and absolute application path:

```bash
cd /home/<deploy-user>/All-tech-hub
APP_DIR="$(pwd)"
DEPLOY_USER="$(id -un)"
sed \
  -e "s|__APP_DIR__|${APP_DIR}|g" \
  -e "s|__DEPLOY_USER__|${DEPLOY_USER}|g" \
  deployment/leosoft-gunicorn.service \
  | sudo tee /etc/systemd/system/leosoft-gunicorn.service >/dev/null

sudo systemctl daemon-reload
sudo systemctl enable leosoft-gunicorn.service
```

Do not start the service until the virtual environment and migrations have been prepared by the deployment script.

## 5. Add the Nginx site without disturbing existing projects

```bash
cd /home/<deploy-user>/All-tech-hub
APP_DIR="$(pwd)"
sed "s|__APP_DIR__|${APP_DIR}|g" deployment/nginx-leosoftug.com.conf \
  | sudo tee /etc/nginx/sites-available/leosoftug.com >/dev/null

sudo ln -sfn /etc/nginx/sites-available/leosoftug.com /etc/nginx/sites-enabled/leosoftug.com
sudo nginx -t
sudo systemctl reload nginx
```

The configuration uses its own domain, logs, static/media aliases and Gunicorn socket, so it can coexist with the Django projects already on the VPS.

## 6. Run the first deployment

The first run creates the virtual environment when it does not exist, installs dependencies, validates production settings, applies migrations, collects static files, creates staff roles, configures the LEOSOFT company profile and starts Gunicorn.

```bash
cd /home/<deploy-user>/All-tech-hub
SKIP_GIT_PULL=1 HEALTHCHECK_URL=http://leosoftug.com/healthz/ ./deployment/deploy.sh
```

Check the service and logs:

```bash
sudo systemctl status leosoft-gunicorn --no-pager
sudo journalctl -u leosoft-gunicorn -n 100 --no-pager
curl -I http://leosoftug.com/healthz/
```

## 7. Enable HTTPS

After DNS resolves to the VPS and the HTTP Nginx site works:

```bash
sudo certbot --nginx \
  -d leosoftug.com \
  -d www.leosoftug.com \
  --redirect

sudo nginx -t
sudo systemctl reload nginx
curl -fsS https://leosoftug.com/healthz/
```

Confirm automatic certificate renewal without changing other hosted sites:

```bash
sudo certbot renew --dry-run
```

## 8. Create the first administrator

```bash
cd /home/<deploy-user>/All-tech-hub
set -a
source .env
set +a
.venv/bin/python manage.py createsuperuser
```

Sign in at `https://leosoftug.com/admin/` and complete the company email, telephone, address, logo, tax information and document settings. Staff two-factor authentication is required in production by default.

## Routine deployments

After changes have been merged into `main`:

```bash
cd /home/<deploy-user>/All-tech-hub
./deployment/deploy.sh
```

To create a pre-deployment backup, configure PostgreSQL passwordless access for `pg_dump` through a deployment-user `.pgpass` file, then run:

```bash
RUN_BACKUP=1 ./deployment/deploy.sh
```

## Useful checks

```bash
sudo nginx -t
sudo systemctl is-active leosoft-gunicorn
sudo journalctl -u leosoft-gunicorn -f
curl -fsS https://leosoftug.com/healthz/
.venv/bin/python manage.py check --deploy
```

## Rollback

Identify the last known-good commit, check it out on the deployment branch, reinstall requirements when they changed, run migrations only when appropriate, collect static files and restart the service:

```bash
git log --oneline -10
git checkout <known-good-commit>
SKIP_GIT_PULL=1 ./deployment/deploy.sh
```

Database migrations may not always be safely reversible. Take a verified PostgreSQL and media backup before releases that alter production data or schema.
