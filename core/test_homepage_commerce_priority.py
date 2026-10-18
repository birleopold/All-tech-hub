"""Homepage must show true service pricing and prioritise primary actions."""
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product


@override_settings(SECURE_SSL_REDIRECT=False)
class HomepageCommercePriorityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Service", slug="priority-service")
        Product.objects.create(
            name="Laptop repair without set price",
            slug="homepage-unpriced-repair",
            category=category,
            kind=Product.KIND_SERVICE,
            price=0,
            track_inventory=False,
            is_published=True,
            is_featured=True,
        )
        Product.objects.create(
            name="Network setup priced service",
            slug="homepage-priced-setup",
            category=category,
            kind=Product.KIND_SERVICE,
            price=75000,
            track_inventory=False,
            is_published=True,
            is_featured=True,
        )

    def test_service_cards_avoid_zero_price_and_show_quotation(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laptop repair without set price")
        self.assertContains(response, "Request a quotation")
        self.assertNotContains(response, "From UGX 0")
        self.assertContains(response, "From UGX 75000")

    def test_products_services_and_help_are_easy_to_find(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertLess(html.index('id="homepage-products"'),
                        html.index("Technology support beyond the sale"))
        self.assertLess(html.index("Technology support beyond the sale"),
                        html.index("Choose according to the job"))
        self.assertIn("<details", html)
        self.assertIn("More buying guidance and how LEOSOFT supports customers", html)
