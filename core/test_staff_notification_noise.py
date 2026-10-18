"""Regression tests for repeated staff notification delivery."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
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

    def test_staff_inbox_filters_read_and_unread(self):
        unread = staff_notify(self.user, "Urgent new assignment", "/staff/jobs/")
        read = staff_notify(self.user, "Previously handled", "/staff/jobs/")
        read.is_read = True
        read.save(update_fields=["is_read"])
        self.client.force_login(self.user)
        url = reverse("staff_notifications")
        result = self.client.get(url, {"show": "unread"})
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, "Urgent new assignment")
        self.assertNotContains(result, "Previously handled")
        result = self.client.get(url, {"show": "read"})
        self.assertContains(result, "Previously handled")
        self.assertNotContains(result, "Urgent new assignment")

    def test_cleanup_changes_only_old_alerts_for_logged_in_user(self):
        from datetime import timedelta
        from core.models import StaffNotification
        other = get_user_model().objects.create_user(
            username="another-staff", password="test-only", is_staff=True
        )
        old = staff_notify(self.user, "Old action", "/staff/jobs/10/")
        fresh = staff_notify(self.user, "New action", "/staff/jobs/11/")
        another = staff_notify(other, "Old action", "/staff/jobs/10/")
        StaffNotification.objects.filter(pk__in=[old.pk, another.pk]).update(
            created_at=timezone.now() - timedelta(days=32)
        )
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("staff_notifications_acknowledge"),
            {"scope": "older_30_days"},
        )
        self.assertEqual(response.status_code, 302)
        old.refresh_from_db()
        fresh.refresh_from_db()
        another.refresh_from_db()
        self.assertTrue(old.is_read)
        self.assertFalse(fresh.is_read)
        self.assertFalse(another.is_read)

    def test_cleanup_rejects_unrecognized_scope(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("staff_notifications_acknowledge"), {"scope": "delete"})
        self.assertEqual(response.status_code, 403)
