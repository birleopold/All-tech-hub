import os
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product
from catalog.quality import catalogue_quality_rows, catalogue_quality_summary


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
        with patch.dict(os.environ, {"ALLTECH_RELEASE_SHA": "release-123"}):
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
