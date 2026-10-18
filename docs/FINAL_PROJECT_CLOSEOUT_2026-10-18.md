# LEOSOFT / All-tech-hub — development closeout and handover
Date: 2026-10-18
Repository: `birleopold/All-tech-hub`
Target: `https://leosoftug.com`

## Decision

**Feature-development handoff: CLOSED as a release candidate.**

The eight-phase source implementation has been handed over, including the
storefront, catalogue operations, checkout, customer portal, CRM, purchasing
and finance, marketing, repair handover, signed delivery records, offline
technician note drafts, order-specific verified reviews, quotation comparisons
and the guarded release process.

**Production certification: NOT CLOSED.** This distinction is deliberate.
No file can truthfully attest to stock counted in person, a payment received
from a live provider, a phone actually used, or a restored production backup
without the corresponding real results.

Last verified successful full-suite VPS baseline: `c0737f0` (754 Django tests).
All changes **after** that SHA require a fresh successful full gate and
staging/production acceptance before their completion is certified. GitHub
hosted workflows have recently failed before acquiring runners; an unstarted
workflow is not a failed unit test and is not passing evidence.

## Final guarded release

Run as the existing `admin` user on the VPS; do not call
`scripts/update_vps.sh` directly or bypass the test gate.

```bash
cd /home/admin/All-tech-hub
git checkout main
git pull --ff-only origin main
bash scripts/final_release_closeout.sh
```

The closeout command preserves the **entire gate and deployment output** in
`~/leosoft-release-logs/closeout-*.log` and refuses deployment after failures.
Once all automated checks pass and the real release is live, it verifies the
site readiness revision, database and migration status, Gunicorn and the
existing social-marketing timer. It then writes a status-only JSON report in
the same private log directory.

**If the command exits nonzero, the automated release is NOT signed off.**
Retain the full log, correct the failure and repeat the guarded procedure.
Do not paste real credentials, private customer attachments or backups into
issues or chat. An interrupted terminal does not imply success.

## Independent evidence still required

| Area | Required real-world acceptance | Status |
| --- | --- | --- |
| Catalogue | Staff inspect real stock, brand, condition, exact product IDs, warranty, prices, shipping and genuine photos; resolve Merchant feed approvals | PENDING BUSINESS DATA |
| Checkout/payment | Provider sandbox callbacks, duplicate and refund tests, live authenticated transactions and reconciled settlement | PENDING PROVIDER |
| Customer messaging | Verify real SMTP email delivery, unsubscribe and consent; approved social channels and failure handling | PENDING PROVIDER |
| Customer/staff UX | Real Android, iOS, tablet, desktop and keyboard journeys for orders, quotes, repair/service jobs and permissions | PENDING DEVICE |
| Database recovery | Actual checksum-verified PostgreSQL and public/private-media restore into an isolated database; record results | PENDING OPS |
| CI | GitHub Actions obtains a runner and actually executes checks; review billing and runner policy | PENDING REPO ADMIN |

Use `docs/FINAL_ACCEPTANCE_CHECKLIST_2026-10-18.md`,
`docs/PHASE8_BROWSER_ACCEPTANCE.md` and
`docs/PHASE8_RELEASE_EVIDENCE.md` for exact acceptance procedures.

## Release and security baseline

- Private recipient signatures are permission-controlled; generic staff
  membership alone does not grant access to handover signature images.
- Do not publish staff-only Merchant Center readiness defects on customer
  product pages or fabricate stock or manufacturer identifiers.
- Payment references submitted by customers are not provider-verified payments.
- Offline technician draft notes require manual replay; no offline payment,
  inventory or job-status action is allowed.
- Protect `.env`, existing private key files, uploaded customer media and
  local backup/log directories outside public web routes. Do not rewrite or
  delete original keys until their users are identified.
- Refrain from more discretionary scope expansion on this repository until
  final release evidence is green. Resume only for a verified defect or a
  separately authorised new feature.

## What to bring when revisiting

The deployed SHA, the closeout log filename, the JSON release result, the
isolated PostgreSQL restore summary, results from browser checks, and concrete
payment/merchant-provider confirmations. Without them, the release should
remain labelled **candidate / not fully certified**.

## Transition

All-tech-hub is ready to be **put aside as a development project**.
This does not imply that production certification or operational business
setup was performed remotely. New development can now proceed on another
repository without obscuring these explicit operational obligations.
