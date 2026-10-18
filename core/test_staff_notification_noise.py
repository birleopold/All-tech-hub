"""Regression tests for repeated staff notification delivery."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from core.models import StaffNotification
from core.notifications import staff_notify


class StaffNotificationNoiseTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="staff-notification-retry", password="test-only", is_staff=True
        )

    def test_immediate_identical_retry_reuses_unread_notice(self):
        first = staff_notify(self.user, "Repair #123 requires attention", "/staff/jobs/123/")
        second = staff_notify(self.user, "Repair #123 requires attention", "/staff/jobs/123/")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(StaffNotification.objects.filter(recipient=self.user).count(), 1)

    def test_different_destination_does_not_disappear(self):
        staff_notify(self.user, "Repair requires attention", "/staff/jobs/123/")
        staff_notify(self.user, "Repair requires attention", "/staff/jobs/456/")
        self.assertEqual(StaffNotification.objects.filter(recipient=self.user).count(), 2)

    def test_read_alert_allows_fresh_notice(self):
        first = staff_notify(self.user, "Invoice needs review", "/staff/documents/")
        first.is_read = True
        first.save(update_fields=["is_read"])
        second = staff_notify(self.user, "Invoice needs review", "/staff/documents/")
        self.assertNotEqual(first.pk, second.pk)
