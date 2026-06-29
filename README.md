# ALLTECH Hub

ALLTECH Hub is a Django platform for retail orders, inventory, purchasing,
billing, repair jobs, customer support, reporting, and a customer portal.

It includes an append-only stock movement ledger, customer and supplier
returns, payment reconciliation, refunds with credit notes, invoice aging,
Mobile Money payment recording, and authenticator-app two-factor security.

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

## Production

Set `ALLTECH_ENV=production`, provide a random `ALLTECH_SECRET_KEY` of at least
50 characters, configure `ALLTECH_ALLOWED_HOSTS`, use PostgreSQL, and terminate
HTTPS either in Django or a trusted reverse proxy.

```powershell
python manage.py check --deploy
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py bootstrap_roles
gunicorn config.wsgi:application
```

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
the command through Task Scheduler, cron, or your hosting platform and copy the
result to off-site storage. Test restoration regularly.

## Deployment checklist

- Use PostgreSQL and persistent media storage.
- Run migrations and `bootstrap_roles`.
- Run `check --deploy`.
- Configure SMTP and verify delivery.
- Check `/healthz/` after deployment.
- Schedule backups and due-reminder commands.
- Keep secrets outside the repository.
- Monitor application and reverse-proxy logs.
