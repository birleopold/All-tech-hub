"""The actual LEOSOFT lion is discoverable by browsers and Google."""
import json
from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image


@override_settings(SECURE_SSL_REDIRECT=False)
class LeosoftFaviconTests(TestCase):
    def test_brand_icon_exists_and_is_valid_google_eligible_png(self):
        path = Path("static/icons/leosoft-lion.png")
        self.assertTrue(path.is_file())
        with Image.open(path) as icon:
            self.assertEqual(icon.format, "PNG")
            self.assertEqual(icon.width, icon.height)
            self.assertGreaterEqual(icon.width, 48)

    def test_homepage_declares_icon_and_apple_touch(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'rel="icon" type="image/png"')
        self.assertContains(response, 'rel="apple-touch-icon"')
        self.assertContains(response, 'rel="shortcut icon"')
        self.assertContains(response, 'leosoft-lion')

    def test_root_favicon_path_redirects_to_crawlable_static_icon(self):
        response = self.client.get(reverse("site_favicon"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("leosoft-lion", response["Location"])
        self.assertIn("public", response["Cache-Control"])
        robots = self.client.get(reverse("robots_txt")).content.decode()
        self.assertNotIn("Disallow: /static/", robots)
        self.assertNotIn("Disallow: /favicon.ico", robots)

    def test_pwa_manifest_uses_real_brand_symbol(self):
        manifest = json.loads(Path("static/site.webmanifest").read_text(encoding="utf-8"))
        self.assertTrue(any(
            "leosoft-lion.png" in icon["src"] and icon["type"] == "image/png"
            for icon in manifest["icons"]
        ))
        self.assertFalse(any("alltech-icon.svg" in icon["src"] for icon in manifest["icons"]))
