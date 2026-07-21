from unittest.mock import patch

from django.db import DatabaseError
from django.templatetags.static import static
from django.test import TestCase
from django.urls import reverse


class OperationalFoundationTests(TestCase):
    def test_health_endpoint_reports_database_readiness_without_cache(self):
        response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"], "ok")
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")

    @patch("core.health.connection.cursor", side_effect=DatabaseError("database unavailable"))
    def test_health_endpoint_returns_service_unavailable_when_database_is_down(self, _cursor):
        response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "degraded")
        self.assertEqual(response.json()["database"], "error")
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_public_layout_loads_foundation_styles_and_accessible_mobile_navigation(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, static("css/foundation.css"))
        self.assertContains(response, 'class="mobile-scroll-footer')
        self.assertContains(response, 'aria-label="Secondary mobile navigation"')
        self.assertContains(response, ">Customer sign in</a>")
        self.assertNotContains(response, 'style="position: static !important')

    def test_service_worker_precaches_current_public_foundation_assets(self):
        response = self.client.get(reverse("service_worker"))
        body = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('const CACHE_NAME = "leosoft-public-assets-v3"', body)
        self.assertIn(static("css/foundation.css"), body)
        self.assertIn(static("js/alltech_ui.js"), body)
        self.assertNotIn("/media/", body)
        self.assertIn("no-store", response.headers["Cache-Control"])
