from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product


class CatalogueQualityPageRegressionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Catalogue quality regression",
            slug="catalogue-quality-regression",
        )
        cls.product = Product.objects.create(
            category=cls.category,
            name="Catalogue quality test product",
            slug="catalogue-quality-test-product",
            price=Decimal("100000"),
            is_published=True,
        )
        cls.staff = get_user_model().objects.create_user(
            username="catalogue-quality-regression-staff",
            password="test-password-123",
            is_staff=True,
        )

    def test_page_renders_product_actions_without_missing_url_names(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("staff_catalogue_quality"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)
        self.assertContains(
            response,
            reverse("staff_product_edit", args=[self.product.pk]),
        )
        self.assertContains(response, "Review listing")
