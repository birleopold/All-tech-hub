from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class ReportAccessTests(TestCase):
    def test_export_requires_staff(self):
        response = self.client.get(reverse("staff_export_orders_csv"))
        self.assertEqual(response.status_code, 404)

    def test_staff_export_is_csv(self):
        user = User.objects.create_user("reporter", password="pw", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse("staff_export_orders_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))

    def test_report_contains_fulfillment_summary(self):
        user = User.objects.create_user("analyst", password="pw", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse("staff_reports"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("fulfillment_counts", response.context)
