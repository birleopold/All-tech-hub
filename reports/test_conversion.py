from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from commerce.models import Order
from crm.models import Customer
from growth.models import SavedCart
from messaging.models import OutboundEmail
from reports.conversion import conversion_summary


class ConversionLifecycleReportTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Report Customer",
            email="report@example.com",
        )
        self.order = Order.objects.create(
            reference="ORD-CONV-001",
            customer=self.customer,
            status=Order.STATUS_CONFIRMED,
            contact_name=self.customer.name,
            contact_email=self.customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            total="500000.00",
            coupon_code_applied="WELCOME",
        )
        OutboundEmail.objects.create(
            to_email=self.customer.email,
            subject=f"Order {self.order.reference} received — LEOSOFT UG LTD",
            body="Confirmation",
            status=OutboundEmail.STATUS_SENT,
            sent_at=timezone.now(),
        )
        OutboundEmail.objects.create(
            to_email=self.customer.email,
            subject=f"Order {self.order.reference}: Confirmed",
            body="Status update",
            status=OutboundEmail.STATUS_SENT,
            sent_at=timezone.now(),
        )
        SavedCart.objects.create(
            session_key="session-recovered",
            email=self.customer.email,
            cart_data={"p:1": 1},
            subtotal="500000.00",
            status=SavedCart.STATUS_RECOVERED,
            recovered_order=self.order,
        )
        SavedCart.objects.create(
            session_key="session-active",
            email="active@example.com",
            cart_data={"p:2": 1},
            subtotal="200000.00",
            status=SavedCart.STATUS_ACTIVE,
        )

    def test_summary_reconciles_orders_saved_carts_and_email_health(self):
        summary = conversion_summary(30)

        self.assertEqual(summary["order_count"], 1)
        self.assertEqual(summary["revenue"], Decimal("500000.00"))
        self.assertEqual(summary["average_order_value"], Decimal("500000.00"))
        self.assertEqual(summary["coupon_orders"], 1)
        self.assertEqual(summary["coupon_order_rate"], Decimal("100.00"))
        self.assertEqual(summary["saved_cart_recovered"], 1)
        self.assertEqual(summary["saved_cart_active"], 1)
        self.assertEqual(summary["saved_cart_recovery_rate"], Decimal("50.00"))
        self.assertEqual(summary["recovered_revenue"], Decimal("500000.00"))
        self.assertEqual(summary["checkout_conversion_proxy"], Decimal("50.00"))
        self.assertEqual(summary["missing_confirmation_emails"], 0)
        self.assertEqual(summary["failed_order_emails"], 0)
        self.assertEqual(summary["status_emails_sent"], 1)

    def test_summary_flags_failed_email_and_old_pending_order(self):
        pending = Order.objects.create(
            reference="ORD-CONV-PENDING",
            customer=self.customer,
            status=Order.STATUS_PENDING,
            contact_name=self.customer.name,
            contact_email="pending@example.com",
            billing_summary="Kampala",
            shipping_summary="Kampala",
            total="100000.00",
        )
        Order.objects.filter(pk=pending.pk).update(
            placed_at=timezone.now() - timedelta(hours=25)
        )
        OutboundEmail.objects.create(
            to_email=pending.contact_email,
            subject=f"Order {pending.reference} received — LEOSOFT UG LTD",
            body="Confirmation",
            status=OutboundEmail.STATUS_FAILED,
            error="SMTP unavailable",
        )

        summary = conversion_summary(30)
        self.assertEqual(summary["failed_order_emails"], 1)
        self.assertEqual(summary["missing_confirmation_emails"], 1)
        self.assertEqual(summary["pending_older_than_24h"], 1)

    def test_staff_dashboard_is_private_and_renders_metrics(self):
        response = self.client.get(reverse("staff_conversion_lifecycle"))
        self.assertNotEqual(response.status_code, 200)

        user_model = get_user_model()
        staff = user_model.objects.create_user(
            username="conversion-staff",
            email="staff@example.com",
            password="strong-test-password",
            is_staff=True,
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("staff_conversion_lifecycle"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conversion and customer lifecycle")
        self.assertContains(response, "500,000.00")
        self.assertContains(response, "Saved carts")
