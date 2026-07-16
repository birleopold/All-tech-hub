from django.test import TestCase
from django.utils import timezone

from commerce.models import Order, OrderStatusEvent
from commerce.progress import order_progress
from crm.models import Customer


class OrderProgressTests(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name="Progress Customer",
            email="progress@example.com",
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
