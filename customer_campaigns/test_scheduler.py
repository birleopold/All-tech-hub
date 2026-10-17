from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from crm.models import Customer
from customer_campaigns.forms import CampaignScheduleForm
from customer_campaigns.models import (
    CampaignAutomationEvent,
    CustomerCampaign,
    CustomerCampaignRecipient,
)
from customer_campaigns.reporting import campaign_integrity_findings
from customer_campaigns.services import (
    CampaignOperationError,
    approve_campaign,
    pause_campaign,
    prepare_campaign,
    process_scheduled_campaigns,
    resume_campaign,
    schedule_campaign,
    send_campaign_batch,
)
from loyalty.models import CustomerMarketingPreference
from loyalty.services import update_marketing_preference, withdraw_all_marketing
from messaging.models import OutboundEmail


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="hello@leosoftug.com",
    PUBLIC_BASE_URL="https://leosoftug.com",
    CUSTOMER_CAMPAIGN_SEND_ENABLED=True,
    CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED=True,
    CUSTOMER_CAMPAIGN_REQUIRE_SEPARATE_APPROVER=True,
    CUSTOMER_CAMPAIGN_MAX_RECIPIENTS=20,
    CUSTOMER_CAMPAIGN_BATCH_SIZE=2,
    CUSTOMER_CAMPAIGN_APPROVAL_VALID_HOURS=48,
    CUSTOMER_CAMPAIGN_SCHEDULE_MAX_LEAD_HOURS=24,
    CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE=1,
    CUSTOMER_CAMPAIGN_AUTOMATION_INTERVAL_MINUTES=15,
    CUSTOMER_CAMPAIGN_FAILURE_MIN_ATTEMPTS=3,
    CUSTOMER_CAMPAIGN_FAILURE_RATE_PERCENT=50,
)
class ScheduledCampaignTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.creator = user_model.objects.create_user(
            username="schedule-creator",
            password="strong-test-password",
            is_staff=True,
        )
        self.approver = user_model.objects.create_user(
            username="schedule-approver",
            password="strong-test-password",
            is_staff=True,
        )
        self.customer = self._customer(1)
        self.campaign = CustomerCampaign.objects.create(
            name="Scheduled product update",
            topic=CustomerCampaign.TOPIC_PRODUCT_UPDATES,
            segment=CustomerCampaign.SEGMENT_ALL,
            subject="Hello {first_name}",
            body="A scheduled update. Unsubscribe: {unsubscribe_url}",
            max_recipients=20,
            created_by=self.creator,
        )

    def _customer(self, number: int) -> Customer:
        customer = Customer.objects.create(
            name=f"Scheduled Customer {number}",
            email=f"scheduled{number}@example.com",
            phone=f"+256700100{number:03d}",
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

    def _approve(self):
        prepare_campaign(self.campaign, user=self.creator)
        return approve_campaign(self.campaign, user=self.approver)

    def _schedule(self, *, batch_size=1):
        self._approve()
        return schedule_campaign(
            self.campaign,
            user=self.creator,
            scheduled_for=timezone.now() + timedelta(minutes=15),
            batch_size=batch_size,
        )

    def _make_due(self):
        self.campaign.refresh_from_db()
        self.campaign.next_run_at = timezone.now() - timedelta(minutes=1)
        self.campaign.save(update_fields=["next_run_at", "updated_at"])

    def test_schedule_requires_approved_campaign_and_records_event(self):
        with self.assertRaisesMessage(CampaignOperationError, "approved campaign"):
            schedule_campaign(
                self.campaign,
                user=self.creator,
                scheduled_for=timezone.now() + timedelta(minutes=15),
                batch_size=1,
            )
        scheduled = self._schedule()
        event = scheduled.automation_events.get(
            action=CampaignAutomationEvent.ACTION_SCHEDULED
        )
        self.assertEqual(scheduled.status, CustomerCampaign.STATUS_SCHEDULED)
        self.assertTrue(scheduled.automated_delivery)
        self.assertEqual(scheduled.automation_batch_size, 1)
        self.assertEqual(event.actor, self.creator)
        self.assertIsNotNone(scheduled.approval_expires_at)

    def test_schedule_form_requires_exact_phrase(self):
        approved = self._approve()
        scheduled_for = timezone.localtime(
            timezone.now() + timedelta(minutes=30)
        ).strftime("%Y-%m-%dT%H:%M")
        invalid = CampaignScheduleForm(
            {
                "scheduled_for": scheduled_for,
                "batch_size": 1,
                "confirmation": "SCHEDULE WRONG",
            },
            campaign=approved,
        )
        self.assertFalse(invalid.is_valid())
        valid = CampaignScheduleForm(
            {
                "scheduled_for": scheduled_for,
                "batch_size": 1,
                "confirmation": f"SCHEDULE {approved.pk}",
            },
            campaign=approved,
        )
        self.assertTrue(valid.is_valid(), valid.errors)

    @override_settings(CUSTOMER_CAMPAIGN_SCHEDULER_ENABLED=False)
    def test_scheduler_switch_blocks_due_execution(self):
        self._schedule()
        self._make_due()
        summary = process_scheduled_campaigns(limit=10)
        self.campaign.refresh_from_db()
        self.assertTrue(summary["disabled"])
        self.assertEqual(self.campaign.status, CustomerCampaign.STATUS_SCHEDULED)
        self.assertEqual(len(mail.outbox), 0)

    def test_due_batches_are_paced_and_complete(self):
        self._customer(2)
        self._schedule()
        self._make_due()

        first = process_scheduled_campaigns(limit=10)
        self.campaign.refresh_from_db()
        self.assertEqual(first["processed"], 1)
        self.assertEqual(first["sent"], 1)
        self.assertEqual(self.campaign.status, CustomerCampaign.STATUS_SCHEDULED)
        self.assertEqual(self.campaign.sent_count, 1)
        self.assertIsNotNone(self.campaign.next_run_at)

        self._make_due()
        second = process_scheduled_campaigns(limit=10)
        self.campaign.refresh_from_db()
        self.assertEqual(second["sent"], 1)
        self.assertEqual(second["completed"], 1)
        self.assertEqual(self.campaign.status, CustomerCampaign.STATUS_COMPLETED)
        self.assertEqual(self.campaign.sent_count, 2)
        self.assertEqual(self.campaign.automation_run_count, 2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(campaign_integrity_findings()["errors"], 0)

    def test_withdrawal_after_scheduling_is_suppressed(self):
        self._schedule()
        preference = self.customer.marketing_preference
        withdraw_all_marketing(preference)
        self._make_due()

        summary = process_scheduled_campaigns(limit=10)
        recipient = CustomerCampaignRecipient.objects.get(campaign=self.campaign)
        self.campaign.refresh_from_db()
        self.assertEqual(summary["sent"], 0)
        self.assertEqual(recipient.status, CustomerCampaignRecipient.STATUS_SUPPRESSED)
        self.assertEqual(recipient.suppression_reason, "email_consent_withdrawn")
        self.assertEqual(self.campaign.status, CustomerCampaign.STATUS_COMPLETED)
        self.assertEqual(len(mail.outbox), 0)

    def test_expired_approval_suppresses_remaining_recipients(self):
        self._schedule()
        self.campaign.refresh_from_db()
        self.campaign.approval_expires_at = timezone.now() - timedelta(minutes=1)
        self.campaign.next_run_at = timezone.now() - timedelta(minutes=1)
        self.campaign.save(
            update_fields=["approval_expires_at", "next_run_at", "updated_at"]
        )

        summary = process_scheduled_campaigns(limit=10)
        self.campaign.refresh_from_db()
        recipient = self.campaign.recipients.get()
        self.assertGreaterEqual(summary["expired"], 1)
        self.assertEqual(self.campaign.status, CustomerCampaign.STATUS_EXPIRED)
        self.assertEqual(recipient.status, CustomerCampaignRecipient.STATUS_SUPPRESSED)
        self.assertEqual(recipient.suppression_reason, "campaign_approval_expired")
        self.assertEqual(len(mail.outbox), 0)

    def test_manual_delivery_cannot_bypass_scheduled_mode(self):
        self._schedule()
        with self.assertRaisesMessage(CampaignOperationError, "scheduled-delivery mode"):
            send_campaign_batch(self.campaign, user=self.creator, batch_size=1)

    def test_pause_and_resume_record_append_only_events(self):
        scheduled = self._schedule()
        paused = pause_campaign(
            scheduled,
            user=self.creator,
            reason="Review campaign timing.",
        )
        self.assertEqual(paused.status, CustomerCampaign.STATUS_PAUSED)
        resumed = resume_campaign(
            paused,
            user=self.approver,
            next_run_at=timezone.now() + timedelta(minutes=20),
        )
        self.assertEqual(resumed.status, CustomerCampaign.STATUS_SCHEDULED)
        actions = list(
            resumed.automation_events.order_by("occurred_at", "id").values_list(
                "action", flat=True
            )
        )
        self.assertEqual(
            actions,
            [
                CampaignAutomationEvent.ACTION_SCHEDULED,
                CampaignAutomationEvent.ACTION_PAUSED,
                CampaignAutomationEvent.ACTION_RESUMED,
            ],
        )

    @override_settings(
        CUSTOMER_CAMPAIGN_AUTOMATION_BATCH_SIZE=2,
        CUSTOMER_CAMPAIGN_FAILURE_MIN_ATTEMPTS=2,
        CUSTOMER_CAMPAIGN_FAILURE_RATE_PERCENT=50,
    )
    def test_delivery_failure_rate_pauses_remaining_schedule(self):
        self._customer(2)
        self._customer(3)
        self._schedule(batch_size=2)
        self._make_due()

        def fail_delivery(log, **kwargs):
            log.mark_failed("SMTP unavailable during test")
            log.save(update_fields=["status", "error", "sent_at"])
            return log

        # A newly queued message must use the first-send API, not the retry
        # path which is reserved for explicitly approved retries.
        with patch(
            "customer_campaigns.services.send_queued_outbound_email",
            side_effect=fail_delivery,
        ) as first_send:
            summary = process_scheduled_campaigns(limit=10)

        self.assertEqual(first_send.call_count, 2)

        self.campaign.refresh_from_db()
        self.assertEqual(summary["failed"], 2)
        self.assertEqual(summary["paused"], 1)
        self.assertEqual(self.campaign.status, CustomerCampaign.STATUS_PAUSED)
        self.assertEqual(
            self.campaign.pause_reason,
            "delivery_failure_rate_circuit_breaker",
        )
        self.assertEqual(
            self.campaign.recipients.filter(
                status=CustomerCampaignRecipient.STATUS_PENDING
            ).count(),
            1,
        )
        self.assertEqual(
            OutboundEmail.objects.filter(status=OutboundEmail.STATUS_FAILED).count(),
            2,
        )
