from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from customer_campaigns.models import CustomerCampaign
from customer_campaigns.reporting import campaign_integrity_findings


@override_settings(
    CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE=1,
    CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER=True,
)
class ScheduledCampaignAuditTests(TestCase):
    def test_incomplete_schedule_control_is_an_integrity_error(self):
        approver = get_user_model().objects.create_user(
            username="schedule-audit-approver",
            password="strong-test-password",
            is_staff=True,
        )
        campaign = CustomerCampaign.objects.create(
            name="Incomplete schedule evidence",
            topic=CustomerCampaign.TOPIC_PRODUCT_UPDATES,
            segment=CustomerCampaign.SEGMENT_ALL,
            subject="Audit test",
            body="Audit test body",
            status=CustomerCampaign.STATUS_SCHEDULED,
            automated_delivery=True,
            approved_by=approver,
            approved_at=timezone.now(),
            approval_expires_at=timezone.now() + timedelta(hours=12),
        )

        findings = campaign_integrity_findings()
        self.assertEqual(findings["scheduled_missing_control"], 1)
        self.assertGreater(findings["errors"], 0)
        self.assertEqual(campaign.automation_run_count, 0)
