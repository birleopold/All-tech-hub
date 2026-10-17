from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product


class PublicExperienceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Computers",
            slug="computers",
            description="Computers for work and learning.",
        )
        cls.product = Product.objects.create(
            category=cls.category,
            kind=Product.KIND_PHYSICAL,
            name="Professional Laptop",
            slug="professional-laptop",
            sku="LAP-PRO-1",
            short_description="A dependable laptop for everyday professional work.",
            price=Decimal("2500000.00"),
            stock_quantity=3,
            is_published=True,
            is_featured=True,
        )
        cls.service = Product.objects.create(
            category=cls.category,
            kind=Product.KIND_SERVICE,
            name="Laptop diagnostics",
            slug="laptop-diagnostics",
            short_description="Professional inspection and fault diagnosis.",
            price=Decimal("50000.00"),
            track_inventory=False,
            is_published=True,
            is_featured=True,
        )

    def test_homepage_renders_mature_public_sections(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "public-home-page")
        self.assertContains(response, "Technology that works for you.")
        self.assertContains(response, "Shop our products")
        self.assertContains(response, self.product.name)
        self.assertContains(response, self.service.name)
        self.assertContains(response, "public_experience.css")
        self.assertEqual(response.context["catalog_stats"]["products"], 1)
        self.assertEqual(response.context["catalog_stats"]["services"], 1)
        self.assertEqual(response.context["catalog_categories"][0].public_item_count, 2)

    def test_catalog_renders_discovery_layout_and_filters(self):
        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "public-catalog-page")
        self.assertContains(response, "Search, filter and compare with confidence")
        self.assertContains(response, "market-filter-panel")
        self.assertContains(response, "market-product-card")
        self.assertContains(response, self.product.name)
        self.assertContains(response, self.service.name)

    def test_catalog_search_and_kind_filters_remain_functional(self):
        search_response = self.client.get(reverse("product_list"), {"q": "LAP-PRO-1"})
        self.assertContains(search_response, self.product.name)
        self.assertNotContains(search_response, self.service.name)

        service_response = self.client.get(
            reverse("product_list"),
            {"kind": Product.KIND_SERVICE},
        )
        self.assertContains(service_response, self.service.name)
        self.assertNotContains(service_response, self.product.name)

    def test_service_worker_precaches_new_public_assets(self):
        response = self.client.get(reverse("service_worker"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "leosoft-public-assets-v7")
        self.assertContains(response, "public_experience")
