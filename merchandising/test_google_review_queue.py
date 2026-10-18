"""Google review queue exports never approve or modify inventory."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from catalog.models import Category, Product
from merchandising.management.commands.export_google_review_queue import spreadsheet_safe


class GoogleReviewQueueTests(TestCase):
    def test_spreadsheet_formula_is_not_executable(self):
        self.assertEqual(spreadsheet_safe("=HYPERLINK(\"example\")"), "'=HYPERLINK(\"example\")")
        self.assertEqual(spreadsheet_safe("Normal laptop"), "Normal laptop")

    def test_queue_prioritizes_available_products_without_approving_them(self):
        category = Category.objects.create(name="Accessories", slug="google-review-queue-test")
        in_stock = Product.objects.create(
            category=category, name="Available laptop", slug="google-review-queue-available",
            price="200000.00", track_inventory=True, stock_quantity=2, is_published=True,
        )
        Product.objects.create(
            category=category, name="Unavailable laptop", slug="google-review-queue-unavailable",
            price="200000.00", track_inventory=True, stock_quantity=0, is_published=True,
        )
        with TemporaryDirectory() as folder:
            destination = Path(folder) / "queue.csv"
            call_command("export_google_review_queue", output=str(destination))
            with destination.open(encoding="utf-8-sig", newline="") as source:
                rows = list(csv.DictReader(source))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["product_id"], str(in_stock.pk))
            self.assertEqual(rows[0]["merchant_approved"], "no")
            self.assertEqual(rows[1]["stock_quantity"], "0")
            self.assertIn("commercial profile", rows[0]["missing_checks"])
            self.assertTrue(rows[0]["review_path"].startswith("/staff/"))
            self.assertFalse(destination.with_name("unknown.csv").exists())
        self.assertFalse(hasattr(in_stock, "commerce_profile"))
