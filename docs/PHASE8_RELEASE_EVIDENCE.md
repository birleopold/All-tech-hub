# Phase 8 — release certification evidence

**Status: In progress. NOT production-certified.**

The source-code phase board is separate from this evidence register.
Do not mark any row as passed without a real command result, timestamp and
release SHA. A committed workflow is not a successfully executed workflow.

## Offline candidate check

From a trusted clone with Python dependencies and Node.js installed:

```bash
bash scripts/phase8_release_gate.sh
```

This always forces development-mode settings, a temporary SQLite database,
temporary media/backup paths and in-memory email backend. It checks the
effective Django paths before running anything, creates an isolated checksummed
backup, verifies the archive and SQLite database contents, restores that backup
into another temporary SQLite file and checks the restored migration state.
It does **not** read the
VPS `.env`, modify its PostgreSQL database, publish social content,
charge customers or send email. Passing verifies basic syntax, Django checks,
migration drift, fresh-database migrations, isolated backup/restore,
and the Django test suite. The SQLite restore is NOT a PostgreSQL production
backup/restore drill.

Use specific test module paths only for diagnosis, not sign-off:

```bash
bash scripts/phase8_release_gate.sh marketing.test_attribution automation.test_social_operator_experience
```

## Evidence register

| Gate | Current status | Required real-world evidence |
| --- | --- | --- |
| GitHub Actions checkout and runner allocation | BLOCKED | Runner assigned; jobs have steps and executed logs |
| Full Django and Ruff | PENDING | Latest commit SHA, green CI run links, zero failures |
| Migration rehearsal with production-like PostgreSQL copy | PENDING | Staging database backup, migrations and rollback notes |
| Restore drill | PENDING | Isolated restore with checksums plus sampled attachments |
| Customer checkout and staff fulfilment | PENDING | Desktop/mobile purchase, order lifecycle, stock restoration |
| Finance, repair and permissions | PENDING | Two-role workflow, duplicate retry, invoice and expense checks |
| Automation and external APIs | PENDING | Telegram/Meta dry integration, provider confirmations and failure-recovery evidence |
| Merchant data | PENDING | Valid actual products, image/link/price matching and strict feed validation |
| Accessibility/responsive | PENDING | 320px phone, tablet, laptop, desktop and keyboard/touch inspection |
| Production smoke and rollback | PENDING | Release SHA, readiness endpoint, systemd timers, monitoring and rollback rehearsal |

**GitHub Actions blocker seen before this work:** workflows complete as failed
with no job steps. Investigate runner availability, organisation policy,
GitHub Actions account/billing settings or other workflow-start restrictions.
No claim about the underlying cause can be made without a completed job log.

## Controlled production path

1. Freeze the candidate SHA only after CI and staging evidence are green.
2. Rehearse PostgreSQL migrations and restore independently from production.
3. Preserve a verified pre-migration backup and record its location securely.
4. Use the already tracked `bash scripts/update_vps.sh` on the actual VPS,
   rather than inventing new Gunicorn/timer paths.
5. Verify `https://leosoftug.com/health/ready/` reports the deployed SHA,
   check public catalogue/checkout and privileged operations, and check
   `leosoft-marketing-posts.timer` health.
6. Keep sensitive backup details and customer data out of this repository.

The existing `scripts/deploy_production.sh` already checks release settings,
performs backups before migrations, runs SEO/merchant audits, collects hashed
assets and checks Gunicorn readiness; Phase 8 adds evidence, not a second
production deployment implementation.
