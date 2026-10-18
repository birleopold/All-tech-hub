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
