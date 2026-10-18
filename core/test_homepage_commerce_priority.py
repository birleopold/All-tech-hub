"""Homepage is a concise shop front, not a long educational landing page."""
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
            price=0, track_inventory=False, is_published=True, is_featured=True,
        )
        Product.objects.create(
            name="Network setup priced service",
            slug="homepage-priced-setup",
            category=category,
            kind=Product.KIND_SERVICE,
            price=75000, track_inventory=False, is_published=True, is_featured=True,
        )

    def test_service_cards_avoid_zero_price_and_show_quotation(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Laptop repair without set price")
        self.assertContains(response, "Request a quotation")
        self.assertNotContains(response, "From UGX 0")
        self.assertContains(response, "From UGX 75000")

    def test_homepage_has_only_primary_shopping_and_short_trust_content(self):
        response = self.client.get(reverse("home"))
        html = response.content.decode().split('<main id="main-content"', 1)[1].split("</main>", 1)[0]
        self.assertLess(html.index('id="homepage-products"'), html.index("Technology support beyond the sale"))
        self.assertLess(html.index("Technology support beyond the sale"), html.index("Shop with confidence"))
        self.assertContains(response, "Shop our products")
        self.assertContains(response, "Shop with confidence")
        self.assertContains(response, reverse("buying_guide_list"))
        for removed in (
            "Choose according to the job", "Narrow the options before comparing",
            "Recently viewed", "Refurbished technology",
            "More buying guidance and how LEOSOFT supports customers",
            "Make a better decision before spending", "Start with the result you need",
        ):
            self.assertNotIn(removed, html)

    def test_mobile_categories_have_single_expandable_menu_not_repeated_nav_rows(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Mobile shopping categories")
        self.assertContains(response, "Shop categories")
        self.assertContains(response, "More categories and filters")
