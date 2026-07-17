from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from crm.models import Customer
from customer_campaigns.forms import CampaignSendForm
from customer_campaigns.models import CustomerCampaign, CustomerCampaignRecipient
from customer_campaigns.reporting import campaign_integrity_findings
from customer_campaigns.services import (
    CampaignOperationError,
    approve_campaign,
    prepare_campaign,
    send_campaign_batch,
)
from loyalty.models import CustomerMarketingPreference
from loyalty.services import update_marketing_preference, withdraw_all_marketing
from messaging.models import OutboundEmail


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="hello@leosoftug.com",
    PUBLIC_BASE_URL="https://leosoftug.com",
    CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=100,
    CUSTOMER_CAMPAIGN_BATCH_SIZE=2,
    CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER=True,
)
class ControlledCustomerCampaignTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.creator = user_model.objects.create_user(
            username="campaign-creator",
            password="strong-test-password",
            is_staff=True,
        )
        self.approver = user_model.objects.create_user(
            username="campaign-approver",
            password="strong-test-password",
            is_staff=True,
        )
        self.customer = Customer.objects.create(
            name="Amina Customer",
            email="amina@example.com",
            phone="+256700000010",
        )
        update_marketing_preference(
            self.customer,
            email_marketing=True,
            whatsapp_marketing=False,
            product_updates=True,
            special_offers=False,
            source=CustomerMarketingPreference.SOURCE_PORTAL,
        )
        self.campaign = CustomerCampaign.objects.create(
            name="July product update",
            topic=CustomerCampaign.TOPIC_PRODUCT_UPDATES,
            segment=CustomerCampaign.SEGMENT_ALL,
            subject="Hello {first_name} — new from {company}",
            body=(
                "Hello {customer_name},\n\nSee our latest products.\n\n"
                "Unsubscribe: {unsubscribe_url}"
            ),
            max_recipients=20,
            created_by=self.creator,
        )

    def _create_consented_customer(self, number: int) -> Customer:
        customer = Customer.objects.create(
            name=f"Customer {number}",
            email=f"customer{number}@example.com",
            phone=f"+256700000{number:03d}",
        )
        update_marketing_preference(
            customer,
            email_marketing=True,
            whatsapp_marketing=False,
            product_updates=True,
            special_offers=False,
            source=CustomerMarketingPreference.SOURCE_PORTAL,
        )
        return customer

    def test_preparation_requires_matching_channel_topic_and_event(self):
        offer_customer = Customer.objects.create(
            name="Offer Customer",
            email="offers@example.com",
        )
        update_marketing_preference(
            offer_customer,
            email_marketing=True,
            whatsapp_marketing=False,
            product_updates=False,
            special_offers=True,
            source=CustomerMarketingPreference.SOURCE_PORTAL,
        )
        Customer.objects.create(
            name="No Consent Customer",
            email="no-consent@example.com",
        )
        manual_customer = Customer.objects.create(
            name="Active Flag Without Event",
            email="no-event@example.com",
        )
        CustomerMarketingPreference.objects.create(
            customer=manual_customer,
            email_marketing=True,
            product_updates=True,
        )

        prepared = prepare_campaign(self.campaign, user=self.creator)
        recipients = list(prepared.recipients.select_related("customer", "consent_event"))
        self.assertEqual(prepared.status, CustomerCampaign.STATUS_PREPARED)
        self.assertEqual(len(recipients), 1)
        self.assertEqual(recipients[0].customer, self.customer)
        self.assertIsNotNone(recipients[0].consent_event)

    def test_creator_or_preparer_cannot_approve(self):
        prepare_campaign(self.campaign, user=self.creator)
        with self.assertRaisesMessage(
            CampaignOperationError,
            "different authorised staff member",
        ):
            approve_campaign(self.campaign, user=self.creator)

    @override_settings(CUSTOMER_CAMPAIGN_SEND_ENABLED=False)
    def test_master_switch_blocks_delivery(self):
        prepare_campaign(self.campaign, user=self.creator)
        approve_campaign(self.campaign, user=self.approver)
        with self.assertRaisesMessage(CampaignOperationError, "safety switch"):
            send_campaign_batch(self.campaign, user=self.creator)
        self.assertEqual(OutboundEmail.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(CUSTOMER_CAMPAIGN_SEND_ENABLED=True)
    def test_approved_campaign_sends_with_unsubscribe_and_evidence(self):
        prepare_campaign(self.campaign, user=self.creator)
        approve_campaign(
            self.campaign,
            user=self.approver,
            approval_note="Audience and message checked.",
        )
        result = send_campaign_batch(self.campaign, user=self.creator)
        recipient = CustomerCampaignRecipient.objects.get(campaign=self.campaign)
        log = recipient.outbound_email

        self.assertEqual(result.status, CustomerCampaign.STATUS_COMPLETED)
        self.assertEqual(recipient.status, CustomerCampaignRecipient.STATUS_SENT)
        self.assertEqual(log.status, OutboundEmail.STATUS_SENT)
        self.assertIn("/preferences/unsubscribe/", log.body)
        self.assertIn("Amina", log.subject)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(campaign_integrity_findings()["errors"], 0)

    @override_settings(CUSTOMER_CAMPAIGN_SEND_ENABLED=True)
    def test_withdrawal_after_preparation_suppresses_before_send(self):
        prepare_campaign(self.campaign, user=self.creator)
        approve_campaign(self.campaign, user=self.approver)
        preference = self.customer.marketing_preference
        withdraw_all_marketing(preference)

        result = send_campaign_batch(self.campaign, user=self.creator)
        recipient = CustomerCampaignRecipient.objects.get(campaign=self.campaign)
        self.assertEqual(result.status, CustomerCampaign.STATUS_COMPLETED)
        self.assertEqual(
            recipient.status,
            CustomerCampaignRecipient.STATUS_SUPPRESSED,
        )
        self.assertEqual(recipient.suppression_reason, "email_consent_withdrawn")
        self.assertEqual(OutboundEmail.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(CUSTOMER_CAMPAIGN_SEND_ENABLED=True)
    def test_email_change_after_preparation_requires_reprepare(self):
        prepare_campaign(self.campaign, user=self.creator)
        approve_campaign(self.campaign, user=self.approver)
        self.customer.email = "changed@example.com"
        self.customer.save(update_fields=["email"])

        send_campaign_batch(self.campaign, user=self.creator)
        recipient = CustomerCampaignRecipient.objects.get(campaign=self.campaign)
        self.assertEqual(
            recipient.suppression_reason,
            "email_changed_reprepare_required",
        )
        self.assertEqual(OutboundEmail.objects.count(), 0)

    @override_settings(CUSTOMER_CAMPAIGN_SEND_ENABLED=True)
    def test_batches_never_exceed_configured_limit(self):
        self._create_consented_customer(11)
        self._create_consented_customer(12)
        prepare_campaign(self.campaign, user=self.creator)
        approve_campaign(self.campaign, user=self.approver)

        first = send_campaign_batch(
            self.campaign,
            user=self.creator,
            batch_size=99,
        )
        self.assertEqual(first.sent_count, 2)
        self.assertEqual(first.status, CustomerCampaign.STATUS_SENDING)

        second = send_campaign_batch(
            self.campaign,
            user=self.creator,
            batch_size=99,
        )
        self.assertEqual(second.sent_count, 3)
        self.assertEqual(second.status, CustomerCampaign.STATUS_COMPLETED)
        self.assertEqual(len(mail.outbox), 3)

    @override_settings(CUSTOMER_CAMPAIGN_SEND_ENABLED=True)
    def test_uncertain_queued_delivery_is_not_automatically_resent(self):
        prepare_campaign(self.campaign, user=self.creator)
        approve_campaign(self.campaign, user=self.approver)
        recipient = self.campaign.recipients.get()
        log = OutboundEmail.objects.create(
            to_email=recipient.email_address,
            subject="Queued but uncertain",
            body="Delivery state is uncertain",
            status=OutboundEmail.STATUS_QUEUED,
            created_by=self.creator,
        )
        recipient.status = CustomerCampaignRecipient.STATUS_PROCESSING
        recipient.outbound_email = log
        recipient.attempted_at = timezone.now() - timedelta(hours=1)
        recipient.save(
            update_fields=[
                "status",
                "outbound_email",
                "attempted_at",
                "updated_at",
            ]
        )

        result = send_campaign_batch(self.campaign, user=self.creator)
        recipient.refresh_from_db()
        self.assertEqual(result.status, CustomerCampaign.STATUS_SENDING)
        self.assertEqual(recipient.status, CustomerCampaignRecipient.STATUS_PROCESSING)
        self.assertEqual(OutboundEmail.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 0)

    def test_generic_email_log_retry_is_blocked_for_campaign_delivery(self):
        prepare_campaign(self.campaign, user=self.creator)
        recipient = self.campaign.recipients.get()
        log = OutboundEmail.objects.create(
            to_email=recipient.email_address,
            subject="Failed campaign email",
            body="Contains an unsubscribe link /preferences/unsubscribe/example/",
            status=OutboundEmail.STATUS_FAILED,
            error="Test failure",
            created_by=self.creator,
        )
        recipient.status = CustomerCampaignRecipient.STATUS_FAILED
        recipient.outbound_email = log
        recipient.save(update_fields=["status", "outbound_email", "updated_at"])

        self.client.force_login(self.creator)
        response = self.client.post(
            reverse("staff_email_log_retry", kwargs={"pk": log.pk})
        )
        self.assertRedirects(
            response,
            reverse(
                "staff_customer_campaign_detail",
                kwargs={"pk": self.campaign.pk},
            ),
        )
        log.refresh_from_db()
        self.assertEqual(log.status, OutboundEmail.STATUS_FAILED)
        self.assertEqual(len(mail.outbox), 0)

    def test_send_form_requires_exact_confirmation_phrase(self):
        form = CampaignSendForm(
            {"confirmation": "SEND WRONG", "batch_size": 1},
            campaign=self.campaign,
        )
        self.assertFalse(form.is_valid())
        valid = CampaignSendForm(
            {"confirmation": f"SEND {self.campaign.pk}", "batch_size": 1},
            campaign=self.campaign,
        )
        self.assertTrue(valid.is_valid(), valid.errors)

    def test_staff_pages_are_private(self):
        self.client.force_login(self.creator)
        response = self.client.get(reverse("staff_customer_campaigns"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        self.assertIn("noindex", response.headers["X-Robots-Tag"])

    def test_integrity_audit_detects_sent_email_without_unsubscribe(self):
        prepare_campaign(self.campaign, user=self.creator)
        recipient = self.campaign.recipients.get()
        log = OutboundEmail.objects.create(
            to_email=recipient.email_address,
            subject="Unsafe test",
            body="No preference link",
            status=OutboundEmail.STATUS_SENT,
            created_by=self.creator,
        )
        recipient.status = CustomerCampaignRecipient.STATUS_SENT
        recipient.outbound_email = log
        recipient.save(update_fields=["status", "outbound_email", "updated_at"])
        self.campaign.sent_count = 1
        self.campaign.save(update_fields=["sent_count", "updated_at"])

        findings = campaign_integrity_findings()
        self.assertEqual(findings["sent_without_unsubscribe"], 1)
        self.assertGreater(findings["errors"], 0)
