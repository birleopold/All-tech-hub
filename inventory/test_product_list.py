from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product


class ProductManageListViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            "product-manager",
            "products@example.com",
            "pw",
            is_staff=True,
        )
        cls.laptops = Category.objects.create(
            name="Laptops",
            slug="laptops",
            sort_order=1,
        )
        cls.accessories = Category.objects.create(
            name="Accessories",
            slug="accessories",
            sort_order=2,
        )

        for index in range(30):
            category = cls.laptops if index % 2 == 0 else cls.accessories
            Product.objects.create(
                category=category,
                name=f"Product {index:02d}",
                slug=f"product-{index:02d}",
                sku=f"SKU-{index:02d}",
                price=Decimal(index + 1),
                stock_quantity=index,
            )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("staff_products")

    def test_product_list_is_paginated_at_twenty_five_items(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_paginated"])
        self.assertEqual(len(response.context["products"]), 25)
        self.assertEqual(response.context["paginator"].num_pages, 2)
        self.assertContains(response, "Page 1 of 2")
        self.assertContains(response, 'href="?page=2"')

    def test_category_filter_returns_only_the_selected_category(self):
        response = self.client.get(self.url, {"category": self.laptops.slug})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_category"], self.laptops.slug)
        self.assertEqual(response.context["paginator"].count, 15)
        self.assertTrue(
            all(product.category_id == self.laptops.pk for product in response.context["products"])
        )

    def test_price_desc_sort_orders_products_from_high_to_low(self):
        response = self.client.get(self.url, {"sort": "price_desc"})

        prices = [product.price for product in response.context["products"]]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_sort"], "price_desc")
        self.assertEqual(prices, sorted(prices, reverse=True))
        self.assertEqual(prices[0], Decimal("30"))

    def test_pagination_links_preserve_active_search_and_sort(self):
        response = self.client.get(self.url, {"q": "Product", "sort": "name_desc"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "q=Product&amp;sort=name_desc&amp;page=2")
