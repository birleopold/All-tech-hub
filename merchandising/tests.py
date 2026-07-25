from __future__ import annotations

from decimal import Decimal
from unittest.mock import PropertyMock, patch

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product
from catalog.presentation import prepare_public_products
from growth.models import ProductGrowthData
from merchandising.constants import ROOT_COMMERCIAL_SLUGS
from merchandising.models import (
    BuyingGuide,
    CommercialLandingPage,
    DeliveryZone,
    ProductCommerceProfile,
)


class CommercialSeedTests(TestCase):
    def test_seed_creates_research_pages_guides_and_delivery_zones(self):
        call_command("seed_commercial_growth", verbosity=0)
        self.assertEqual(
            set(CommercialLandingPage.objects.values_list("slug", flat=True)),
            set(ROOT_COMMERCIAL_SLUGS),
        )
        self.assertGreaterEqual(BuyingGuide.objects.count(), 15)
        self.assertGreaterEqual(DeliveryZone.objects.count(), 4)
        self.assertTrue(
            CommercialLandingPage.objects.get(slug="laptop-prices-in-uganda").faqs.exists()
        )

    def test_seed_preserves_staff_edits_without_refresh(self):
        call_command("seed_commercial_growth", verbosity=0)
        page = CommercialLandingPage.objects.get(slug="laptop-prices-in-uganda")
        page.title = "Staff-edited laptop hub"
        page.save(update_fields=["title", "updated_at"])
        call_command("seed_commercial_growth", verbosity=0)
        page.refresh_from_db()
        self.assertEqual(page.title, "Staff-edited laptop hub")


class CommercialPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_commercial_growth", verbosity=0)
        cls.category = Category.objects.create(name="Laptops", slug="laptops")
        cls.product = Product.objects.create(
            category=cls.category,
            kind=Product.KIND_PHYSICAL,
            name="Dell Latitude 7420 Core i7 Laptop",
            slug="dell-latitude-7420-core-i7-laptop",
            sku="DL7420",
            short_description="A compact business laptop with fast SSD storage.",
            description="Tested business laptop for office and remote work.",
            price=Decimal("1850000"),
            stock_quantity=2,
            is_published=True,
        )
        ProductGrowthData.objects.create(
            product=cls.product,
            brand="Dell",
            mpn="LAT-7420-I7",
            condition=ProductGrowthData.CONDITION_REFURBISHED,
        )
        ProductCommerceProfile.objects.create(
            product=cls.product,
            processor_family="Intel Core i7",
            processor_generation="11th Gen",
            ram_capacity="16GB",
            storage_capacity="512GB",
            storage_type="SSD",
            actual_photos=True,
            warranty_months=6,
            condition_notes="Tested refurbished unit with light signs of normal use.",
            stock_confirmed_at=timezone.now(),
        )

    def test_root_commercial_page_uses_live_catalogue_and_faq_schema(self):
        response = self.client.get("/laptop-prices-in-uganda/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laptop Prices in Uganda")
        self.assertContains(response, self.product.name)
        self.assertContains(response, '"@type":"FAQPage"')
        self.assertContains(response, "https://leosoftug.com/laptop-prices-in-uganda/")

    def test_brand_page_filters_live_products(self):
        response = self.client.get("/dell-laptops-uganda/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        response = self.client.get("/hp-laptops-uganda/")
        self.assertNotContains(response, self.product.name)

    def test_product_detail_exposes_inspected_facts(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Intel Core i7")
        self.assertContains(response, "16GB")
        self.assertContains(response, "512GB")
        self.assertContains(response, "6-month warranty")
        self.assertContains(response, '"additionalProperty"')

    def test_card_proxy_exposes_verified_decision_signals(self):
        product = (
            Product.objects.select_related("growth_data", "commerce_profile")
            .prefetch_related("gallery_images", "variants")
            .get(pk=self.product.pk)
        )
        card = prepare_public_products([product])[0]
        self.assertTrue(card.public_actual_photos)
        self.assertEqual(card.public_warranty_months, 6)
        self.assertEqual(card.public_processor_summary, "Intel Core i7 11th Gen")
        self.assertEqual(card.public_memory_storage_summary, "16GB / 512GB SSD")

    def test_guide_and_commercial_sitemap_are_indexable(self):
        guide = BuyingGuide.objects.first()
        response = self.client.get(guide.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"@type":"Article"')
        sitemap = self.client.get(reverse("commercial_sitemap"))
        self.assertEqual(sitemap.status_code, 200)
        self.assertContains(sitemap, "/laptop-prices-in-uganda/")
        self.assertContains(sitemap, guide.get_absolute_url())


class MerchantReadinessTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Computers", slug="computers")
        self.product = Product.objects.create(
            category=category,
            name="Lenovo ThinkPad Test Unit",
            slug="lenovo-thinkpad-test-unit",
            sku="THINK-TEST",
            short_description="A fully described product used for readiness tests.",
            price=Decimal("1200000"),
            stock_quantity=1,
            is_published=True,
        )
        self.metadata = ProductGrowthData.objects.create(
            product=self.product,
            brand="Lenovo",
            mpn="20TEST",
            condition=ProductGrowthData.CONDITION_NEW,
        )
        self.profile = ProductCommerceProfile.objects.create(
            product=self.product,
            actual_photos=True,
            merchant_enabled=True,
            merchant_free_shipping=True,
            stock_confirmed_at=timezone.now(),
            price_verified_at=timezone.now(),
        )

    def test_legacy_default_condition_is_not_enough(self):
        missing = self.profile.merchant_missing_fields()
        self.assertIn("identity verification", missing)
        self.assertIn("condition verification", missing)
        self.assertFalse(self.profile.is_merchant_ready)

    def test_explicit_verification_can_make_complete_product_ready(self):
        now = timezone.now()
        self.profile.identity_verified_at = now
        self.profile.condition_verified_at = now
        self.profile.save(
            update_fields=["identity_verified_at", "condition_verified_at", "updated_at"]
        )
        with patch.object(
            Product,
            "primary_display_image",
            new_callable=PropertyMock,
            return_value=object(),
        ):
            self.assertEqual(self.profile.merchant_missing_fields(), [])
            self.assertTrue(self.profile.is_merchant_ready)
            self.assertEqual(self.profile.merchant_readiness_score, 100)
