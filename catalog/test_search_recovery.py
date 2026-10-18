"""Public search recovery: preserve original query and existing filters."""
from django.test import TestCase, override_settings
from django.urls import reverse
from catalog.models import Category, Product


@override_settings(SECURE_SSL_REDIRECT=False)
class SearchRecoveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        computers = Category.objects.create(name="Computers", slug="recovery-computers")
        networking = Category.objects.create(name="Networking", slug="recovery-networking")
        cls.laptop = Product.objects.create(
            category=computers, name="Lenovo ThinkPad Laptop",
            slug="recovery-lenovo-laptop", price=750000,
            stock_quantity=2, is_published=True,
        )
        Product.objects.create(
            category=networking, name="Ubiquiti Router",
            slug="recovery-router", price=280000,
            stock_quantity=2, is_published=True,
        )
        Product.objects.create(
            category=computers, name="Unpublished Printer",
            slug="recovery-printer", price=250000,
            stock_quantity=2, is_published=False,
        )

    def test_typo_hint_preserves_search_and_click_produces_results(self):
        response = self.client.get(reverse("product_list"), {"q": "Laptpo"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["paginator"].count, 0)
        suggestion = response.context["search_correction"]
        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion["query"].casefold(), "laptop")
        self.assertContains(response, "Did you mean")
        self.assertContains(response, "No matching items found")
        clicked = self.client.get(suggestion["url"])
        self.assertEqual(clicked.context["paginator"].count, 1)
        self.assertEqual(clicked.context["products"][0].pk, self.laptop.pk)

    def test_correction_respects_category_filters(self):
        response = self.client.get(
            reverse("product_list"),
            {"q": "Laptpo", "category": "recovery-computers"},
        )
        self.assertIn("category=recovery-computers",
                      response.context["search_correction"]["url"])
        wrong = self.client.get(
            reverse("product_list"),
            {"q": "Laptpo", "category": "recovery-networking"},
        )
        self.assertIsNone(wrong.context["search_correction"])

    def test_exact_and_unpublished_or_unrelated_searches_have_no_hint(self):
        exact = self.client.get(reverse("product_list"), {"q": "Laptop"})
        self.assertIsNone(exact.context["search_correction"])
        for term in ("Prniter", "zzzzzzz"):
            result = self.client.get(reverse("product_list"), {"q": term})
            self.assertIsNone(result.context["search_correction"])
