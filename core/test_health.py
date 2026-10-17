from django.test import TestCase
from django.urls import reverse


class HealthCheckTests(TestCase):
    def test_health_check_reports_database_status(self):
        response = self.client.get(reverse("healthz"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["database"], "ok")
        self.assertIn("timestamp", response.json())
