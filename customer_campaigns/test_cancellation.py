from django.contrib.auth import get_user_model
from django.test import TestCase

from crm.models import Customer
from customer_campaigns.models import CustomerCampaign, CustomerCampaignRecipient
from customer_campaigns.services import CampaignOperationError, cancel_campaign


class CustomerCampaignCancellationTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="campaign-canceller",
            password="strong-test-password",
            is_staff=True,
        )
        self.customer = Customer.objects.create(
            name="Cancellation Customer",
            email="cancel@example.com",
        )
        self.campaign = CustomerCampaign.objects.create(
            name="Cancellation safety test",
            topic=CustomerCampaign.TOPIC_PRODUCT_UPDATES,
            segment=CustomerCampaign.SEGMENT_ALL,
            subject="Test",
            body="Test body",
            max_recipients=1,
            status=CustomerCampaign.STATUS_SENDING,
            created_by=self.staff,
        )
        self.recipient = CustomerCampaignRecipient.objects.create(
            campaign=self.campaign,
            customer=self.customer,
            email_address=self.customer.email,
            status=CustomerCampaignRecipient.STATUS_PROCESSING,
        )
        self.campaign.prepared_count = 1
        self.campaign.save(update_fields=["prepared_count", "updated_at"])

    def test_processing_recipient_blocks_campaign_cancellation(self):
        with self.assertRaisesMessage(
            CampaignOperationError,
            "currently processing",
        ):
            cancel_campaign(self.campaign, user=self.staff)
        self.campaign.refresh_from_db()
        self.recipient.refresh_from_db()
        self.assertEqual(self.campaign.status, CustomerCampaign.STATUS_SENDING)
        self.assertEqual(
            self.recipient.status,
            CustomerCampaignRecipient.STATUS_PROCESSING,
        )

    def test_pending_recipient_is_suppressed_when_campaign_is_cancelled(self):
        self.recipient.status = CustomerCampaignRecipient.STATUS_PENDING
        self.recipient.save(update_fields=["status", "updated_at"])
        result = cancel_campaign(self.campaign, user=self.staff)
        self.recipient.refresh_from_db()
        self.assertEqual(result.status, CustomerCampaign.STATUS_CANCELLED)
        self.assertEqual(
            self.recipient.status,
            CustomerCampaignRecipient.STATUS_SUPPRESSED,
        )
        self.assertEqual(self.recipient.suppression_reason, "campaign_cancelled")
