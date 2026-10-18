"""Google review queue exports never approve or modify inventory."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import TestCase
from django.utils import timezone

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
            self.assertEqual(rows[0]["feed_eligible_now"], "no")
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

    def test_merchant_approval_requires_permission_and_saved_facts(self):
        from django.contrib.auth.models import Permission
        from merchandising.models import ProductCommerceProfile
        category = Category.objects.create(name="Merchant gate", slug="merchant-gate-test")
        product = Product.objects.create(
            category=category, name="Unverified stock", slug="merchant-gate-unit",
            price="100000.00", is_published=True, track_inventory=True,
            stock_quantity=2,
        )
        profile = ProductCommerceProfile.objects.create(product=product)
        staff = get_user_model().objects.create_user(
            username="merchant-gate-staff", password="test-only", is_staff=True
        )
        url = reverse("staff_product_merchant_approval", args=[product.pk])
        self.client.force_login(staff)
        response = self.client.post(url, {"action": "approve"})
        self.assertEqual(response.status_code, 403)
        staff.user_permissions.add(
            Permission.objects.get(codename="change_productcommerceprofile")
        )
        response = self.client.post(url, {"action": "approve"})
        self.assertEqual(response.status_code, 302)
        profile.refresh_from_db()
        self.assertFalse(profile.merchant_enabled)

    def test_merchant_approval_revoke_is_idempotent(self):
        from django.contrib.auth.models import Permission
        from merchandising.models import ProductCommerceProfile
        category = Category.objects.create(name="Revocation", slug="merchant-revoke-test")
        product = Product.objects.create(
            category=category, name="Previously approved", slug="merchant-revoke-unit",
            price="100000.00", is_published=True,
        )
        profile = ProductCommerceProfile.objects.create(product=product, merchant_enabled=True)
        staff = get_user_model().objects.create_user(
            username="merchant-revoke-staff", password="test-only", is_staff=True
        )
        staff.user_permissions.add(
            Permission.objects.get(codename="change_productcommerceprofile")
        )
        self.client.force_login(staff)
        url = reverse("staff_product_merchant_approval", args=[product.pk])
        self.assertEqual(self.client.post(url, {"action": "disable"}).status_code, 302)
        self.assertEqual(self.client.post(url, {"action": "disable"}).status_code, 302)
        profile.refresh_from_db()
        self.assertFalse(profile.merchant_enabled)

    def test_approved_but_expired_stock_is_not_claimed_as_feed_eligible(self):
        from merchandising.models import ProductCommerceProfile
        category = Category.objects.create(name="Stale stock", slug="stale-stock-queue-test")
        product = Product.objects.create(
            category=category, name="Approved but stale",
            slug="approved-stale-queue", price="100000.00",
            track_inventory=True, stock_quantity=5, is_published=True,
        )
        ProductCommerceProfile.objects.create(
            product=product, merchant_enabled=True,
            stock_confirmed_at=timezone.now() - timezone.timedelta(days=31),
        )
        with TemporaryDirectory() as folder:
            dest = Path(folder) / "stale.csv"
            call_command("export_google_review_queue", output=str(dest))
            with dest.open(encoding="utf-8-sig", newline="") as source:
                row = next(r for r in csv.DictReader(source)
                           if r["product_id"] == str(product.pk))
        self.assertEqual(row["merchant_approved"], "yes")
        self.assertEqual(row["feed_eligible_now"], "no")
        self.assertIn("renew stock inspection", row["missing_checks"])
