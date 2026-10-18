"""Local Google growth reports are factual and read-only."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from catalog.models import Category, Product
from merchandising.management.commands.report_google_growth import google_growth_report


class GoogleGrowthReportTests(TestCase):
    def test_report_labels_local_data_and_preserves_product(self):
        category = Category.objects.create(name="Google report", slug="google-report-tests")
        product = Product.objects.create(
            category=category, name="Unverified stock", slug="google-report-unverified",
            price="1000.00", is_published=True, stock_quantity=0,
        )
        report = google_growth_report()
        self.assertEqual(report["source"], "leosoft-local-audit")
        self.assertIn("not live Google", report["note"])
        self.assertIsNone(report["search_console"]["latest_data_end"])
        self.assertGreaterEqual(report["merchant"]["total_products"], 1)
        product.refresh_from_db()
        self.assertTrue(product.is_published)

    def test_json_output_is_valid_and_atomic(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "google-report.json"
            call_command("report_google_growth", output=str(path))
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("seo", data)
            self.assertIn("merchant", data)
            self.assertIn("search_console", data)
