"""The Google scheduled-fetch URL must never leak unverified inventory."""
from xml.etree import ElementTree as ET
from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product
from catalog.seo_feeds import GOOGLE_NS
from growth.models import ProductGrowthData
from merchandising.models import ProductCommerceProfile


@override_settings(
    SECURE_SSL_REDIRECT=False,
    MERCHANT_STRICT_READINESS=False,
)
class GoogleApprovedFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(
            name="Test computers", slug="approved-merchant-feed-tests"
        )
        cls.ready_product = Product.objects.create(
            category=category,
            name="Verified test computer",
            slug="google-approved-verified-test-computer",
            price="350000.00",
            stock_quantity=3,
            is_published=True,
            short_description="Test machine with verified catalogue details.",
            image="products/verified-unit.jpg",
        )
        ProductGrowthData.objects.create(
            product=cls.ready_product,
            brand="Demo Manufacturer", condition="new",
            gtin="4006381333931",
        )
        cls.profile = ProductCommerceProfile.objects.create(
            product=cls.ready_product,
            merchant_enabled=True,
            actual_photos=True,
            identity_verified_at=timezone.now(),
            condition_verified_at=timezone.now(),
            stock_confirmed_at=timezone.now(),
            price_verified_at=timezone.now(),
            merchant_shipping_price="15000.00",
        )
        cls.unapproved = Product.objects.create(
            category=category,
            name="Unapproved test computer",
            slug="google-unapproved-test-computer",
            price="120000.00",
            stock_quantity=1,
            is_published=True,
            short_description="An item awaiting staff inspection.",
            image="products/unapproved-unit.jpg",
        )

    def test_approved_source_ignores_legacy_audit_only_setting(self):
        response = self.client.get(reverse("google_approved_merchant_feed"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/rss+xml", response["Content-Type"])
        self.assertEqual(response["X-Merchant-Readiness"], "strict")
        self.assertEqual(response["X-Merchant-Eligible-Items"], "1")
        self.assertEqual(response["X-Merchant-Excluded-Items"], "1")
        root = ET.fromstring(response.content)
        items = root.findall("./channel/item")
        self.assertEqual(len(items), 1)
        ns = {"g": GOOGLE_NS}
        self.assertEqual(
            items[0].find("g:title", ns).text,
            self.ready_product.name,
        )
        self.assertEqual(
            items[0].find("g:shipping/g:price", ns).text,
            "15000.00 UGX",
        )
        self.assertEqual(
            items[0].find("g:availability", ns).text,
            "in_stock",
        )
        self.assertNotIn(self.unapproved.name.encode(), response.content)

    def test_revoking_approval_removes_product_from_feed(self):
        self.profile.merchant_enabled = False
        self.profile.save(update_fields=["merchant_enabled"])
        response = self.client.get(reverse("google_approved_merchant_feed"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Merchant-Eligible-Items"], "0")
        self.assertEqual(len(ET.fromstring(response.content).findall("./channel/item")), 0)

    def test_approved_source_still_fails_closed_if_database_lookup_fails(self):
        with patch("merchandising.merchant.ProductCommerceProfile.objects.filter") as mocked:
            mocked.side_effect = OperationalError("schema unavailable")
            response = self.client.get(reverse("google_approved_merchant_feed"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["X-Merchant-Readiness"], "schema-unavailable")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotIn(b"<item>", response.content)

    def test_existing_legacy_url_is_not_changed(self):
        response = self.client.get(reverse("google_merchant_feed"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Merchant-Readiness"], "audit-only")

    def test_staff_seo_panel_displays_import_source_and_readiness(self):
        from django.contrib.auth import get_user_model

        staff = get_user_model().objects.create_superuser(
            username="approved-feed-admin",
            email="approved@example.invalid",
            password="test-only",
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("staff_seo"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Approved-products XML feed URL")
        self.assertContains(response, "/feeds/google-approved.xml")
        self.assertContains(response, "only staff-approved, fully verified products")
