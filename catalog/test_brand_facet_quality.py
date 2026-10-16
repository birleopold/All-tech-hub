"""Regression tests for brand filters, staff editing cues and unpriced services."""
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.brand_facets import grouped_brand_rows
from catalog.models import Category, Product
from growth.models import ProductGrowthData


@override_settings(SECURE_SSL_REDIRECT=False)
class CatalogBrandConsistencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Laptops", slug="brand-test-laptops")
        cls.products = []
        for index, brand in enumerate(("Samsung", "SAMSUNG", " Samsung ")):
            product = Product.objects.create(
                category=category,
                name=f"Galaxy Notebook {index}",
                slug=f"brand-test-galaxy-{index}",
                price=Decimal("350000.00"),
                stock_quantity=2,
                is_published=True,
            )
            ProductGrowthData.objects.create(product=product, brand=brand)
            cls.products.append(product)
        cls.user = get_user_model().objects.create_user(
            username="brand-reviewer", password="test-password", is_staff=True
        )

    def test_brand_grouping_preserves_counts_and_source_spellings(self):
        groups = grouped_brand_rows([
            {"brand": "SAMSUNG", "product_count": 2},
            {"brand": "Samsung", "product_count": 3},
            {"brand": " Samsung ", "product_count": 1},
            {"brand": "  ", "product_count": 4},
        ])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["brand"], "Samsung")
        self.assertEqual(groups[0]["product_count"], 6)
        self.assertEqual(len(groups[0]["variants"]), 3)

    def test_public_filters_group_case_and_space_variations(self):
        response = self.client.get(reverse("product_list"))
        self.assertEqual(response.status_code, 200)
        brands = [row for row in response.context["catalog_brands"]
                  if row["brand"] == "Samsung"]
        self.assertEqual(len(brands), 1)
        self.assertEqual(brands[0]["product_count"], 3)
        filtered = self.client.get(reverse("product_list"), {"brand": "samsung"})
        self.assertEqual(filtered.context["paginator"].count, 3)
        self.assertEqual(filtered.context["current_brand"], "Samsung")

    def test_canonical_brand_route_and_search_suggestions(self):
        response = self.client.get(reverse("product_brand", args=["samsung"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["paginator"].count, 3)
        suggestions = self.client.get(
            reverse("catalog_suggestions"), {"q": "sams"}
        ).json()
        matches = [row for row in suggestions["brands"]
                   if row["name"] == "Samsung"]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["count"], 3)

    def test_staff_workspace_flags_inconsistent_names_without_rewriting(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("staff_catalogue_quality"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Brand names to standardize")
        self.assertEqual(response.context["duplicate_brand_group_count"], 1)
        self.assertEqual(response.context["duplicate_brand_groups"][0]["product_count"], 3)
        self.assertEqual(
            set(ProductGrowthData.objects.values_list("brand", flat=True)),
            {"Samsung", "SAMSUNG", " Samsung "},
        )


@override_settings(SECURE_SSL_REDIRECT=False)
class UnpricedServicePresentationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Support", slug="service-price-test")
        cls.unpriced = Product.objects.create(
            category=category, name="Network assessment", slug="service-price-assessment",
            kind=Product.KIND_SERVICE, price=Decimal("0.00"),
            track_inventory=False, is_published=True,
        )
        cls.priced = Product.objects.create(
            category=category, name="Network installation", slug="service-price-install",
            kind=Product.KIND_SERVICE, price=Decimal("75000.00"),
            track_inventory=False, is_published=True,
        )

    def test_unpriced_service_requires_estimate_not_zero_price(self):
        response = self.client.get(self.unpriced.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Request an estimate")
        self.assertNotContains(response, 'property="product:price:amount"')
        schema = json.loads(str(response.context["product_schema_json"]))
        self.assertEqual(schema["@type"], "Service")
        self.assertNotIn("price", schema["offers"])
        self.assertNotIn("priceCurrency", schema["offers"])

    def test_priced_service_keeps_real_price_in_schema_and_metadata(self):
        response = self.client.get(self.priced.get_absolute_url())
        self.assertContains(response, 'property="product:price:amount"')
        schema = json.loads(str(response.context["product_schema_json"]))
        self.assertEqual(schema["offers"]["price"], "75000.00")
