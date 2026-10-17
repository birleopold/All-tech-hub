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

## Deployment migration drift resolved

The guarded VPS release rehearsal for source revision `29fea04` stopped
before production deployment at `makemigrations --check --dry-run`.
Django proposed `operations/migrations/0009_alter_jobexpense_reference.py`.
The missing migration state was only the `help_text` metadata on the
existing `JobExpense.reference` field. Migration `0009` now records
that field metadata without changing the reference column or existing
expense records. Re-run the isolated release gate and require its success
before applying any production database migrations. This entry documents
the code fix; no successful VPS rerun is claimed.

## Interrupted VPS certification run (2026-10-18)

The user's captured VPS output for release `83d7b5f` confirms:

- Django `check`, migration drift detection and clean SQLite migrations passed.
- Checksummed backup verification and disposable SQLite restore passed.
- The full suite found **750 tests** but produced multiple `E` and `F`
  markers. The captured log ends before the test-result summary and therefore
  does not establish the number or identity of all failures.
- An invalid customer return triggered a genuine HTTP 500 in
  `CustomerReturn.clean()` when `order_line` was absent, now guarded.
- Very small watermarked images raised a Pillow inverted-coordinate error,
  now handled without discarding their image output.
- Some HTTP 403/404/400 responses are intentional security tests, not failures
  unless their associated test assertion is marked `F` or `E`.

The release gate MUST remain blocking until the captured full-suite failures
are understood and corrected. Use a detached shell with persistent stdout and
stderr logs; never use interactive `set -e` to launch a prolonged certification
session over an unreliable SSH connection. No production deployment was
confirmed by this interrupted run.

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

**GitHub Actions blocker — confirmed on 2026-10-17:** workflows finish as failed
before a runner is assigned, with runner_id=0 and no steps:
- [Django CI run 39068599170](https://github.com/birleopold/All-tech-hub/actions/runs/39068599170) — both jobs unstarted.
- [CI run 39068599212](https://github.com/birleopold/All-tech-hub/actions/runs/39068599212) — test job unstarted.

This is **not** a failing Django assertion or proof the application is green.
Investigate GitHub Actions runner availability, repository/organisation policies,
and account billing/usage in GitHub. Never weaken CI checks to clear an
allocation blocker. Its underlying cause cannot be diagnosed from job logs
because no steps were executed.

The Phase 8 offline script now checks its effective Django settings so all
test databases, public/private media and backups are isolated. It also verifies
an isolated SQLite backup and restores it into a separate disposable file.
That is **not** a production-like PostgreSQL recovery or external-provider test.

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
