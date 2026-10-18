"""Read-only notification volume report."""
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from core.models import StaffNotification


class NotificationNoiseReportTests(TestCase):
    def test_report_does_not_modify_notifications(self):
        user = get_user_model().objects.create_user(
            username="notification-noise-report", password="local-test", is_staff=True
        )
        StaffNotification.objects.create(recipient=user, message="Repeated warning")
        StaffNotification.objects.create(recipient=user, message="Repeated warning")
        output = StringIO()
        call_command("report_notification_noise", days=30, limit=10, stdout=output)
        self.assertIn("total=2", output.getvalue())
        self.assertIn("Repeated warning", output.getvalue())
        self.assertEqual(StaffNotification.objects.filter(is_read=False).count(), 2)
