# LEOSOFT — final acceptance and owner-dependent evidence
Date: 2026-10-18

This checklist distinguishes source implementation from evidence that each
customer/staff journey really works. The code changes on main must first pass
the existing guarded release gate; they must not bypass it.

## Confirmed release baseline

- Git revision `c0737f0` passed 754 Django tests with zero failures/errors
  on the VPS. Temporary SQLite migration and backup/restore checks passed.
- The same release created a production PostgreSQL **backup file** before
  migrations, restarted the existing Gunicorn service, checked the marketing
  timer and returned public readiness HTTP 200 at the matching SHA.
- Neither a successful dump nor a green isolated suite proves recovery of a
  real PostgreSQL database with media attachments.
- Newer commits add catalogue search correction, an auditable job handover and
  homepage ordering/pricing corrections. These are **unverified candidates**
  until the next guarded VPS run.

## Functional completion: remain open until verified

- [ ] **P1 Storefront:** On 320px mobile, tablet and desktop, navigate home →
  catalogue → filters → product detail → purchase or quote; verify keyboard
  focus, search typo recovery and truthful service pricing.
- [ ] **P2 Catalogue and inventory:** Staff verify actual inventory and keep
  obsolete tracked listings unpublished or clearly enquiry-based. As of the
  preceding deployed audit, 207 listings were flagged out of stock.
  Do not fabricate stock, brand, condition, GTIN or MPN.
- [ ] **P3 Checkout and fulfilment:** Execute a guest purchase, account
  purchase, delivery/pickup quote, staff status transition, order tracking,
  cancellation and duplicate-request replay on a controlled test order.
  Live provider payments require independently verified sandbox credentials,
  callbacks and settlement reconciliation.
- [ ] **P4 Customer service and after-sales:** Verify real verified-email
  customer signup, orders, bills, repair history, customer-owned attachments,
  warranty claim and completed-work handover on mobile and desktop.
  SMTP delivery must be independently confirmed.
- [ ] **P5 Staff command centre:** Verify Sales, Inventory, Technician,
  Finance and Manager navigation, search, task ownership and forbidden paths
  using accounts with *only* their assigned roles.
- [ ] **P6 Finance and field operations:** Review purchase partial receiving,
  stock ledger, job expenses, quote approval, refunds, invoice ageing and
  audited field handover. Rehearse restoring the PostgreSQL dump AND media into
  an isolated test system without touching production, then capture proof.
- [ ] **P7 Marketing:** Confirm Telegram and any separately approved Meta
  channels end to end, per-channel delivery status, manual Publish Now,
  failed-job review, real email consent and unsubscribe. Merchant feed
  eligibility requires actual product inspections and external approval.
- [ ] **P8 Release certification:** Confirm green *executed* CI steps (the
  latest GitHub-hosted jobs have no recorded steps), full VPS release gate for
  the final SHA, visual and keyboard tests, recovery exercise, HTTPS/CSP
  review, uptime checks and monitored provider health.

## Real production data blockers (previous deployed audit)

- Published catalogue: 225; catalogue quality: 81% average, zero critical.
- Search optimisation readiness: 80%.
- Merchant profiles: 222; ready: 0; enabled: 0; 42% average readiness.
- 207 published tracked products flagged out of stock; 142 missing feed and
  condition metadata; 165 physical products missing brand metadata; 220
  physical products missing manufacturer identifiers.

These represent missing verified data or external-account approvals. A source
code commit cannot establish the physical stock or invent manufacturer IDs.

## Next guarded release command

```bash
cd /home/admin/All-tech-hub
git pull --ff-only origin main
bash scripts/phase8_verified_deploy.sh
```

A failed test or migration check must stop production deployment. Record the
new SHA, test summary and readiness output only after the command has really
finished; do not mark these acceptance boxes passed on code alone.

## Secrets and server files

The VPS previously had untracked `private_key.pem` and `public_key.pem`.
The new root-level ignore rule helps prevent accidental Git addition but
**does not secure existing files**. Identify their current consumers, then
move private material to a restricted path outside web and repository roots;
do not remove or relocate a key before confirming which service uses it.

## PostgreSQL and media recovery rehearsal (new candidate implementation)

Run **only after** the guarded release candidate passes. The new script never reads
`.env`, does not attach to the running PostgreSQL cluster, cannot connect to
the production socket or host, and refuses root execution. It starts its own
PostgreSQL cluster under a private temporary directory (using installed
`initdb` and `pg_ctl`), restores one checksummed custom-format dump into its
own throwaway database, checks Django migration records and restored public
tables, extracts public/private media under the same private directory, and
stops the throwaway cluster at the end. Any failure means recovery is **not**
certified. Ensure enough disk capacity for a second DB copy and media archive.

The backups created by `backup_project --include-media` have a manifest at
`<backup directory>/manifest.json`. Example:

```bash
cd /home/admin/All-tech-hub
manifest="$(find backups -mindepth 2 -maxdepth 2 -name manifest.json -type f -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
test -n "$manifest" || { echo "No managed backup manifest found"; exit 1; }
.venv/bin/python scripts/phase8_postgres_restore_drill.py "$manifest"
```

The output is one JSON object reporting `status=passed`, migration count,
public-table count, recovered media-file count and source release label. A
successful source-code CI check does not substitute for executing this command.
The original backup and live database are left untouched. Do not paste a
customer's database, file names, credentials or archive into a public issue.

## Evidence for specific requested features

- **Quotation revision history:** `billing.DocumentRevision` stores revision
  number, reason, snapshot, actor and time; a staff document revision workflow
  exists. Real role-specific revision/approval and PDF acceptance remain open.
- **Field-work handover:** `operations.JobCard.customer_signature` captures an
  optional *intake* signature. New `operations.JobHandover.signature`
  provides a separate completed-work recipient acknowledgement via staff
  touch/mouse drawing or safe image upload. Consent, role checks and customer
  ownership protect access, and old handovers remain explicitly unsigned.
  **Not yet certified:** VPS migration/test gate, actual device signing,
  recipient identification checks, or any legal e-signature requirement.
- **Typo-tolerant search:** customer suggestions were code-staged in the
  catalogue, with same-filter result confirmation. Real navigation and the
  current branch's regression gate have not yet been verified on the VPS.
- **Verified-purchase review:** order-bound review URL and customer review form
  exist under the commerce retention workflows. Actual completed-order
  authorisation, moderation and customer-device acceptance remain open.
- **Offline field operations:** the staff job detail and technician bench now
  offer explicit device-only drafts for internal field notes, using a per-user
  browser queue with seven-day expiry. The staff member manually syncs after
  reconnecting; server checks CSRF, permissions, UUID idempotency, a matching
  job revision and non-terminal status. Conflicting drafts are retained for
  human review. Actual device testing and VPS release verification remain
  open. Offline inventory, expenses, payment, time entries, signatures and
  status transitions are deliberately not queued because they require live
  conflict/reconciliation checks.

## Follow-up hardening candidate — final acceptance still open

- Offline technician notes: the browser queue now deletes expired device drafts
  when it is opened; it never sends a note without an explicit sync action.
- Verified-purchase reviews: server service now serialises review creation per
  customer, treats repeat identical content as idempotent, prevents published
  review rewrites from the private URL and rejects overlong text explicitly.
  Public review screen provides a clear published/locked state. This requires
  normal Django and browser test execution on the target candidate release.
- Quotation revisions: paid, cancelled, inventory-posted and receipt documents
  cannot be unlocked by the ordinary revision action. Issued quote revisions
  preserve the prior accepted/approved terms in the snapshot, clear finance
  and customer acceptance and rotate the earlier private customer link.
  Re-approval and new customer acceptance are necessary before a revised
  quotation can be treated as approved. Execute the focused regression module
  and customer link test in the release gate.
- The latest source code cannot attest to external payment settlement, real
  SMTP delivery, provider webhooks, social publication, Merchant Center
  approvals, physical inventory counts or the availability of GitHub-hosted
  runners. Keep these items open with operational owners.
