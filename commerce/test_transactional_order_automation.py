from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.db import transaction
from django.test import TestCase, override_settings

from automation.models import AutomationJob
from automation.order_notifications import (
    JOB_ORDER_CONFIRMATION_EMAIL,
    JOB_ORDER_STATUS_EMAIL,
    queue_order_confirmation_email,
)
from automation.services import process_automation_jobs
from commerce.models import Order, OrderStatusEvent
from crm.models import Customer
from messaging.models import OutboundEmail


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="orders@example.com",
    ORDER_CUSTOMER_EMAILS_ENABLED=True,
    ORDER_STATUS_EMAILS_ENABLED=True,
)
class TransactionalOrderAutomationTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Automation Customer",
            email="buyer@example.com",
            phone="+256700000000",
        )

    def create_order(self, reference="ORD-AUTO-001"):
        return Order.objects.create(
            reference=reference,
            customer=self.customer,
            contact_name=self.customer.name,
            contact_email=self.customer.email,
            contact_phone=self.customer.phone,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            subtotal=Decimal("1500000.00"),
            tax_rate=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total=Decimal("1500000.00"),
        )

    def test_order_and_notification_job_commit_together(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                order = self.create_order("ORD-ROLLBACK-001")
                self.assertTrue(
                    AutomationJob.objects.filter(
                        idempotency_key=f"order-confirmation:{order.pk}"
                    ).exists()
                )
                raise RuntimeError("rollback checkout")

        self.assertFalse(Order.objects.filter(reference="ORD-ROLLBACK-001").exists())
        self.assertFalse(
            AutomationJob.objects.filter(job_type=JOB_ORDER_CONFIRMATION_EMAIL).exists()
        )

    def test_worker_sends_confirmation_once_with_stable_idempotency(self):
        order = self.create_order()
        job = AutomationJob.objects.get(
            idempotency_key=f"order-confirmation:{order.pk}"
        )
        self.assertEqual(job.job_type, JOB_ORDER_CONFIRMATION_EMAIL)

        result = process_automation_jobs(limit=10, worker_id="test-order-worker")

        job.refresh_from_db()
        self.assertEqual(job.status, AutomationJob.STATUS_SUCCEEDED)
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(order.reference, mail.outbox[0].subject)
        outbound = OutboundEmail.objects.get(
            idempotency_key=f"order-confirmation:{order.pk}"
        )
        self.assertEqual(outbound.status, OutboundEmail.STATUS_SENT)
        self.assertEqual(outbound.attempt_count, 1)

        self.assertFalse(queue_order_confirmation_email(order.pk))
        process_automation_jobs(limit=10, worker_id="test-order-worker-again")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(OutboundEmail.objects.count(), 1)

    def test_visible_status_event_is_delivered_by_same_worker(self):
        order = self.create_order("ORD-AUTO-STATUS")
        process_automation_jobs(limit=10, worker_id="test-confirmation-worker")
        mail.outbox.clear()

        event = OrderStatusEvent.objects.create(
            order=order,
            from_status=Order.STATUS_PENDING,
            to_status=Order.STATUS_CONFIRMED,
            note="Stock and payment details confirmed.",
            visible_to_customer=True,
        )
        job = AutomationJob.objects.get(idempotency_key=f"order-status:{event.pk}")
        self.assertEqual(job.job_type, JOB_ORDER_STATUS_EMAIL)

        process_automation_jobs(limit=10, worker_id="test-status-worker")

        job.refresh_from_db()
        self.assertEqual(job.status, AutomationJob.STATUS_SUCCEEDED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(order.reference, mail.outbox[0].subject)
        self.assertIn("Confirmed", mail.outbox[0].subject)
        self.assertTrue(
            OutboundEmail.objects.filter(
                idempotency_key=f"order-status:{event.pk}",
                status=OutboundEmail.STATUS_SENT,
            ).exists()
        )

    def test_private_status_event_does_not_queue_customer_email(self):
        order = self.create_order("ORD-AUTO-PRIVATE")
        event = OrderStatusEvent.objects.create(
            order=order,
            from_status=Order.STATUS_PENDING,
            to_status=Order.STATUS_CONFIRMED,
            note="Internal verification note.",
            visible_to_customer=False,
        )
        self.assertFalse(
            AutomationJob.objects.filter(
                idempotency_key=f"order-status:{event.pk}"
            ).exists()
        )

    def test_smtp_failure_is_recorded_and_scheduled_for_retry(self):
        order = self.create_order("ORD-AUTO-RETRY")
        job = AutomationJob.objects.get(
            idempotency_key=f"order-confirmation:{order.pk}"
        )

        with patch(
            "commerce.customer_messages.send_mail",
            side_effect=RuntimeError("temporary SMTP outage"),
        ):
            result = process_automation_jobs(limit=1, worker_id="test-failing-worker")

        job.refresh_from_db()
        self.assertEqual(job.status, AutomationJob.STATUS_RETRY)
        self.assertEqual(result["retried"], 1)
        self.assertIn("temporary SMTP outage", job.last_error)
        outbound = OutboundEmail.objects.get(
            idempotency_key=f"order-confirmation:{order.pk}"
        )
        self.assertEqual(outbound.status, OutboundEmail.STATUS_FAILED)
        self.assertEqual(outbound.attempt_count, 1)
