from django.test import TestCase
from django.urls import reverse

from catalog.experience import COMPARE_SESSION_KEY, RECENT_SESSION_KEY
from catalog.models import Category, Product


class CatalogExperienceTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Computers", slug="computers")
        self.products = [
            Product.objects.create(
                category=self.category,
                name=f"Laptop {index}",
                slug=f"laptop-{index}",
                price=f"{1000000 + index * 100000}.00",
                stock_quantity=2,
            )
            for index in range(1, 6)
        ]
        self.service = Product.objects.create(
            category=self.category,
            kind=Product.KIND_SERVICE,
            name="Laptop repair",
            slug="laptop-repair",
            price="80000.00",
            track_inventory=False,
        )

    def test_compare_toggle_is_session_based_and_limited_to_four_products(self):
        for product in self.products[:4]:
            response = self.client.post(
                reverse("product_compare_toggle", args=[product.pk]),
                {"next": reverse("product_list")},
            )
            self.assertRedirects(response, reverse("product_list"))

        self.assertEqual(
            self.client.session[COMPARE_SESSION_KEY],
            [product.pk for product in self.products[:4]],
        )

        self.client.post(
            reverse("product_compare_toggle", args=[self.products[4].pk]),
            {"next": reverse("product_compare")},
        )
        self.assertEqual(len(self.client.session[COMPARE_SESSION_KEY]), 4)

        response = self.client.get(reverse("product_compare"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.products[0].name)
        self.assertNotContains(response, self.products[4].name)
        self.assertContains(response, 'name="robots" content="noindex,follow"')

    def test_services_cannot_enter_product_comparison(self):
        self.client.post(
            reverse("product_compare_toggle", args=[self.service.pk]),
            {"next": self.service.get_absolute_url()},
        )
        self.assertEqual(self.client.session.get(COMPARE_SESSION_KEY, []), [])

    def test_recent_products_keep_most_recent_order_and_exclude_current(self):
        self.client.get(self.products[0].get_absolute_url())
        response = self.client.get(self.products[1].get_absolute_url())

        self.assertEqual(
            self.client.session[RECENT_SESSION_KEY][:2],
            [self.products[1].pk, self.products[0].pk],
        )
        recent = response.context["recent_products"]
        self.assertEqual([product.pk for product in recent], [self.products[0].pk])

    def test_catalog_canonical_excludes_rotation_sort_and_search_parameters(self):
        response = self.client.get(
            reverse("product_list"),
            {
                "kind": "physical",
                "category": self.category.slug,
                "sort": "price_low",
                "q": "Laptop",
                "view": "temporary-seed",
            },
        )
        canonical = response.context["catalog_canonical_url"]
        self.assertIn("kind=physical", canonical)
        self.assertIn("category=computers", canonical)
        self.assertNotIn("sort=", canonical)
        self.assertNotIn("q=", canonical)
        self.assertNotIn("view=", canonical)
        self.assertTrue(response.context["catalog_noindex"])
        self.assertContains(response, 'name="robots" content="noindex,follow"')

    def test_clearing_comparison_removes_session_selection(self):
        session = self.client.session
        session[COMPARE_SESSION_KEY] = [self.products[0].pk]
        session.save()
        response = self.client.post(reverse("product_compare_clear"))
        self.assertRedirects(response, reverse("product_compare"))
        self.assertNotIn(COMPARE_SESSION_KEY, self.client.session)
