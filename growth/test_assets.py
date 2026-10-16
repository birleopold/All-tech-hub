from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Category, Product
from core.models import CompanySettings


class GrowthContentImageTests(TestCase):
    def setUp(self):
        company = CompanySettings.load()
        company.company_name = "LEOSOFT"
        company.legal_name = "LEOSOFT UG LTD"
        company.website = "https://leosoftug.com"
        company.save()
        category = Category.objects.create(
            name="Image cards",
            slug="growth-image-cards",
        )
        self.product = Product.objects.create(
            category=category,
            name="Marketing Image Laptop",
            slug="marketing-image-laptop",
            price=Decimal("2500000"),
            stock_quantity=2,
            is_published=True,
        )
        self.user = get_user_model().objects.create_superuser(
            username="asset-admin",
            email="asset@example.com",
            password="TestPass123!",
        )

    def test_square_and_story_cards_are_valid_png_downloads(self):
        self.client.force_login(self.user)
        for format_name in ("square", "story"):
            response = self.client.get(
                reverse(
                    "staff_growth_content_image",
                    args=[self.product.pk, format_name],
                )
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/png")
            self.assertTrue(response.content.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertGreater(len(response.content), 5000)

    def test_anonymous_download_is_redirected_to_sign_in(self):
        response = self.client.get(
            reverse("staff_growth_content_image", args=[self.product.pk, "square"])
        )
        self.assertEqual(response.status_code, 302)

    def test_unpublished_products_are_not_exportable(self):
        self.product.is_published = False
        self.product.save(update_fields=["is_published"])
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("staff_growth_content_image", args=[self.product.pk, "square"])
        )
        self.assertEqual(response.status_code, 404)

    def test_unknown_image_format_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse(
                "staff_growth_content_image",
                args=[self.product.pk, "unknown"],
            )
        )
        self.assertEqual(response.status_code, 404)
