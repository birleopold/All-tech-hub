# LEOSOFT UG LTD

LEOSOFT UG LTD is a Django platform for technology retail orders, inventory,
purchasing, billing, repair jobs, customer support, reporting, and a customer
portal.

It includes an append-only stock movement ledger, customer and supplier
returns, payment reconciliation, refunds with credit notes, invoice aging,
Mobile Money payment recording, and authenticator-app two-factor security.

The project retains the existing `ALLTECH_` environment-variable names for
backward compatibility.

## Local setup

```powershell
py -3.13 -m venv .venv
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

## Production

Set `ALLTECH_ENV=production`, provide a random `ALLTECH_SECRET_KEY` of at least
50 characters, configure `ALLTECH_ALLOWED_HOSTS`, use PostgreSQL, and terminate
HTTPS through Nginx.

```bash
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py bootstrap_roles
gunicorn config.wsgi:application
```

The full Ubuntu VPS instructions for **leosoftug.com** are in
[`deployment/README.md`](deployment/README.md). The production workflow remains
on `origin/main`, so future server updates use `git pull origin main`.

Uploaded media must be stored on persistent storage or object storage. Do not
serve production media directly through Django.

## Health check

Use `/healthz/` for uptime monitoring and deployment checks. It returns a small
JSON response, confirms database connectivity, and does not expose private
settings.

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

- Use PostgreSQL and persistent media storage.
- Run migrations, `bootstrap_roles`, and `configure_company`.
- Run `check --deploy`.
- Configure SMTP and verify delivery.
- Check `/healthz/` after deployment.
- Schedule backups and due-reminder commands.
- Keep secrets outside the repository.
- Monitor application and reverse-proxy logs.
