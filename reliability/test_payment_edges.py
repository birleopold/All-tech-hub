from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from commerce.models import Order
from crm.models import Customer
from reliability.models import PaymentAttempt
from reliability.services import (
    create_payment_attempt,
    record_payment_refund,
    transition_payment_attempt,
)


class PaymentEdgeCaseTests(TestCase):
    def setUp(self):
        customer = Customer.objects.create(
            name="Payment Edge Customer",
            email="payment-edge@example.com",
        )
        self.order = Order.objects.create(
            reference="ORD-PAYMENT-EDGE-001",
            customer=customer,
            contact_name=customer.name,
            contact_email=customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
        )

    def test_late_paid_callback_is_rejected_for_cancelled_order(self):
        attempt, _ = create_payment_attempt(
            order=self.order,
            idempotency_key="late-paid-callback",
            amount=Decimal("100.00"),
            provider="testpay",
        )
        self.order.status = Order.STATUS_CANCELLED
        self.order.cancellation_reason = "Cancelled before provider callback"
        self.order.save(update_fields=["status", "cancellation_reason", "updated_at"])

        with self.assertRaises(ValidationError):
            transition_payment_attempt(attempt, PaymentAttempt.STATUS_PAID)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.STATUS_CREATED)

    def test_disputed_payment_can_be_refunded_through_audited_service(self):
        attempt, _ = create_payment_attempt(
            order=self.order,
            idempotency_key="disputed-payment",
            amount=Decimal("100.00"),
            provider="testpay",
        )
        attempt = transition_payment_attempt(
            attempt,
            PaymentAttempt.STATUS_PAID,
            auto_confirm_order=False,
        )
        attempt = transition_payment_attempt(
            attempt,
            PaymentAttempt.STATUS_DISPUTED,
            auto_confirm_order=False,
        )

        refund, created = record_payment_refund(
            payment_attempt=attempt,
            idempotency_key="disputed-refund",
            amount=Decimal("100.00"),
            reason="Dispute resolved by full refund",
        )

        self.assertTrue(created)
        self.assertEqual(refund.amount, Decimal("100.00"))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.STATUS_REFUNDED)
        self.assertEqual(attempt.refundable_amount, Decimal("0"))
