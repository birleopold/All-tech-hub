from __future__ import annotations

import tempfile
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product, ProductImage, ProductVariant
from core.models import AuditEvent
from growth.models import ProductGrowthData
from merchandising.models import (
    BuyingGuide,
    CommercialLandingPage,
    ProductCommerceProfile,
    SearchQueryInsight,
)
from merchandising.services import apply_bulk_catalogue_enrichment

TEST_MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="leosoft-growth-operations-"))
ONE_PIXEL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00"
    b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00"
    b"\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


@override_settings(
    MEDIA_ROOT=TEST_MEDIA_ROOT,
    PUBLIC_BASE_URL="https://leosoftug.com",
)
class CatalogueGrowthOperationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(
            username="catalogue-growth-staff",
            password="test-password-123",
            is_staff=True,
        )
        cls.category = Category.objects.create(
            name="Laptops",
            slug="catalogue-growth-laptops",
            description="Laptops for work, learning and business use.",
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def create_product(self, *, name="Dell Latitude Growth Test", stock=2):
        return Product.objects.create(
            category=self.category,
            kind=Product.KIND_PHYSICAL,
            name=name,
            slug=name.lower().replace(" ", "-")[:200],
            short_description="A business laptop prepared for catalogue testing.",
            description="A detailed business laptop description for customers.",
            price=Decimal("1500000"),
            stock_quantity=stock,
            track_inventory=True,
            is_published=True,
        )

    def test_commercial_review_route_renders_for_physical_product(self):
        product = self.create_product()

        response = self.client.get(
            reverse("staff_product_commercial_review", args=[product.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, product.name)
        self.assertContains(response, "Merchant readiness")

    def test_bulk_enrichment_updates_only_selected_verified_facts(self):
        product = self.create_product()
        gallery = ProductImage.objects.create(
            product=product,
            image=SimpleUploadedFile(
                "dell-latitude.gif",
                ONE_PIXEL_GIF,
                content_type="image/gif",
            ),
            alt_text="",
        )

        response = self.client.post(
            reverse("staff_catalogue_bulk_enrichment"),
            {
                "product_ids": [str(product.pk)],
                "brand": "Dell",
                "condition": ProductGrowthData.CONDITION_REFURBISHED,
                "warranty_months": "6",
                "delivery_note": "Delivery confirmed before payment.",
                "shipping_mode": "price",
                "merchant_shipping_price": "10000",
                "generate_missing_sku": "on",
                "fill_blank_alt_text": "on",
                "confirm_actual_photos": "on",
                "verify_identity": "on",
                "verify_condition": "on",
                "verify_stock": "on",
                "verify_price": "on",
            },
        )

        self.assertRedirects(response, reverse("staff_catalogue_bulk_enrichment"))
        product.refresh_from_db()
        gallery.refresh_from_db()
        metadata = product.growth_data
        profile = product.commerce_profile
        self.assertEqual(product.sku, f"LS-{product.pk:06d}")
        self.assertEqual(metadata.brand, "Dell")
        self.assertEqual(metadata.condition, ProductGrowthData.CONDITION_REFURBISHED)
        self.assertEqual(profile.warranty_months, 6)
        self.assertEqual(profile.merchant_shipping_price, Decimal("10000"))
        self.assertFalse(profile.merchant_free_shipping)
        self.assertTrue(profile.actual_photos)
        self.assertIsNotNone(profile.identity_verified_at)
        self.assertIsNotNone(profile.condition_verified_at)
        self.assertIsNotNone(profile.stock_confirmed_at)
        self.assertIsNotNone(profile.price_verified_at)
        self.assertFalse(profile.merchant_enabled)
        self.assertIn(product.name, gallery.alt_text)
        self.assertIn("refurbished", gallery.alt_text.lower())
        self.assertTrue(
            AuditEvent.objects.filter(verb="catalog.bulk_enrichment").exists()
        )

    def test_sku_only_job_does_not_create_unverified_feed_or_commercial_rows(self):
        product = self.create_product(name="Generic Laptop SKU Safety")

        result = apply_bulk_catalogue_enrichment(
            products=[product],
            cleaned_data={"generate_missing_sku": True},
            actor=self.staff,
        )

        product.refresh_from_db()
        self.assertEqual(result["skus_generated"], 1)
        self.assertTrue(product.sku)
        self.assertFalse(ProductGrowthData.objects.filter(product=product).exists())
        self.assertFalse(
            ProductCommerceProfile.objects.filter(product=product).exists()
        )

    def test_bulk_condition_verification_requires_explicit_condition(self):
        product = self.create_product(name="Condition Verification Safety")
        ProductGrowthData.objects.create(product=product, brand="HP")

        result = apply_bulk_catalogue_enrichment(
            products=[product],
            cleaned_data={"verify_condition": True},
            actor=self.staff,
        )

        profile = product.commerce_profile
        self.assertIsNone(profile.condition_verified_at)
        self.assertEqual(result["condition_verification_skipped"], 1)

    def test_search_console_csv_import_surfaces_growth_opportunity(self):
        report = SimpleUploadedFile(
            "Queries.csv",
            (
                "Top queries,Clicks,Impressions,CTR,Position\n"
                "laptop prices in uganda,10,1000,1%,8.2\n"
            ).encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(
            reverse("staff_seo"),
            {
                "date_start": "2026-07-01",
                "date_end": "2026-07-27",
                "csv_file": report,
            },
        )

        self.assertRedirects(response, reverse("staff_seo"))
        insight = SearchQueryInsight.objects.get(query="laptop prices in uganda")
        self.assertEqual(insight.clicks, 10)
        self.assertEqual(insight.impressions, 1000)
        self.assertEqual(insight.ctr, Decimal("0.0100"))
        self.assertEqual(insight.date_start, date(2026, 7, 1))
        dashboard = self.client.get(reverse("staff_seo"))
        self.assertContains(dashboard, "laptop prices in uganda")
        self.assertContains(dashboard, "Page-one opportunity")

    def test_strict_merchant_audit_blocks_enabled_incomplete_product(self):
        product = self.create_product(name="Incomplete Merchant Product")
        ProductCommerceProfile.objects.create(
            product=product,
            merchant_enabled=True,
        )

        with self.assertRaises(CommandError):
            call_command("audit_merchant", "--strict", stdout=StringIO())

    def test_commercial_hub_uses_variant_price_and_paginates(self):
        page = CommercialLandingPage.objects.create(
            slug="test-laptop-prices-in-uganda",
            title="Test Laptop Prices in Uganda",
            meta_description="Compare test laptop prices and verified options.",
            intro="A test commercial landing page for laptop prices.",
            category_keywords="laptop",
            search_terms="notebook",
        )
        related_page = CommercialLandingPage.objects.create(
            slug="test-business-laptops-uganda",
            title="Test Business Laptops Uganda",
            meta_description="Compare business laptops for professional work.",
            intro="Business laptop guidance.",
            category_keywords="laptop,business",
        )
        guide = BuyingGuide.objects.create(
            title="Test laptop buying guide",
            slug="test-laptop-buying-guide",
            excerpt="How to compare laptop specifications and condition.",
            body="Detailed laptop guidance.",
            keywords="laptop",
        )
        products = []
        for index in range(25):
            products.append(
                Product.objects.create(
                    category=self.category,
                    kind=Product.KIND_PHYSICAL,
                    name=f"Laptop Hub Product {index:02d}",
                    slug=f"laptop-hub-product-{index:02d}",
                    short_description="A laptop for commercial hub testing.",
                    description="Detailed laptop catalogue information.",
                    price=Decimal("2000000") + index,
                    stock_quantity=1,
                    is_published=True,
                )
            )
        ProductVariant.objects.create(
            product=products[0],
            name="8GB / 256GB SSD",
            sku="HUB-VARIANT-1",
            price=Decimal("1250000"),
            stock_quantity=1,
            is_active=True,
        )

        response = self.client.get(page.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["price_min"], Decimal("1250000"))
        self.assertEqual(response.context["paginator"].num_pages, 2)
        self.assertEqual(response.context["available_count"], 25)
        self.assertContains(response, related_page.title)
        self.assertContains(response, guide.title)
        self.assertContains(response, 'rel="next"', html=False)

        second_page = self.client.get(page.get_absolute_url(), {"page": 2})
        self.assertContains(
            second_page,
            f'<link rel="canonical" href="https://leosoftug.com{page.get_absolute_url()}?page=2">',
            html=False,
        )

    def test_product_page_links_relevant_hubs_and_guides(self):
        product = self.create_product(name="Dell Authority Link Product")
        ProductGrowthData.objects.create(
            product=product,
            brand="Dell",
            condition=ProductGrowthData.CONDITION_REFURBISHED,
        )
        ProductCommerceProfile.objects.create(
            product=product,
            identity_verified_at=timezone.now(),
            condition_verified_at=timezone.now(),
        )
        page = CommercialLandingPage.objects.create(
            slug="dell-authority-test",
            title="Dell Laptops Authority Test",
            meta_description="Compare Dell laptop options.",
            intro="Dell laptop comparison.",
            brand="Dell",
            category_keywords="laptop",
        )
        guide = BuyingGuide.objects.create(
            title="Dell laptop authority guide",
            slug="dell-laptop-authority-guide",
            excerpt="How to choose a Dell laptop.",
            body="Detailed Dell laptop guidance.",
            keywords="Dell,laptop",
        )

        response = self.client.get(product.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, page.title)
        self.assertContains(response, guide.title)
