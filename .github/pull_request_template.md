## Purpose

Describe the business or security problem this change solves.

## Scope

- [ ] Customer-facing behaviour
- [ ] Staff workflow
- [ ] Database or migration
- [ ] Inventory, payments or financial documents
- [ ] Authentication, permissions or private files
- [ ] Deployment, Nginx, systemd or environment settings

## Validation

- [ ] `python manage.py makemigrations --check --dry-run`
- [ ] `python manage.py check`
- [ ] Relevant tests passed
- [ ] Production `collectstatic` passed when static files changed
- [ ] Permission and ownership checks were tested
- [ ] Failure and retry behaviour was considered

Commands and results:

```text
Paste concise results here.
```

## Deployment and rollback

State the deployment order, required environment values, migrations, service
restarts, smoke tests and rollback steps.

## Data and security review

- [ ] No credentials or customer data were committed
- [ ] Sensitive uploads are not exposed through public media URLs
- [ ] Destructive or financial actions are audited
- [ ] Backward compatibility and existing records were considered
