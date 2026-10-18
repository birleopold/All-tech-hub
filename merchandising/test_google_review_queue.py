"""Google review queue exports never approve or modify inventory."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.urls import reverse
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

    def test_variant_stock_is_prioritized_even_when_base_quantity_zero(self):
        from catalog.models import ProductVariant
        category = Category.objects.create(name="Variant category", slug="variant-google-review")
        product = Product.objects.create(category=category, name="Variant laptop",
            slug="variant-google-laptop", price="250000.00",
            track_inventory=True, stock_quantity=0, is_published=True)
        ProductVariant.objects.create(product=product, name="8GB RAM", sku="VAR-LAPTOP-8",
            price="250000.00", is_active=True, track_inventory=True, stock_quantity=4)
        from merchandising.management.commands.export_google_review_queue import build_google_review_rows
        rows = build_google_review_rows(available_only=True)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["product_id"], product.pk)
        self.assertEqual(rows[0]["stock_quantity"], 4)

    def test_staff_download_is_protected_and_contains_review_links(self):
        url = reverse("staff_google_review_queue")
        anonymous = self.client.get(url)
        self.assertNotEqual(anonymous.status_code, 200)
        staff = get_user_model().objects.create_user(
            username="merchant-review-staff", password="test-only", is_staff=True,
        )
        self.client.force_login(staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("merchant_approved", response.content.decode("utf-8-sig"))

    def test_seo_page_provides_in_stock_priorities(self):
        category = Category.objects.create(name="Ready queue", slug="ready-queue-extra")
        product = Product.objects.create(
            category=category, name="Ready Stock Unit", slug="ready-stock-extra",
            price="120000.00", track_inventory=True, stock_quantity=3,
            is_published=True,
        )
        staff = get_user_model().objects.create_user(
            username="seo-priority-staff", password="test-only", is_staff=True,
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("staff_seo"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, product.name)
        self.assertContains(response, "Google review: products with recorded stock")
