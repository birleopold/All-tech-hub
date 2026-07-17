from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import StaffNotification
from customer_campaigns.models import CampaignAutomationEvent, CustomerCampaign


class ScheduledCampaignNotificationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.creator = user_model.objects.create_user(
            username="notification-creator",
            password="strong-test-password",
            is_staff=True,
        )
        self.approver = user_model.objects.create_user(
            username="notification-approver",
            password="strong-test-password",
            is_staff=True,
        )
        self.campaign = CustomerCampaign.objects.create(
            name="Notification campaign",
            topic=CustomerCampaign.TOPIC_PRODUCT_UPDATES,
            segment=CustomerCampaign.SEGMENT_ALL,
            subject="Notification test",
            body="Notification test body",
            created_by=self.creator,
            approved_by=self.approver,
        )

    def test_system_pause_notifies_responsible_staff(self):
        CampaignAutomationEvent.objects.create(
            campaign=self.campaign,
            action=CampaignAutomationEvent.ACTION_PAUSED,
            message="Delivery health control opened.",
        )
        self.assertEqual(StaffNotification.objects.count(), 2)
        self.assertTrue(
            StaffNotification.objects.filter(recipient=self.creator).exists()
        )
        self.assertTrue(
            StaffNotification.objects.filter(recipient=self.approver).exists()
        )

    def test_actor_is_not_notified_about_their_own_critical_action(self):
        CampaignAutomationEvent.objects.create(
            campaign=self.campaign,
            action=CampaignAutomationEvent.ACTION_EXPIRED,
            actor=self.creator,
            message="Approval expired.",
        )
        self.assertFalse(
            StaffNotification.objects.filter(recipient=self.creator).exists()
        )
        self.assertTrue(
            StaffNotification.objects.filter(recipient=self.approver).exists()
        )

    def test_noncritical_schedule_event_does_not_create_alert(self):
        CampaignAutomationEvent.objects.create(
            campaign=self.campaign,
            action=CampaignAutomationEvent.ACTION_SCHEDULED,
            actor=self.creator,
            message="Scheduled.",
        )
        self.assertEqual(StaffNotification.objects.count(), 0)
