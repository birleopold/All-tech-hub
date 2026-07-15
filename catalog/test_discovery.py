from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product


class CatalogDiscoveryTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Computers", slug="computers")
        for index in range(15):
            Product.objects.create(
                category=self.category,
                kind=Product.KIND_PHYSICAL,
                name=f"Laptop {index:02d}",
                slug=f"laptop-{index:02d}",
                price=1000000 + (index * 100000),
                stock_quantity=2,
                is_published=True,
                is_featured=True,
            )
        for index in range(4):
            Product.objects.create(
                category=self.category,
                kind=Product.KIND_SERVICE,
                name=f"IT Service {index:02d}",
                slug=f"it-service-{index:02d}",
                price=50000 + (index * 10000),
                is_published=True,
                is_featured=True,
            )

    def _page_ids(self, response):
        return [product.pk for product in response.context["products"]]

    def test_discovery_seed_is_stable_across_pagination(self):
        seed = "0123456789abcdef"
        first = self.client.get(reverse("product_list"), {"view": seed})
        second = self.client.get(
            reverse("product_list"),
            {"view": seed, "page": 2},
        )

        first_ids = self._page_ids(first)
        second_ids = self._page_ids(second)
        self.assertEqual(first.context["rotation_seed"], seed)
        self.assertEqual(second.context["rotation_seed"], seed)
        self.assertFalse(set(first_ids) & set(second_ids))
        self.assertEqual(len(first_ids) + len(second_ids), 19)

    def test_explicit_name_sort_overrides_rotation(self):
        response = self.client.get(reverse("product_list"), {"sort": "name"})
        names = [product.name for product in response.context["products"]]

        self.assertEqual(names, sorted(names))
        self.assertEqual(response.context["current_sort"], "name")
        self.assertEqual(response.context["rotation_seed"], "")

    def test_explicit_price_sort_overrides_rotation(self):
        response = self.client.get(
            reverse("product_list"),
            {"kind": Product.KIND_PHYSICAL, "sort": "price_high"},
        )
        prices = [product.price for product in response.context["products"]]

        self.assertEqual(prices, sorted(prices, reverse=True))

    @patch(
        "catalog.discovery.new_rotation_seed",
        side_effect=["1111111111111111", "2222222222222222"],
    )
    def test_home_rotates_products_and_services_separately(self, mocked_seed):
        response = self.client.get(reverse("home"))

        featured_products = list(response.context["featured_products"])
        featured_services = list(response.context["featured_services"])
        self.assertTrue(featured_products)
        self.assertTrue(featured_services)
        self.assertTrue(
            all(product.kind == Product.KIND_PHYSICAL for product in featured_products)
        )
        self.assertTrue(
            all(product.kind == Product.KIND_SERVICE for product in featured_services)
        )
        self.assertEqual(mocked_seed.call_count, 2)
