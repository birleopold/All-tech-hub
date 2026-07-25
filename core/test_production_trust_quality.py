import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product
from catalog.quality import catalogue_quality_rows, catalogue_quality_summary
from core.backups import latest_backup_status
from core.models import ContactMessage


class ProductionHealthAndHeadersTests(TestCase):
    def test_liveness_and_readiness_are_non_cacheable(self):
        live = self.client.get(reverse("health_live"))
        ready = self.client.get(reverse("health_ready"))
        legacy = self.client.get(reverse("healthz"))

        self.assertEqual(live.status_code, 200)
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(live.json()["status"], "ok")
        self.assertEqual(ready.json()["database"], "ok")
        for response in (live, ready, legacy):
            self.assertEqual(response["Cache-Control"], "no-store, max-age=0")
            self.assertIn("noindex", response["X-Robots-Tag"])
            self.assertTrue(response["X-Request-ID"])

    def test_release_label_and_safe_request_id_are_exposed(self):
        with patch("core.health.RUNNING_RELEASE", "release-123"):
            response = self.client.get(
                reverse("health_live"),
                HTTP_X_REQUEST_ID="customer-report-1234",
            )

        self.assertEqual(response.json()["release"], "release-123")
        self.assertEqual(response["X-Request-ID"], "customer-report-1234")

        replaced = self.client.get(
            reverse("health_live"),
            HTTP_X_REQUEST_ID="bad request id with spaces",
        )
        self.assertNotEqual(
            replaced["X-Request-ID"],
            "bad request id with spaces",
        )

    def test_private_pages_are_not_cached_and_common_security_headers_exist(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("noindex", response["X-Robots-Tag"])
        self.assertEqual(response["X-Permitted-Cross-Domain-Policies"], "none")
        self.assertEqual(response["Cross-Origin-Resource-Policy"], "same-site")
        self.assertTrue(response["X-Request-ID"])

    @override_settings(DEBUG=False)
    def test_not_found_page_includes_support_reference(self):
        response = self.client.get(
            "/this-page-does-not-exist/",
            HTTP_X_REQUEST_ID="missing-page-1234",
        )

        self.assertEqual(response.status_code, 404)
        self.assertContains(
            response,
            "We could not find that page",
            status_code=404,
        )
        self.assertContains(response, "missing-page-1234", status_code=404)
        self.assertEqual(response["Cache-Control"], "no-store, max-age=0")
        self.assertIn("noindex", response["X-Robots-Tag"])


class PublicBuyingGuideTests(TestCase):
    def test_buying_guide_explains_condition_and_confirmation_steps(self):
        response = self.client.get(reverse("buying_guide"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "What the condition labels mean")
        self.assertContains(response, "New equipment")
        self.assertContains(response, "Prepared for resale")
        self.assertContains(response, "Pre-owned equipment")
        self.assertContains(response, "Request written confirmation")
        self.assertContains(response, reverse("product_compare"))
        self.assertNotContains(response, "style=", html=False)

    def test_buying_guide_is_discoverable_from_navigation_and_sitemap(self):
        home = self.client.get(reverse("home"))
        sitemap = self.client.get(reverse("seo_sitemap", args=["static"]))

        self.assertContains(home, reverse("buying_guide"))
        self.assertEqual(sitemap.status_code, 200)
        self.assertContains(sitemap, reverse("buying_guide"))


class ContactAbuseProtectionTests(TestCase):
    def test_contact_honeypot_rejects_automated_submission(self):
        response = self.client.post(
            reverse("contact"),
            {
                "request_type": "product",
                "name": "Automated Sender",
                "email": "bot@example.com",
                "phone": "0700000000",
                "subject": "Bulk request",
                "message": "This otherwise looks like a valid contact request.",
                "website": "https://spam.example.com",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ContactMessage.objects.count(), 0)
        self.assertContains(response, "Your request could not be accepted")

    def test_contact_form_still_accepts_legitimate_submission(self):
        response = self.client.post(
            reverse("contact"),
            {
                "request_type": "product",
                "name": "Real Customer",
                "email": "customer@example.com",
                "phone": "0700000000",
                "subject": "Laptop question",
                "message": "Please confirm the available specification and price.",
                "website": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)


class BackupCommandTests(TransactionTestCase):
    reset_sequences = True

    def test_sqlite_backup_contains_database_manifest_and_checksum(self):
        if not settings.DATABASES["default"]["ENGINE"].endswith("sqlite3"):
            self.skipTest("SQLite-specific online backup verification")

        ContactMessage.objects.create(
            name="Backup Customer",
            email="backup@example.com",
            subject="Backup record",
            message="This row proves the database was populated before backup.",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            backup_root = Path(temporary_directory)
            with override_settings(BACKUP_ROOT=backup_root):
                call_command("backup_project", "--retention-days=0")
                status = latest_backup_status()

            backup_directories = list(backup_root.glob("leosoft-*"))
            self.assertEqual(len(backup_directories), 1)
            backup_directory = backup_directories[0]
            database_path = backup_directory / "database.sqlite3"
            manifest_path = backup_directory / "manifest.json"
            self.assertTrue(database_path.exists())
            self.assertGreater(database_path.stat().st_size, 0)
            self.assertTrue(manifest_path.exists())
            self.assertTrue(status.exists)
            self.assertTrue(status.healthy)
            self.assertEqual(status.path, backup_directory)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            database_record = next(
                item for item in manifest["files"] if item["name"] == "database.sqlite3"
            )
            self.assertEqual(database_record["size_bytes"], database_path.stat().st_size)
            self.assertEqual(len(database_record["sha256"]), 64)


class CatalogueQualityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Quality laptops",
            slug="quality-laptops",
            description="",
        )
        cls.product = Product.objects.create(
            category=cls.category,
            kind=Product.KIND_PHYSICAL,
            name="Incomplete quality test laptop",
            slug="incomplete-quality-test-laptop",
            price=Decimal("1000000"),
            stock_quantity=0,
            is_published=True,
        )
        cls.staff = get_user_model().objects.create_user(
            username="quality-staff",
            password="test-password-123",
            is_staff=True,
        )

    def test_incomplete_public_product_is_scored_and_explained(self):
        rows = catalogue_quality_rows()
        row = next(item for item in rows if item.product.pk == self.product.pk)
        codes = {issue.code for issue in row.issues}

        self.assertEqual(row.status, "critical")
        self.assertLess(row.score, 60)
        self.assertIn("image_missing", codes)
        self.assertIn("short_copy_missing", codes)
        self.assertIn("detail_copy_missing", codes)
        self.assertIn("sku_missing", codes)
        self.assertIn("growth_data_missing", codes)
        self.assertIn("base_stock_missing", codes)

        summary = catalogue_quality_summary(rows)
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["critical"], 1)

    def test_staff_quality_workspace_lists_actionable_gaps(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("staff_catalogue_quality"),
            {"status": "critical"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Product listing quality")
        self.assertContains(response, self.product.name)
        self.assertContains(response, "No customer-visible image")
        self.assertContains(
            response,
            reverse("staff_product_edit", args=[self.product.pk]),
        )

    def test_project_audit_command_reports_catalogue_summary(self):
        with patch.dict(os.environ, {"ALLTECH_ENV": "development"}):
            call_command("audit_project")
