#!/usr/bin/env python3
"""Non-mutating real-browser smoke tests for the public LEOSOFT storefront.

Optional developer dependency: python -m pip install playwright
Then: python -m playwright install chromium
No checkout/payment or staff changes are submitted.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse


VIEWPORTS = (320, 390, 768, 1440)
PUBLIC_PAGES = (("/", "Home"), ("/catalog/", "Catalogue"))


def check_site(base: str, *, engine: str = "chromium", timeout_ms: int = 30000) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Install browser-only test tools with: python -m pip install playwright; "
            "python -m playwright install chromium"
        ) from exc

    base_url = base.rstrip("/") + "/"
    parsed = urlparse(base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError("Provide an absolute HTTP(S) site URL.")
    failures = []
    successful_checks = []

    def record(ok: bool, message: str):
        (successful_checks if ok else failures).append(message)

    with sync_playwright() as playwright:
        browser_type = getattr(playwright, engine)
        browser = browser_type.launch(headless=True)
        try:
            for width in VIEWPORTS:
                context = browser.new_context(
                    viewport={"width": width, "height": 850},
                    device_scale_factor=1,
                    reduced_motion="reduce",
                )
                page = context.new_page()
                page.set_default_timeout(timeout_ms)
                for path, label in PUBLIC_PAGES:
                    try:
                        url = urljoin(base_url, path.lstrip("/"))
                        response = page.goto(url, wait_until="domcontentloaded")
                        ok = response is not None and response.status < 400
                        record(ok, f"{width}px {label}: HTTP {response.status if response else 'no response'}")
                        if not ok:
                            continue
                        page.locator("body").wait_for(state="visible")
                        overflow = page.evaluate(
                            "() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth)"
                        )
                        record(overflow <= 8, f"{width}px {label}: horizontal overflow {overflow}px")
                        if path == "/catalog/":
                            links = page.locator(".market-product-card__image-link")
                            record(links.count() > 0, f"{width}px Catalogue: visible product cards exist")
                            if width == 320:
                                filter_toggle = page.locator(".market-mobile-filter > summary")
                                record(filter_toggle.count() > 0, "320px Catalogue: mobile filter control exists")
                                if filter_toggle.count():
                                    filter_toggle.first.click()
                                    record(page.locator("#mobile-market-filter-panel").is_visible(),
                                           "320px Catalogue: mobile filters can be expanded")
                            if links.count():
                                destination = links.first.get_attribute("href")
                                if destination:
                                    detail_url = urljoin(base_url, destination)
                                    if urlparse(detail_url).netloc != parsed.netloc:
                                        record(False, f"{width}px Product: unexpected external product URL")
                                    else:
                                        detail = page.goto(detail_url, wait_until="domcontentloaded")
                                        record(detail is not None and detail.status < 400,
                                               f"{width}px Product: detail page responds")
                                        if detail is not None and detail.status < 400:
                                            html = page.locator("body").inner_text()
                                            record("Staff Merchant readiness" not in html,
                                                   f"{width}px Product: internal merchant diagnostics are hidden")
                                            overflow = page.evaluate(
                                                "() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth)"
                                            )
                                            record(overflow <= 8,
                                                   f"{width}px Product: horizontal overflow {overflow}px")
                    except Exception as exc:
                        record(False, f"{width}px {label}: browser error {type(exc).__name__}: {exc}")
                page.goto(base_url, wait_until="domcontentloaded")
                page.keyboard.press("Tab")
                focusable = page.evaluate(
                    "() => document.activeElement !== document.body && "
                    "document.activeElement !== document.documentElement"
                )
                record(bool(focusable), f"{width}px Home: keyboard focus available")
                context.close()
        finally:
            browser.close()
    return {
        "site": parsed.scheme + "://" + parsed.netloc,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "browser_engine": engine,
        "public_read_only": True,
        "checks_passed": len(successful_checks),
        "checks_failed": len(failures),
        "passed": len(failures) == 0,
        "failures": failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://leosoftug.com")
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--report", help="Optional JSON report output path (no screenshots or customer data)")
    args = parser.parse_args()
    try:
        report = check_site(args.base_url, engine=args.browser, timeout_ms=args.timeout_ms)
    except (RuntimeError, ValueError) as exc:
        parser.exit(2, f"Browser smoke test unavailable: {exc}\n")
    output = json.dumps(report, indent=2)
    if args.report:
        from pathlib import Path
        target = Path(args.report).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
