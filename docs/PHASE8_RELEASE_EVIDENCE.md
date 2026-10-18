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

## VPS integrated suite and deploy safety finding (2026-10-18)

The captured complete Django run for commit `7bfcfea` ran 752 cases and
reported **40 failures, 9 errors**. Genuine production-affecting defects
included a missing `Product` import in the staff order detail (HTTP 500)
and a dashboard quick-action crash on absent `orders_in_transit` count;
these are now guarded. Other failures affect checkout, mail delivery,
marketing campaigns, customer enrollment, catalogue discovery, SEO and
legacy layout expectations; not all are necessarily independent defects.

**Critical:** despite the failed isolated suite, the next interactive shell
command executed `bash scripts/update_vps.sh`. The VPS then migrated,
restarted Gunicorn and reported a healthy release `7bfcfea`. Deployment
success is **not** a green test report. Run certification in a script with
`set -Eeuo pipefail` and an explicit failing-result guard; do not paste a
series of shell commands whose next line deploys after a failed test.

A second detached run was started, but the uploaded tail shows migration
rehearsal only and no completion status. No claim of passing tests is made.

## Release gate safety wrapper

Use `bash scripts/phase8_verified_deploy.sh` only when ready for an actual
release attempt. It runs the isolated tests first, saves the entire output
to `~/leosoft-release-logs/`, and **will not** invoke the existing
`scripts/update_vps.sh` after test failures. The guard uses
`set -Eeuo pipefail` so that `tee` cannot mask a failing test command.
It also refuses to deploy from a checkout containing tracked local edits.
Do not use the raw `update_vps.sh` while Phase 8 is blocked.

## 752-test VPS run on 217db7b and Phase 8 remediation

The user-supplied 2026-10-18 VPS output for source commit `217db7b`
completed **752 Django tests with 39 failures and 7 errors**. The temporary
SQLite migration rehearsal and backup/restore integrity checks succeeded.
The historic interactive multi-command paste **continued to deploy**
`217db7b` despite the failed suite. Its public readiness check returned
HTTP 200; this does not certify customer or staff workflows.

Remediation commits after that VPS run corrected:

- queued campaign delivery that had never performed a first send;
- quotation-only services incorrectly included in 'available now';
- blank extra commercial-document line rows treated as filled forms;
- valid category hubs incorrectly filtered away by optional search synonyms;
- retired UX/SEO assertions rewritten to match actual current screens,
  strict unverified-schema omissions and revised sitemap structure;
- checkout tests updated for explicit pickup when delivery tariffs are absent;
- email tests updated for the durable notification worker rather than
  synchronous database-signal delivery;
- test fixtures now include real Merchant feed images and verified identity
  when the claimed metadata has actually been checked.

The corrected suite has **not yet been executed in full on the VPS**.
GitHub Actions for the latest commits report job failures without any job
steps or available logs (runner provisioning issue); they provide no positive
test evidence. Preserve the fail-closed release gate until all checks pass.

## Duplicate lead-reminder execution corrected

The same growth-automation command processed due lead follow-ups in both
`queue_due_growth_jobs()` and `run_growth_automation.handle()`.
The first path sent and throttled the notification; the second counted
zero, so the operator summary was inaccurate. The command now reuses the
first path's counts and issues no second reminder pass. The existing
integration test asserts both the notification and the reported count.

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

## 754-test VPS run on e5ebe9579dce (2026-10-18)

The latest uploaded guarded release log completed **754 Django tests with 6 failures
and no errors**. The isolated migration and SQLite backup/restore checks passed.
The six remaining failing assertions were: document-register icon-only PDF action,
search suggestion decimal representation, filtered catalogue robots directives,
a scheduler test mocking a retired email retry entry point, immediate cached
checkout marketing consent, and the production helper's configurable virtualenv
path. The scheduled delivery mock has been updated to exercise the first-send
API and verify that failure-count/circuit-breaker behavior still runs. Checkout
consent updates now reuse the locked OneToOne instance instead of retaining a
stale cached default. No assertion or permission controls were removed to
bypass the release gate.

These changes still require a full, successful isolated VPS verification on the
new commit. A successful deploy or HTTP 200 readiness result alone is not
sufficient evidence of Phase 8 certification.

## Verified production release c0737f0 (2026-10-18)

The uploaded VPS output reports `Ran 754 tests ... OK`, successful isolated
migrations and SQLite backup/restore, a pre-migration PostgreSQL dump, no pending
production migrations, running Gunicorn, enabled marketing timer, and healthy
local/public readiness at release `c0737f0`. This supersedes older candidate
notes **for that SHA only**; external providers, PostgreSQL restoration,
mobile/keyboard browser workflows, rollback rehearsal and CI runners remain
uncertified.

## New catalogue and handover features (candidate)

Add spelling recovery for otherwise empty filtered catalogue searches, and an
audited one-time repair handover with staff permission checks, confirmation,
automated ready-to-complete transition and customer portal status. These changes
require the next isolated VPS gate, migration rehearsal and browser acceptance
before they can be marked deployed or verified.
