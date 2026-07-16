from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from catalog.models import Category, Product
from commerce.models import Order
from crm.models import Customer
from reliability.models import PaymentAttempt, PaymentRefund


class TransactionConstraintTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Constraint Test", slug="constraint-test")
        Product.objects.create(
            category=category,
            name="Constraint Product",
            slug="constraint-product",
            price=Decimal("10.00"),
            stock_quantity=1,
        )
        customer = Customer.objects.create(
            name="Constraint Customer",
            email="constraint@example.com",
        )
        self.order = Order.objects.create(
            reference="ORD-CONSTRAINT-001",
            customer=customer,
            contact_name=customer.name,
            contact_email=customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            subtotal=Decimal("10.00"),
            total=Decimal("10.00"),
        )

    def test_database_rejects_nonpositive_payment_amount(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentAttempt.objects.create(
                order=self.order,
                idempotency_key="zero-payment",
                provider="testpay",
                amount=Decimal("0.00"),
            )

    def test_database_rejects_nonpositive_refund_amount(self):
        attempt = PaymentAttempt.objects.create(
            order=self.order,
            idempotency_key="valid-payment",
            provider="testpay",
            amount=Decimal("10.00"),
            status=PaymentAttempt.STATUS_PAID,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentRefund.objects.create(
                payment_attempt=attempt,
                idempotency_key="zero-refund",
                amount=Decimal("0.00"),
                reason="Invalid zero refund",
            )

    def test_database_rejects_duplicate_nonblank_provider_reference(self):
        PaymentAttempt.objects.create(
            order=self.order,
            idempotency_key="provider-reference-one",
            provider="testpay",
            external_reference="PROVIDER-DUPLICATE-001",
            amount=Decimal("10.00"),
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentAttempt.objects.create(
                order=self.order,
                idempotency_key="provider-reference-two",
                provider="testpay",
                external_reference="PROVIDER-DUPLICATE-001",
                amount=Decimal("10.00"),
            )

    def test_database_allows_blank_provider_references(self):
        PaymentAttempt.objects.create(
            order=self.order,
            idempotency_key="blank-provider-reference-one",
            provider="testpay",
            amount=Decimal("4.00"),
        )
        PaymentAttempt.objects.create(
            order=self.order,
            idempotency_key="blank-provider-reference-two",
            provider="testpay",
            amount=Decimal("6.00"),
        )
        self.assertEqual(PaymentAttempt.objects.count(), 2)
