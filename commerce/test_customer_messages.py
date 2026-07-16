from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from catalog.models import Category, Product
from commerce.customer_messages import (
    order_confirmation_subject,
    retry_failed_order_emails,
    send_order_confirmation,
)
from commerce.models import Order, OrderLine, OrderStatusEvent
from core.models import CompanySettings
from crm.models import Customer
from messaging.models import OutboundEmail


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="orders@leosoftug.com",
    ORDER_CUSTOMER_EMAILS_ENABLED=True,
    ORDER_STATUS_EMAILS_ENABLED=True,
)
class CustomerOrderEmailTests(TestCase):
    def setUp(self):
        company = CompanySettings.load()
        company.company_name = "LEOSOFT UG LTD"
        company.website = "https://leosoftug.com"
        company.email = "sales@leosoftug.com"
        company.phone = "+256700000000"
        company.bank_details = "Mobile Money: 0700000000\nAccount name: LEOSOFT UG LTD"
        company.save()
        self.customer = Customer.objects.create(
            name="Email Customer",
            email="buyer@example.com",
        )
        category = Category.objects.create(name="Computers", slug="computers")
        product = Product.objects.create(
            category=category,
            name="Business Laptop",
            slug="business-laptop-email-test",
            price="1500000.00",
            stock_quantity=2,
        )
        self.order = Order.objects.create(
            reference="ORD-EMAIL-001",
            customer=self.customer,
            contact_name=self.customer.name,
            contact_email=self.customer.email,
            contact_phone="0700000000",
            billing_summary="Kampala",
            shipping_summary="Kampala",
            total="1500000.00",
        )
        OrderLine.objects.create(
            order=self.order,
            product=product,
            description=product.name,
            quantity=1,
            unit_price=product.price,
        )

    def test_confirmation_is_logged_sent_and_deduplicated(self):
        first = send_order_confirmation(self.order)
        second = send_order_confirmation(self.order)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.status, OutboundEmail.STATUS_SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, order_confirmation_subject(self.order))
        self.assertIn(self.order.reference, mail.outbox[0].body)
        self.assertIn("Mobile Money", mail.outbox[0].body)
        self.assertIn(str(self.order.view_key), mail.outbox[0].body)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_console_backend_is_not_treated_as_customer_delivery(self):
        row = send_order_confirmation(self.order)

        self.assertIsNone(row)
        self.assertFalse(OutboundEmail.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_customer_visible_status_event_sends_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            OrderStatusEvent.objects.create(
                order=self.order,
                from_status=Order.STATUS_PENDING,
                to_status=Order.STATUS_CONFIRMED,
                note="Payment reference received",
                visible_to_customer=True,
            )

        row = OutboundEmail.objects.get(subject=f"Order {self.order.reference}: Confirmed")
        self.assertEqual(row.status, OutboundEmail.STATUS_SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Payment reference received", mail.outbox[0].body)

    def test_internal_status_event_does_not_email_customer(self):
        with self.captureOnCommitCallbacks(execute=True):
            OrderStatusEvent.objects.create(
                order=self.order,
                from_status=Order.STATUS_PENDING,
                to_status=Order.STATUS_PROCESSING,
                note="Internal fraud review",
                visible_to_customer=False,
            )
        self.assertFalse(OutboundEmail.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_delivery_failure_is_logged_without_raising(self):
        with patch(
            "commerce.customer_messages.send_mail",
            side_effect=RuntimeError("SMTP unavailable"),
        ):
            row = send_order_confirmation(self.order)

        self.assertEqual(row.status, OutboundEmail.STATUS_FAILED)
        self.assertIn("SMTP unavailable", row.error)

    def test_failed_order_email_can_be_retried(self):
        row = OutboundEmail.objects.create(
            to_email=self.customer.email,
            subject=f"Order {self.order.reference}: Dispatched",
            body="Your order is on the way.",
            status=OutboundEmail.STATUS_FAILED,
            error="Temporary failure",
        )
        result = retry_failed_order_emails(limit=10)
        row.refresh_from_db()

        self.assertEqual(result, {"processed": 1, "sent": 1, "failed": 0})
        self.assertEqual(row.status, OutboundEmail.STATUS_SENT)
        self.assertEqual(row.error, "")
