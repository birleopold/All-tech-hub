# Phase 3 automation operations

## Connector verification

Configuration-only check:

```bash
python manage.py check_marketing_integrations
```

After official Meta credentials are configured and automatic publishing is enabled, perform read-only account verification:

```bash
python manage.py check_marketing_integrations --require-meta --live
```

This prints the verified Page/account name or ID. It never prints the access token.

## Queue health

```bash
python manage.py check_automation_health --json
```

The check fails when:

- queued or retrying work is overdue;
- a running worker lock is stale;
- a permanent failure requires investigation.

## Retry failed work

Before retrying a social delivery, inspect the external platform. A transport failure can leave the publishing outcome uncertain.

After confirming the post was not already published and correcting the underlying problem:

```bash
python manage.py retry_failed_automation_jobs --limit 100
python manage.py run_automation_jobs --process-only
```

## Abandon one failed job without deleting history

Use the exact idempotency key shown in the automation diagnostics:

```bash
python manage.py cancel_automation_job \
  'social:123:facebook' \
  --reason 'Verified as not suitable for automatic retry; publish manually.'
```

A cancelled social job becomes a manual delivery requirement. Its attempts and error history remain in the database.

## Inspect service logs

```bash
sudo journalctl -u leosoft-marketing-posts.service -n 100 --no-pager
sudo journalctl -u leosoft-automation-health.service -n 100 --no-pager
```

## Emergency stop

```bash
sudo systemctl disable --now leosoft-marketing-posts.timer
sudo systemctl disable --now leosoft-automation-health.timer
```

Also set:

```dotenv
ALLTECH_META_AUTO_PUBLISH_ENABLED=0
```

Then restart Gunicorn:

```bash
sudo systemctl restart leosoft_gunicorn
```
