from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from catalog.models import Category, Product, ProductReview, ProductVariant
from commerce.customer_messages import retry_failed_order_emails
from commerce.models import Order, OrderLine, OrderStatusEvent
from commerce.retention import order_review_subject, send_order_review_request
from core.models import CompanySettings
from crm.models import Customer
from messaging.models import OutboundEmail


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="orders@leosoftug.com",
    ORDER_CUSTOMER_EMAILS_ENABLED=True,
    ORDER_STATUS_EMAILS_ENABLED=True,
    ORDER_REVIEW_EMAILS_ENABLED=True,
)
class RetentionExperienceTests(TestCase):
    def setUp(self):
        company = CompanySettings.load()
        company.company_name = "LEOSOFT UG LTD"
        company.website = "https://leosoftug.com"
        company.save()
        self.customer = Customer.objects.create(
            name="Repeat Customer",
            email="repeat@example.com",
        )
        category = Category.objects.create(name="Laptops", slug="retention-laptops")
        self.product = Product.objects.create(
            category=category,
            name="Retention Laptop",
            slug="retention-laptop",
            price="1200000.00",
            stock_quantity=5,
            kind=Product.KIND_PHYSICAL,
        )
        self.order = Order.objects.create(
            reference="ORD-RET-001",
            customer=self.customer,
            status=Order.STATUS_DELIVERED,
            contact_name=self.customer.name,
            contact_email=self.customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            total="1200000.00",
        )
        OrderLine.objects.create(
            order=self.order,
            product=self.product,
            description=self.product.name,
            quantity=1,
            unit_price=self.product.price,
        )

    def test_review_request_is_sent_once_with_private_verified_link(self):
        first = send_order_review_request(self.order)
        second = send_order_review_request(self.order)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.status, OutboundEmail.STATUS_SENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, order_review_subject(self.order))
        self.assertIn(str(self.order.view_key), mail.outbox[0].body)
        self.assertIn(self.product.name, mail.outbox[0].body)

    def test_completed_order_can_submit_verified_review(self):
        url = reverse(
            "order_product_review",
            kwargs={
                "reference": self.order.reference,
                "view_key": self.order.view_key,
                "product_id": self.product.pk,
            },
        )
        response = self.client.post(
            url,
            {"rating": "5", "title": "Excellent", "body": "Reliable laptop."},
        )

        self.assertRedirects(response, self.order.get_absolute_url())
        review = ProductReview.objects.get(product=self.product, customer=self.customer)
        self.assertTrue(review.is_verified_purchase)
        self.assertFalse(review.is_published)
        self.assertEqual(review.rating, 5)

    def test_review_link_rejects_wrong_private_key(self):
        url = reverse(
            "order_product_review",
            kwargs={
                "reference": self.order.reference,
                "view_key": "00000000-0000-0000-0000-000000000000",
                "product_id": self.product.pk,
            },
        )
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_review_link_handles_same_product_on_multiple_variant_lines(self):
        variant = ProductVariant.objects.create(
            product=self.product,
            name="16GB",
            price=self.product.price,
            stock_quantity=2,
        )
        OrderLine.objects.create(
            order=self.order,
            product=self.product,
            product_variant=variant,
            description=f"{self.product.name} — {variant.name}",
            quantity=1,
            unit_price=variant.price,
        )
        url = reverse(
            "order_product_review",
            kwargs={
                "reference": self.order.reference,
                "view_key": self.order.view_key,
                "product_id": self.product.pk,
            },
        )

        self.assertEqual(self.client.get(url).status_code, 200)

    def test_completed_order_can_reorder_available_items(self):
        url = reverse(
            "order_reorder",
            kwargs={
                "reference": self.order.reference,
                "view_key": self.order.view_key,
            },
        )
        response = self.client.post(url)

        self.assertRedirects(response, reverse("cart"))
        self.assertEqual(
            self.client.session.get("alltech_cart"),
            {f"p:{self.product.pk}": 1},
        )

    def test_failed_review_request_can_use_customer_email_retry(self):
        row = OutboundEmail.objects.create(
            to_email=self.customer.email,
            subject=order_review_subject(self.order),
            body="Please review your purchase.",
            status=OutboundEmail.STATUS_FAILED,
            error="Temporary SMTP failure",
        )

        result = retry_failed_order_emails(limit=10)
        row.refresh_from_db()

        self.assertEqual(result, {"processed": 1, "sent": 1, "failed": 0})
        self.assertEqual(row.status, OutboundEmail.STATUS_SENT)
        self.assertEqual(row.error, "")

    def test_customer_visible_completion_event_queues_review_request(self):
        self.order.status = Order.STATUS_FULFILLED
        self.order.save(update_fields=["status", "updated_at"])
        with self.captureOnCommitCallbacks(execute=True):
            OrderStatusEvent.objects.create(
                order=self.order,
                from_status=Order.STATUS_DELIVERED,
                to_status=Order.STATUS_FULFILLED,
                visible_to_customer=True,
            )

        subjects = set(OutboundEmail.objects.values_list("subject", flat=True))
        self.assertIn(f"Order {self.order.reference}: Fulfilled", subjects)
        self.assertIn(order_review_subject(self.order), subjects)
