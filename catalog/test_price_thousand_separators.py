from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product
from merchandising.models import CommercialLandingPage


class CustomerFacingPriceFormattingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Laptops",
            slug="price-format-laptops",
            description="Laptop catalogue used to verify price presentation.",
        )
        cls.product = Product.objects.create(
            category=cls.category,
            kind=Product.KIND_PHYSICAL,
            name="Price Format Laptop",
            slug="price-format-laptop",
            short_description="A product used to verify customer-facing money formatting.",
            description="Detailed product information for price formatting tests.",
            price=Decimal("1000000.00"),
            stock_quantity=2,
            track_inventory=True,
            is_published=True,
        )
        cls.commercial_page = CommercialLandingPage.objects.create(
            slug="price-format-commercial-hub",
            title="Price Format Commercial Hub",
            meta_description="Compare laptop prices with readable thousand separators.",
            intro="A commercial hub used to verify readable prices.",
            category_keywords="laptop",
        )

    def assert_grouped_price(self, response):
        self.assertContains(response, "UGX 1,000,000")
        self.assertNotContains(response, "UGX 1000000.00")

    def test_catalogue_cards_group_every_thousand(self):
        response = self.client.get(reverse("product_list"))

        self.assertEqual(response.status_code, 200)
        self.assert_grouped_price(response)

    def test_commercial_hub_starting_price_is_grouped(self):
        response = self.client.get(self.commercial_page.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assert_grouped_price(response)

    def test_cart_and_checkout_totals_are_grouped(self):
        self.client.post(
            reverse("cart_add", args=[self.product.pk]),
            {"quantity": 1},
        )

        cart_response = self.client.get(reverse("cart"))
        checkout_response = self.client.get(reverse("checkout"))

        self.assertEqual(cart_response.status_code, 200)
        self.assertEqual(checkout_response.status_code, 200)
        self.assert_grouped_price(cart_response)
        self.assert_grouped_price(checkout_response)

    def test_comparison_price_is_grouped(self):
        self.client.post(
            reverse("product_compare_toggle", args=[self.product.pk]),
            {"next": reverse("product_compare")},
        )

        response = self.client.get(reverse("product_compare"))

        self.assertEqual(response.status_code, 200)
        self.assert_grouped_price(response)
