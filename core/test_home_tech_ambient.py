from pathlib import Path

from django.test import TestCase
from django.urls import reverse


class HomeTechnologyAmbientTests(TestCase):
    def test_homepage_renders_decorative_server_rack_scene(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="home-tech-ambient"')
        self.assertContains(response, 'class="home-tech-ambient__rack"')
        self.assertContains(response, 'class="home-tech-ambient__led')
        self.assertContains(response, "css/home_tech_ambient.css")
        self.assertContains(response, 'aria-hidden="true"')

    def test_ambient_asset_remains_lightweight_and_accessible(self):
        stylesheet = Path("static/css/home_tech_ambient.css").read_text(
            encoding="utf-8"
        )
        illustration = Path("templates/core/_home_tech_ambient.html").read_text(
            encoding="utf-8"
        )

        self.assertIn("prefers-reduced-motion: reduce", stylesheet)
        self.assertIn("pointer-events: none", stylesheet)
        self.assertIn("@media (max-width: 767.98px)", stylesheet)
        self.assertIn("home-tech-led-blink", stylesheet)
        self.assertIn("home-tech-data-flow", stylesheet)
        self.assertIn("<animateMotion", illustration)
        self.assertIn('aria-hidden="true"', illustration)
        self.assertNotIn("<script", illustration)
        self.assertNotIn("<video", illustration)
