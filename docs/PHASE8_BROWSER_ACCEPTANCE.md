# Phase 8: public-browser acceptance run

The Django suite does not prove that actual browsers can navigate the storefront.
The read-only Playwright smoke script checks the home, catalogue, first product,
mobile catalogue filters, keyboard focus, accidental staff Merchant-readiness
disclosure, HTTP health, and horizontal overflow on simulated 320, 390, 768
and 1440-pixel viewports. It can run Chromium, Firefox or WebKit separately.

It does not submit an order, publish products, touch the database, or log in.
It does not write screenshots/cookies/customer details into repository files.
A viewport simulation is **not** a real-device accessibility certificate.

## Isolated QA-computer installation

Use a test laptop or a separate staging environment, not the running
production Python environment. On a host with Python 3.12:

```bash
python3 -m venv .browser-test-venv
.browser-test-venv/bin/python -m pip install playwright
.browser-test-venv/bin/python -m playwright install chromium firefox webkit
.browser-test-venv/bin/python scripts/phase8_browser_smoke.py --browser chromium
.browser-test-venv/bin/python scripts/phase8_browser_smoke.py --browser firefox
.browser-test-venv/bin/python scripts/phase8_browser_smoke.py --browser webkit
```

`--base-url https://staging.example.com` selects a test deployment.
`--report /some/private/path/report.json` writes a small status-only JSON.
A failing public route, missing product card, overflowing page, broken mobile
filter, missing keyboard focus or visible Merchant diagnostics exits nonzero.

## Manual acceptance still required

- At 320px and physical Android/iPhone devices: open and close filters,
  search, select and change variants, view warranty/condition, and try the
  quote and call/WhatsApp pathways without submitting live orders.
- At tablet and desktop widths: inspect navigation, product filters, sticky
  actions, checkout form validation, focus outline and tab order.
- In a test environment, verify a complete checkout/order fulfilment journey,
  actual SMTP delivery, payment-provider sandbox callbacks and reconciliation.
  Never submit pretend payments to the live gateway.
- Log in as each least-privilege staff role and as separate customer accounts:
  confirm no access to other customers' orders, signatures, invoices or reviews.
- Simulate connection loss after opening a technician job, save and preview an
  offline internal note, reconnect, manually sync, and test stale-job conflict.
- Test signed collection on actual touch devices and customer-only signature
  access, then rehearse PostgreSQL and media restoration.

The existing guarded release gate must still pass for the final deployed SHA.
GitHub Actions jobs that never acquire a runner do not count as passing tests.
