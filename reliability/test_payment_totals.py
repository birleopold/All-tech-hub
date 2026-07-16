from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Category, Product
from commerce.models import Order
from crm.models import Customer
from reliability.models import OrderReservation, PaymentAttempt
from reliability.services import (
    create_order_reservation,
    create_payment_attempt,
    transition_payment_attempt,
)


class PaymentTotalReliabilityTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Payment Tests", slug="payment-tests")
        Product.objects.create(
            category=category,
            name="Payment Test Product",
            slug="payment-test-product",
            price=Decimal("100.00"),
            stock_quantity=2,
        )
        self.customer = Customer.objects.create(
            name="Payment Customer",
            email="payments@example.com",
        )

    def make_order(self, reference: str) -> Order:
        order = Order.objects.create(
            reference=reference,
            customer=self.customer,
            contact_name=self.customer.name,
            contact_email=self.customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
        )
        create_order_reservation(order, f"reservation-{reference}")
        return order

    def test_partial_payment_does_not_confirm_order_until_total_is_paid(self):
        order = self.make_order("ORD-PARTIAL-001")
        first, _ = create_payment_attempt(
            order=order,
            idempotency_key="partial-payment-1",
            amount=Decimal("40.00"),
            provider="testpay",
        )
        transition_payment_attempt(first, PaymentAttempt.STATUS_PAID)

        order.refresh_from_db()
        order.stock_reservation.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PENDING)
        self.assertEqual(
            order.stock_reservation.status,
            OrderReservation.STATUS_RESERVED,
        )

        second, _ = create_payment_attempt(
            order=order,
            idempotency_key="partial-payment-2",
            amount=Decimal("60.00"),
            provider="testpay",
        )
        transition_payment_attempt(second, PaymentAttempt.STATUS_PAID)

        order.refresh_from_db()
        order.stock_reservation.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_CONFIRMED)
        self.assertEqual(
            order.stock_reservation.status,
            OrderReservation.STATUS_COMMITTED,
        )

    def test_payment_that_would_overpay_order_is_rejected(self):
        order = self.make_order("ORD-OVERPAY-001")
        first, _ = create_payment_attempt(
            order=order,
            idempotency_key="overpay-payment-1",
            amount=Decimal("60.00"),
            provider="testpay",
        )
        transition_payment_attempt(first, PaymentAttempt.STATUS_PAID)
        second, _ = create_payment_attempt(
            order=order,
            idempotency_key="overpay-payment-2",
            amount=Decimal("50.00"),
            provider="testpay",
        )

        with self.assertRaises(ValidationError):
            transition_payment_attempt(second, PaymentAttempt.STATUS_PAID)

        second.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(second.status, PaymentAttempt.STATUS_CREATED)
        self.assertEqual(order.status, Order.STATUS_PENDING)

    def test_provider_reference_replay_returns_existing_attempt(self):
        order = self.make_order("ORD-PROVIDER-001")
        first, created = create_payment_attempt(
            order=order,
            idempotency_key="provider-key-1",
            amount=Decimal("100.00"),
            provider="testpay",
            external_reference="PROVIDER-REF-001",
        )
        replay, replay_created = create_payment_attempt(
            order=order,
            idempotency_key="provider-key-2",
            amount=Decimal("100.00"),
            provider="testpay",
            external_reference="PROVIDER-REF-001",
        )

        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(first.pk, replay.pk)
        self.assertEqual(PaymentAttempt.objects.count(), 1)

    def test_provider_reference_cannot_move_to_another_order(self):
        first_order = self.make_order("ORD-PROVIDER-002")
        second_order = self.make_order("ORD-PROVIDER-003")
        create_payment_attempt(
            order=first_order,
            idempotency_key="provider-key-3",
            amount=Decimal("100.00"),
            provider="testpay",
            external_reference="PROVIDER-REF-002",
        )

        with self.assertRaises(ValidationError):
            create_payment_attempt(
                order=second_order,
                idempotency_key="provider-key-4",
                amount=Decimal("100.00"),
                provider="testpay",
                external_reference="PROVIDER-REF-002",
            )
