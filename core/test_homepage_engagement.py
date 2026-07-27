from pathlib import Path

from django.test import TestCase
from django.urls import reverse


class HomepageEngagementJourneyTests(TestCase):
    def test_homepage_renders_guided_discovery_journey(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="homepage-discovery"')
        self.assertContains(response, "Explore below")
        self.assertContains(response, "Start with the result you need")
        self.assertContains(response, "Find a computer or accessory")
        self.assertContains(response, "See laptop prices and options")
        self.assertContains(response, "Get technical support")
        self.assertContains(response, "Plan documented procurement")
        self.assertContains(response, "Keep exploring with a clearer path")
        self.assertContains(response, "Questions worth exploring")
        self.assertContains(response, "css/home_engagement.css")

    def test_homepage_journey_links_to_real_public_routes(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, reverse("physical_product_list"))
        self.assertContains(response, reverse("service_list"))
        self.assertContains(response, reverse("buying_guide_list"))
        self.assertContains(
            response,
            reverse(
                "buying_guide_detail",
                args=["how-to-choose-a-laptop-in-uganda"],
            ),
        )
        self.assertContains(
            response,
            reverse(
                "buying_guide_detail",
                args=["8gb-vs-16gb-ram-laptop-guide"],
            ),
        )
        self.assertContains(
            response,
            reverse(
                "buying_guide_detail",
                args=["ssd-vs-hdd-storage-guide"],
            ),
        )

    def test_engagement_styles_preserve_responsive_and_reduced_motion_behavior(self):
        stylesheet = Path("static/css/home_engagement.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("prefers-reduced-motion: reduce", stylesheet)
        self.assertIn("@media (max-width: 767.98px)", stylesheet)
        self.assertIn("scroll-behavior: smooth", stylesheet)
        self.assertIn("home-scroll-dot", stylesheet)
        self.assertIn("home-pathway-card", stylesheet)
        self.assertIn("home-confidence-story", stylesheet)
        self.assertNotIn("position: fixed", stylesheet)
