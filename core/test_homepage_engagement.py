"""Guides and education stay on dedicated pages; homepage sells clearly."""
from pathlib import Path

from django.test import TestCase
from django.urls import reverse


class HomepageEngagementJourneyTests(TestCase):
    def test_homepage_keeps_products_services_and_trust_visible(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Explore the catalogue")
        self.assertContains(response, "Shop our products")
        self.assertContains(response, "Shop with confidence")
        self.assertContains(response, reverse("physical_product_list"))
        self.assertContains(response, reverse("service_list"))
        self.assertContains(response, reverse("buying_guide_list"))
        self.assertNotContains(response, "Questions worth exploring")
        self.assertNotContains(response, "Keep exploring with a clearer path")
        self.assertNotContains(response, "Start with the result you need")

    def test_dedicated_guide_routes_remain_available(self):
        self.assertTrue(reverse("buying_guide_list"))
        self.assertTrue(reverse(
            "buying_guide_detail", args=["how-to-choose-a-laptop-in-uganda"]
        ))

    def test_homepage_ambient_respects_reduced_motion(self):
        stylesheet = Path("static/css/home_tech_ambient.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("prefers-reduced-motion: reduce", stylesheet)
        self.assertIn("@media (max-width: 767.98px)", stylesheet)
