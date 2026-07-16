from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from commerce.models import Order, OrderStatusEvent
from commerce.progress import order_progress
from crm.models import Customer


class OrderProgressTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="progress-customer",
            email="progress@example.com",
            password="strong-test-password",
        )
        self.customer = Customer.objects.create(
            name="Progress Customer",
            email=self.user.email,
            user=self.user,
        )

    def make_order(self, **overrides):
        data = {
            "reference": f"ORD-{Order.objects.count() + 1}",
            "customer": self.customer,
            "status": Order.STATUS_PENDING,
            "contact_name": self.customer.name,
            "contact_email": self.customer.email,
            "billing_summary": "Kampala",
            "shipping_summary": "Kampala",
            "total": "100000.00",
        }
        data.update(overrides)
        return Order.objects.create(**data)

    def test_delivery_progress_marks_previous_and_current_steps(self):
        order = self.make_order(status=Order.STATUS_PROCESSING)
        OrderStatusEvent.objects.create(
            order=order,
            from_status=Order.STATUS_PENDING,
            to_status=Order.STATUS_CONFIRMED,
            note="Payment confirmed",
        )
        OrderStatusEvent.objects.create(
            order=order,
            from_status=Order.STATUS_CONFIRMED,
            to_status=Order.STATUS_PROCESSING,
            note="Preparing device",
        )

        progress = order_progress(order)
        states = {step["status"]: step["state"] for step in progress["steps"]}
        self.assertEqual(states[Order.STATUS_PENDING], "complete")
        self.assertEqual(states[Order.STATUS_CONFIRMED], "complete")
        self.assertEqual(states[Order.STATUS_PROCESSING], "current")
        self.assertEqual(states[Order.STATUS_DISPATCHED], "upcoming")
        processing = next(
            step for step in progress["steps"] if step["status"] == Order.STATUS_PROCESSING
        )
        self.assertEqual(processing["note"], "Preparing device")

    def test_pickup_progress_uses_collection_steps(self):
        order = self.make_order(
            status=Order.STATUS_READY,
            fulfillment_type=Order.FULFILLMENT_PICKUP,
        )
        progress = order_progress(order)
        labels = [step["label"] for step in progress["steps"]]
        self.assertIn("Ready for pickup", labels)
        self.assertIn("Collected / fulfilled", labels)
        self.assertNotIn("Dispatched", labels)

    def test_cancelled_progress_preserves_reason(self):
        order = self.make_order(
            status=Order.STATUS_CANCELLED,
            cancellation_reason="Customer requested cancellation",
            cancelled_at=timezone.now(),
        )
        OrderStatusEvent.objects.create(
            order=order,
            from_status=Order.STATUS_PENDING,
            to_status=Order.STATUS_CANCELLED,
            note="Cancelled before confirmation",
        )
        progress = order_progress(order)
        self.assertTrue(progress["cancelled"])
        self.assertEqual(
            progress["cancellation_reason"],
            "Customer requested cancellation",
        )
        self.assertEqual(progress["steps"][0]["state"], "complete")

    def test_receipt_and_portal_pages_render_progress_component(self):
        order = self.make_order(status=Order.STATUS_CONFIRMED)
        OrderStatusEvent.objects.create(
            order=order,
            from_status=Order.STATUS_PENDING,
            to_status=Order.STATUS_CONFIRMED,
            note="Confirmed for testing",
        )

        receipt = self.client.get(
            reverse("order_detail", args=[order.reference, order.view_key])
        )
        self.assertEqual(receipt.status_code, 200)
        self.assertContains(receipt, "Order progress")
        self.assertContains(receipt, "customer_experience.css")
        self.assertEqual(
            receipt.headers["X-Robots-Tag"],
            "noindex, nofollow, noarchive",
        )

        self.client.force_login(self.user)
        portal = self.client.get(reverse("portal_order_detail", args=[order.pk]))
        self.assertEqual(portal.status_code, 200)
        self.assertContains(portal, "Order progress")
        self.assertContains(portal, "customer_experience.css")
