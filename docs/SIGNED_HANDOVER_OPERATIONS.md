# Signed repair and field-work handover

## How to record a completed handover

1. Open **Staff → Service operations → Job details** and complete diagnosis,
   repairs and quality assurance until the job is **Ready for pickup**.
2. In **Collection or delivery handover**, identify the person who receives
   the device or completed work. Choose collection or delivery and add the
   collection-slip reference if available.
3. With the recipient present, ask them to sign on the staff device using a
   finger, mouse or stylus. The accessible fallback is a PNG/JPEG signature
   image upload of no more than 512 KB. Do not draw a signature on their behalf.
4. Confirm **recipient consent** and **handover completion**, then press
   **Save signed handover**. Saving the handover closes a Ready job; the
   operation is atomic and protects against duplicate submissions.
5. The protected signature link appears on the staff job detail and the
   customer's own portal repair detail. A customer cannot open another
   customer's signature even by guessing the URL.

## Security and legacy treatment

- Server checks staff write permission, job state and recipient consent.
- The server accepts bounded PNG/JPEG images, verifies dimensions, removes
  metadata and rewrites image bytes to PNG. Drawn images are decoded and
  validated by the same backend; hidden field input is never blindly trusted.
- Saved files use `job_signatures/handover/`, covered by the production Nginx
  `/media/job_signatures/` **deny** rule. Only Django's permission-checked
  `/protected-media/` response can return a signed image. Do not change this
  deny rule without redesigning the private file endpoint.
- The signature is one-to-one with the handover and cannot be overwritten by
  re-submitting the form. Legacy handovers without signatures remain as they
  were; no signatures are fabricated.
- This feature records consented handover acknowledgement. A signature
  alone does not establish the recipient's identity or prove payment.
  Continue using documented collection ID / order and payment checks.
- Private and public media backups must include this directory. Confirm
  the new file appears in the next independent media restore rehearsal.

## Validation before production certification

The normal `scripts/phase8_verified_deploy.sh` gate checks Django migrations,
full tests and the browser-script syntax before allowing deployment. Focused
coverage also includes `operations.test_handover_workflow` and
`operations.test_handover_signature`.

**Not certified until tested:** actual fingertip/stylus capture on iPhone,
Android, tablets and desktop; correct field staff permission assignments;
protected-file delivery through production Nginx; PostgreSQL and media backup
restore; recipient identification policy and legal record retention.

**Do not upload real customer signatures into tests or CI.**
