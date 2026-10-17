from decimal import Decimal

from django.test import TestCase

from catalog.models import Category, Product
from marketing.models import SocialProfileSettings


class SocialMarketingTests(TestCase):
    def setUp(self):
        category = Category.objects.create(
            name="Marketing test category",
            slug="marketing-test-category",
        )
        self.product = Product.objects.create(
            category=category,
            name="Shareable Laptop",
            slug="shareable-laptop",
            short_description="A dependable laptop for business and study.",
            price=Decimal("2500000"),
            stock_quantity=3,
            is_published=True,
        )

    def test_product_page_has_rich_social_metadata_and_share_controls(self):
        response = self.client.get(self.product.get_absolute_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'property="og:title"')
        self.assertContains(response, 'name="twitter:card"')
        self.assertContains(response, "Send this item to someone")
        self.assertContains(response, "WhatsApp")
        self.assertContains(response, "Facebook")
        self.assertContains(response, "LinkedIn")
        self.assertContains(response, "Copy")
        self.assertContains(response, "utm_campaign")

    def test_sitemap_lists_published_product(self):
        index = self.client.get("/sitemap.xml")
        response = self.client.get("/sitemaps/products.xml")

        self.assertEqual(index.status_code, 200)
        self.assertContains(index, "/sitemaps/products.xml")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.get_absolute_url())

    def test_robots_points_to_sitemap_and_blocks_private_areas(self):
        response = self.client.get("/robots.txt")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/sitemap.xml")
        self.assertContains(response, "Disallow: /admin/")
        self.assertContains(response, "Disallow: /staff/")

    def test_social_profile_settings_build_whatsapp_link(self):
        settings = SocialProfileSettings.load()
        settings.whatsapp_number = "+256 700 123 456"
        settings.save()

        self.assertEqual(settings.whatsapp_url, "https://wa.me/256700123456")
