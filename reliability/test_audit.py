from decimal import Decimal
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from commerce.fulfillment import transition_order
from commerce.models import Order
from crm.models import Customer
from reliability.models import PaymentAttempt
from reliability.services import create_order_reservation


class TransactionIntegrityAuditTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Audit Customer",
            email="audit@example.com",
        )

    def make_order(self, reference: str, status=Order.STATUS_PENDING):
        return Order.objects.create(
            reference=reference,
            customer=self.customer,
            contact_name=self.customer.name,
            contact_email=self.customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            status=status,
        )

    def test_clean_reservation_aware_order_passes_audit(self):
        order = self.make_order("ORD-AUDIT-CLEAN")
        create_order_reservation(order, "audit-clean-reservation")
        transition_order(
            order,
            Order.STATUS_CONFIRMED,
            note="Confirmed for audit",
        )
        output = StringIO()

        call_command("audit_transaction_integrity", stdout=output)

        self.assertIn("Transaction integrity audit passed", output.getvalue())

    def test_legacy_pending_order_is_warning_only_by_default(self):
        self.make_order("ORD-AUDIT-LEGACY")
        output = StringIO()

        call_command("audit_transaction_integrity", stdout=output)

        self.assertIn("pending_without_reservation", output.getvalue())
        with self.assertRaises(CommandError):
            call_command(
                "audit_transaction_integrity",
                fail_on_warning=True,
                stdout=StringIO(),
            )

    def test_cancelled_order_with_live_payment_fails_audit(self):
        order = self.make_order(
            "ORD-AUDIT-FAILED",
            status=Order.STATUS_CANCELLED,
        )
        PaymentAttempt.objects.create(
            order=order,
            idempotency_key="audit-live-payment",
            provider="testpay",
            amount=Decimal("100.00"),
            status=PaymentAttempt.STATUS_PAID,
        )

        with self.assertRaises(CommandError):
            call_command(
                "audit_transaction_integrity",
                stdout=StringIO(),
            )
