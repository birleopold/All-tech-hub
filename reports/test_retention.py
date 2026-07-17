from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import Category, Product, ProductReview, ProductSerial
from commerce.models import Order, OrderLine
from commerce.retention import order_review_subject
from crm.models import Customer
from messaging.models import OutboundEmail
from reports.retention import retention_summary


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    ORDER_REVIEW_EMAILS_ENABLED=True,
)
class RetentionReportTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Retention products",
            slug="retention-products-report",
        )
        self.product = Product.objects.create(
            category=self.category,
            name="Repeat Purchase Product",
            slug="repeat-purchase-product",
            kind=Product.KIND_PHYSICAL,
            price="100000.00",
            stock_quantity=10,
        )
        self.repeat_customer = Customer.objects.create(
            name="Repeat Buyer",
            email="repeat-report@example.com",
        )
        self.new_customer = Customer.objects.create(
            name="New Buyer",
            email="new-report@example.com",
        )
        self.dormant_customer = Customer.objects.create(
            name="Dormant Buyer",
            email="dormant-report@example.com",
        )
        self.first_order = self._order(
            "ORD-RET-RPT-001",
            self.repeat_customer,
            "100000.00",
            days_ago=20,
            status=Order.STATUS_DELIVERED,
        )
        self.second_order = self._order(
            "ORD-RET-RPT-002",
            self.repeat_customer,
            "200000.00",
            days_ago=5,
            status=Order.STATUS_FULFILLED,
        )
        self.new_order = self._order(
            "ORD-RET-RPT-003",
            self.new_customer,
            "50000.00",
            days_ago=3,
            status=Order.STATUS_CONFIRMED,
        )
        self._order(
            "ORD-RET-RPT-OLD",
            self.dormant_customer,
            "75000.00",
            days_ago=120,
            status=Order.STATUS_FULFILLED,
        )
        OutboundEmail.objects.create(
            to_email=self.repeat_customer.email,
            subject=order_review_subject(self.first_order),
            body="Please review your order.",
            status=OutboundEmail.STATUS_SENT,
            sent_at=timezone.now(),
        )
        ProductReview.objects.create(
            product=self.product,
            customer=self.repeat_customer,
            author_name=self.repeat_customer.name,
            rating=4,
            body="Good product.",
            is_verified_purchase=True,
            is_published=True,
        )
        ProductSerial.objects.create(
            product=self.product,
            serial_number="RETENTION-WARRANTY-001",
            status=ProductSerial.STATUS_SOLD,
            sold_to=self.repeat_customer,
            sold_at=self._sold_date_expiring_within_30_days(),
            warranty_months=1,
        )

    @staticmethod
    def _sold_date_expiring_within_30_days():
        target = timezone.localdate() + timedelta(days=15)
        previous_month = target.month - 1
        year = target.year
        if previous_month == 0:
            previous_month = 12
            year -= 1
        return date(year, previous_month, min(target.day, 28))

    def _order(self, reference, customer, total, *, days_ago, status):
        order = Order.objects.create(
            reference=reference,
            customer=customer,
            status=status,
            contact_name=customer.name,
            contact_email=customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            total=total,
        )
        Order.objects.filter(pk=order.pk).update(
            placed_at=timezone.now() - timedelta(days=days_ago)
        )
        order.refresh_from_db()
        OrderLine.objects.create(
            order=order,
            product=self.product,
            description=self.product.name,
            quantity=1,
            unit_price=total,
        )
        return order

    def test_summary_reconciles_repeat_customers_and_reputation(self):
        summary = retention_summary(90)

        self.assertEqual(summary["order_count"], 3)
        self.assertEqual(summary["unique_customers"], 2)
        self.assertEqual(summary["repeat_customers"], 1)
        self.assertEqual(summary["repeat_customer_rate"], Decimal("50.00"))
        self.assertEqual(summary["returning_orders"], 1)
        self.assertEqual(summary["returning_order_rate"], Decimal("33.33"))
        self.assertEqual(summary["revenue"], Decimal("350000.00"))
        self.assertEqual(summary["repeat_revenue"], Decimal("300000.00"))
        self.assertEqual(summary["repeat_revenue_rate"], Decimal("85.71"))
        self.assertEqual(summary["completed_orders"], 2)
        self.assertEqual(summary["review_requests_sent"], 1)
        self.assertEqual(summary["review_request_coverage"], Decimal("50.00"))
        self.assertEqual(summary["verified_review_count"], 1)
        self.assertEqual(summary["published_verified_reviews"], 1)
        self.assertEqual(summary["average_verified_rating"], 4.0)
        self.assertTrue(summary["review_email_enabled"])
        self.assertTrue(summary["email_delivery_ready"])
        self.assertEqual(summary["expiring_warranty_count"], 1)
        self.assertEqual(summary["dormant_customer_count"], 1)
        self.assertEqual(
            summary["dormant_customers"][0]["customer"],
            self.dormant_customer,
        )

    def test_cancelled_orders_do_not_inflate_retention(self):
        self._order(
            "ORD-RET-RPT-CANCELLED",
            self.new_customer,
            "900000.00",
            days_ago=1,
            status=Order.STATUS_CANCELLED,
        )

        summary = retention_summary(90)

        self.assertEqual(summary["order_count"], 3)
        self.assertEqual(summary["revenue"], Decimal("350000.00"))

    def test_staff_dashboard_is_private_and_renders_metrics(self):
        response = self.client.get(reverse("staff_retention_dashboard"))
        self.assertNotEqual(response.status_code, 200)

        staff = get_user_model().objects.create_user(
            username="retention-staff",
            email="retention-staff@example.com",
            password="strong-test-password",
            is_staff=True,
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("staff_retention_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Retention, reviews and repeat sales")
        self.assertContains(response, "85.71%")
        self.assertContains(response, "Verified review performance")
        self.assertContains(response, "Dormant Buyer")
