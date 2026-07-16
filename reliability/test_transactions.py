from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from catalog.models import Category, Product
from commerce.fulfillment import transition_order
from commerce.models import Order, OrderLine
from crm.models import Customer
from reliability.models import OrderReservation, PaymentAttempt, PaymentWebhookEvent
from reliability.services import (
    create_order_reservation,
    create_payment_attempt,
    record_payment_refund,
    register_webhook_event,
    transition_payment_attempt,
)


@override_settings(ORDER_RESERVATION_MINUTES=60)
class TransactionReliabilityTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Laptops", slug="laptops")
        self.product = Product.objects.create(
            category=self.category,
            name="Reliable Laptop",
            slug="reliable-laptop",
            price=Decimal("100.00"),
            stock_quantity=3,
            track_inventory=True,
        )
        self.customer = Customer.objects.create(
            name="Test Customer",
            email="customer@example.com",
        )

    def make_order(self, reference="ORD-TEST-001", total=Decimal("100.00")):
        order = Order.objects.create(
            reference=reference,
            customer=self.customer,
            contact_name=self.customer.name,
            contact_email=self.customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            subtotal=total,
            total=total,
        )
        OrderLine.objects.create(
            order=order,
            product=self.product,
            description=self.product.name,
            quantity=2,
            unit_price=Decimal("50.00"),
        )
        return order

    def test_reservation_key_is_idempotent_for_same_order(self):
        order = self.make_order()
        first = create_order_reservation(order, "checkout-key-1")
        second = create_order_reservation(order, "checkout-key-1")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(OrderReservation.objects.count(), 1)

    def test_reservation_key_cannot_be_reused_for_another_order(self):
        first_order = self.make_order()
        second_order = self.make_order(reference="ORD-TEST-002")
        create_order_reservation(first_order, "checkout-key-2")

        with self.assertRaises(ValidationError):
            create_order_reservation(second_order, "checkout-key-2")

        self.assertEqual(OrderReservation.objects.count(), 1)

    def test_confirmation_commits_reservation_without_changing_stock(self):
        order = self.make_order()
        reservation = create_order_reservation(order, "checkout-key-3")

        transition_order(order, Order.STATUS_CONFIRMED, note="Payment confirmed")

        reservation.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(reservation.status, OrderReservation.STATUS_COMMITTED)
        self.assertIsNotNone(reservation.committed_at)
        self.assertEqual(self.product.stock_quantity, 3)

    def test_cancellation_requires_reason(self):
        order = self.make_order()
        create_order_reservation(order, "checkout-key-reason")

        with self.assertRaises(ValidationError):
            transition_order(order, Order.STATUS_CANCELLED, note="")

        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)
        self.assertEqual(self.product.stock_quantity, 3)

    def test_cancellation_releases_reservation_and_restores_stock_once(self):
        order = self.make_order()
        reservation = create_order_reservation(order, "checkout-key-4")

        transition_order(order, Order.STATUS_CANCELLED, note="Customer cancelled")
        self.product.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)
        self.assertEqual(reservation.status, OrderReservation.STATUS_RELEASED)

        transition_order(order, Order.STATUS_CANCELLED, note="Repeated request")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)

    def test_cancellation_closes_open_payment_attempts(self):
        order = self.make_order()
        create_order_reservation(order, "checkout-key-open-payment")
        attempt, _ = create_payment_attempt(
            order=order,
            idempotency_key="payment-key-open",
            amount=order.total,
            provider="testpay",
        )
        attempt = transition_payment_attempt(
            attempt,
            PaymentAttempt.STATUS_PENDING,
            auto_confirm_order=False,
        )

        transition_order(order, Order.STATUS_CANCELLED, note="Customer cancelled")

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.STATUS_CANCELLED)

    def test_paid_order_requires_full_refund_before_cancellation(self):
        order = self.make_order()
        reservation = create_order_reservation(order, "checkout-key-paid-cancel")
        attempt, _ = create_payment_attempt(
            order=order,
            idempotency_key="payment-key-paid-cancel",
            amount=order.total,
            provider="testpay",
        )
        attempt = transition_payment_attempt(
            attempt,
            PaymentAttempt.STATUS_PAID,
        )

        with self.assertRaises(ValidationError):
            transition_order(order, Order.STATUS_CANCELLED, note="Customer cancelled")

        order.refresh_from_db()
        reservation.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)
        self.assertEqual(reservation.status, OrderReservation.STATUS_COMMITTED)
        self.assertEqual(self.product.stock_quantity, 3)

        record_payment_refund(
            payment_attempt=attempt,
            idempotency_key="refund-key-paid-cancel",
            amount=order.total,
            reason="Full refund before cancellation",
        )
        transition_order(order, Order.STATUS_CANCELLED, note="Refunded and cancelled")

        order.refresh_from_db()
        reservation.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(reservation.status, OrderReservation.STATUS_RELEASED)
        self.assertEqual(self.product.stock_quantity, 5)

    def test_expiry_command_cancels_pending_order_and_restores_stock(self):
        order = self.make_order()
        reservation = create_order_reservation(
            order,
            "checkout-key-5",
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        call_command("expire_order_reservations")

        order.refresh_from_db()
        reservation.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CANCELLED)
        self.assertEqual(reservation.status, OrderReservation.STATUS_EXPIRED)
        self.assertEqual(self.product.stock_quantity, 5)

    def test_payment_attempt_is_idempotent(self):
        order = self.make_order()
        first, first_created = create_payment_attempt(
            order=order,
            idempotency_key="payment-key-1",
            amount=order.total,
            provider="testpay",
        )
        second, second_created = create_payment_attempt(
            order=order,
            idempotency_key="payment-key-1",
            amount=order.total,
            provider="testpay",
        )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_paid_attempt_confirms_order_and_commits_reservation(self):
        order = self.make_order()
        reservation = create_order_reservation(order, "checkout-key-6")
        attempt, _ = create_payment_attempt(
            order=order,
            idempotency_key="payment-key-2",
            amount=order.total,
            provider="testpay",
        )

        transition_payment_attempt(
            attempt,
            PaymentAttempt.STATUS_PAID,
            external_reference="PAY-123",
        )

        order.refresh_from_db()
        reservation.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.STATUS_PAID)
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)
        self.assertEqual(reservation.status, OrderReservation.STATUS_COMMITTED)

    def test_refunds_are_idempotent_and_cannot_exceed_payment(self):
        order = self.make_order()
        create_order_reservation(order, "checkout-key-7")
        attempt, _ = create_payment_attempt(
            order=order,
            idempotency_key="payment-key-3",
            amount=order.total,
            provider="testpay",
        )
        attempt = transition_payment_attempt(
            attempt,
            PaymentAttempt.STATUS_PAID,
            auto_confirm_order=False,
        )

        first, created = record_payment_refund(
            payment_attempt=attempt,
            idempotency_key="refund-key-1",
            amount=Decimal("40.00"),
            reason="Partial return",
        )
        duplicate, duplicate_created = record_payment_refund(
            payment_attempt=attempt,
            idempotency_key="refund-key-1",
            amount=Decimal("40.00"),
            reason="Repeated callback",
        )

        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(first.pk, duplicate.pk)
        attempt.refresh_from_db()
        self.assertEqual(
            attempt.status,
            PaymentAttempt.STATUS_PARTIALLY_REFUNDED,
        )

        with self.assertRaises(ValidationError):
            record_payment_refund(
                payment_attempt=attempt,
                idempotency_key="refund-key-too-large",
                amount=Decimal("61.00"),
                reason="Too much",
            )

        record_payment_refund(
            payment_attempt=attempt,
            idempotency_key="refund-key-2",
            amount=Decimal("60.00"),
            reason="Balance refund",
        )
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.STATUS_REFUNDED)
        self.assertEqual(attempt.refundable_amount, Decimal("0"))

    def test_webhook_event_id_rejects_changed_payload(self):
        event, created = register_webhook_event(
            provider="testpay",
            event_id="evt-1",
            payload={"status": "paid", "amount": "100.00"},
        )
        duplicate, duplicate_created = register_webhook_event(
            provider="testpay",
            event_id="evt-1",
            payload={"amount": "100.00", "status": "paid"},
        )

        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(event.pk, duplicate.pk)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 1)

        with self.assertRaises(ValidationError):
            register_webhook_event(
                provider="testpay",
                event_id="evt-1",
                payload={"status": "failed", "amount": "100.00"},
            )
