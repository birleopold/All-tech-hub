"""Private Google snapshot dashboard regression coverage."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from dashboard.google_report import google_dashboard_metrics


class GoogleReportDashboardTests(SimpleTestCase):
    def test_missing_report_has_clear_state(self):
        with TemporaryDirectory() as root, override_settings(BASE_DIR=Path(root)):
            self.assertEqual(google_dashboard_metrics()["state"], "unavailable")

    def test_private_report_shows_only_uganda_free_listings(self):
        with TemporaryDirectory() as root, override_settings(BASE_DIR=Path(root)):
            path = Path(root) / "google-reports" / "google-growth-latest.json"
            path.parent.mkdir()
            path.write_text(json.dumps({
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "windsor": {
                    "status": "queried",
                    "accounts": {
                        "analytics": {"status": "ok", "rows": [{"active_users": 13}]},
                        "merchant": {"status": "ok", "rows": [
                            {"product_status_country": "UG", "product_status_reporting_context": "FREE_LISTINGS", "product_status_active_count": 0, "product_status_pending_count": 27, "product_status_disapproved_count": 0},
                            {"product_status_country": "US", "product_status_reporting_context": "FREE_LISTINGS", "product_status_active_count": 9, "product_status_pending_count": 0, "product_status_disapproved_count": 0},
                        ]},
                        "search": {"status": "ok", "rows": [
                            {"query": "gaming laptop uganda", "page": "https://leosoftug.com/catalog/", "clicks": 2, "impressions": 10, "position": 4},
                        ]},
                    },
                },
            }), encoding="utf-8")
            result = google_dashboard_metrics()
            self.assertEqual(result["state"], "ready")
            self.assertEqual(result["analytics"], 13)
            self.assertEqual(result["merchant"]["pending"], 27)
            self.assertEqual(result["merchant"]["active"], 0)
            self.assertEqual(len(result["queries"]), 1)

    def test_stale_report_is_labelled(self):
        with TemporaryDirectory() as root, override_settings(BASE_DIR=Path(root)):
            path = Path(root) / "google-reports" / "google-growth-latest.json"
            path.parent.mkdir()
            path.write_text(json.dumps({
                "generated_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
                "windsor": {"status": "not_configured"},
            }))
            result = google_dashboard_metrics()
            self.assertTrue(result["stale"])
            self.assertEqual(result["state"], "not_configured")
