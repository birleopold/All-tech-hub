"""End-to-end screen checks for staff catalogue triage and public pagination."""
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

from django.test import Client

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product


@override_settings(SECURE_SSL_REDIRECT=False)
class StaffCatalogueTriageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(
            name="Test Computers", slug="triage-computers",
            description="Computers for work, home and learning."
        )
        cls.product = Product.objects.create(
            category=category,
            name="Needs-image laptop",
            slug="triage-needs-image",
            price=Decimal("500000.00"),
            short_description="Detailed short description for a sample laptop.",
            description="A complete description of the sample test laptop. " * 5,
            stock_quantity=4, is_published=True,
        )
        cls.user = get_user_model().objects.create_user(
            username="triage-admin", password="pass", is_staff=True, is_superuser=True
        )

    def test_staff_can_filter_on_issue_from_existing_quality_calculator(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("staff_catalogue_quality"), {"issue": "image_missing"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_issue"], "image_missing")
        self.assertEqual(response.context["filtered_quality_count"], 1)
        self.assertContains(response, "Needs-image laptop")
        self.assertContains(response, 'name="issue"')
        self.assertContains(response, "Show listings with No customer-visible image")

    def test_staff_filters_issues_after_publication_and_search(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("staff_catalogue_quality"),
            {"issue": "image_missing", "q": "no such product", "published": "1"}
        )
        self.assertEqual(response.context["filtered_quality_count"], 0)
        self.assertContains(response, "No products match these filters.")
        self.assertContains(response, 'value="image_missing" selected')

    def test_unknown_issue_is_ignored_and_anonymous_is_denied(self):
        response = self.client.get(reverse("staff_catalogue_quality"))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("staff_catalogue_quality"), {"issue": "untrusted-bogus"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_issue"], "")
        self.assertEqual(response.context["filtered_quality_count"], 1)


@override_settings(SECURE_SSL_REDIRECT=False)
class CataloguePaginationAndAvailabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(
            name="Accessories", slug="paginated-accessories"
        )
        for i in range(42):
            Product.objects.create(
                category=category, name=f"Paging Test Product {i:02d}",
                slug=f"paging-test-{i:02d}", price=Decimal("25000.00")+i,
                is_published=True, stock_quantity=2
            )
        cls.unavailable = Product.objects.create(
            category=category, name="Paging Test Unavailable",
            slug="paging-test-unavailable", price=Decimal("24000.00"),
            stock_quantity=0, is_published=True
        )

    def test_generic_category_filters_survive_numbered_pagination(self):
        response = self.client.get(
            reverse("product_list"), {"category": "paginated-accessories"}
        )
        self.assertEqual(response.status_code, 200)
        suffix = parse_qs(response.context["catalog_pagination_suffix"])
        self.assertEqual(suffix["category"], ["paginated-accessories"])
        seed = response.context["rotation_seed"]
        self.assertEqual(suffix["view"], [seed])
        self.assertNotIn("view=", response.context["catalog_canonical_url"])

        # A customer opening page two in a fresh browser sees the same
        # deterministic product ordering as the original page one.
        next_page = Client().get(
            reverse("product_list"),
            {"category": "paginated-accessories", "view": seed, "page": 2},
        )
        self.assertEqual(next_page.status_code, 200)
        self.assertEqual(next_page.context["rotation_seed"], seed)
        first_ids = {p.pk for p in response.context["products"]}
        second_ids = {p.pk for p in next_page.context["products"]}
        self.assertFalse(first_ids.intersection(second_ids))

    def test_routed_landing_filters_switch_to_generic_catalogue(self):
        category = Category.objects.create(
            name="Office", slug="paginated-office"
        )
        office = Product.objects.create(
            category=category, name="Office scanner",
            slug="paginated-office-scanner", price=Decimal("200000"),
            is_published=True, stock_quantity=2,
        )
        response = self.client.get(
            reverse("product_category", args=["paginated-accessories"])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, f'action="{reverse("product_list")}"'
        )
        # Changing the dropdown must not be overwritten by the category URL.
        new_category = self.client.get(
            reverse("product_list"),
            {"category": "paginated-office"},
        )
        self.assertEqual(new_category.status_code, 200)
        self.assertEqual(new_category.context["paginator"].count, 1)
        self.assertEqual(new_category.context["products"][0].pk, office.pk)

    def test_active_filter_removal_reaches_generic_catalogue(self):
        response = self.client.get(
            reverse("product_category", args=["paginated-accessories"]),
            {"sort": "name", "q": "Paging"},
        )
        self.assertEqual(response.status_code, 200)
        category_filter = next(
            item for item in response.context["active_filter_items"]
            if item["label"] == "Accessories"
        )
        remove_url = urlsplit(category_filter["remove_url"])
        self.assertEqual(remove_url.path, reverse("product_list"))
        self.assertNotIn("category", parse_qs(remove_url.query))
        self.assertEqual(parse_qs(remove_url.query)["q"], ["Paging"])

    def test_numbered_pagination_keeps_search_and_sort(self):
        params = {"q": "Paging Test", "sort": "name"}
        response = self.client.get(reverse("product_list"), params)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["is_paginated"])
        self.assertContains(response, 'aria-label="Go to page 2"')
        self.assertContains(response, 'aria-current="page"')
        self.assertContains(response, "sort=name")
        self.assertContains(response, "q=Paging")
        response = self.client.get(
            reverse("product_list"), {**params, "page": 2}
        )
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertContains(response, 'aria-label="Go to page 1"')

    def test_filter_controls_have_labels_and_empty_results_offer_recovery(self):
        response = self.client.get(
            reverse("product_list"), {"q": "no products with this unlikely exact phrase"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="mobile-market-kind"')
        self.assertContains(response, 'id="desktop-market-kind"')
        self.assertContains(response, 'aria-controls="mobile-market-filter-panel"')
        self.assertContains(response, "No matching items found")
        self.assertContains(response, "Clear filters")
        self.assertContains(response, "Ask the team")

    def test_product_cards_show_availability_honestly(self):
        response = self.client.get(
            reverse("product_list"), {"q": "Paging Test Unavailable"}
        )
        self.assertContains(response, "Check availability")
        response = self.client.get(
            reverse("product_list"), {"q": "Paging Test Product", "sort": "name"}
        )
        self.assertContains(response, "Available to order")
