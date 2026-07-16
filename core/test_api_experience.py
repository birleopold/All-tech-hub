from django.test import TestCase
from django.urls import reverse

from commerce.models import Order, OrderStatusEvent, Shipment
from crm.models import Customer


class OrderExperienceApiTests(TestCase):
    def setUp(self):
        customer = Customer.objects.create(
            name="API Customer",
            email="api@example.com",
        )
        self.order = Order.objects.create(
            reference="ORD-API-001",
            customer=customer,
            status=Order.STATUS_DISPATCHED,
            contact_name=customer.name,
            contact_email=customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            total="250000.00",
        )
        OrderStatusEvent.objects.create(
            order=self.order,
            from_status=Order.STATUS_READY,
            to_status=Order.STATUS_DISPATCHED,
            note="Driver has collected the package",
        )
        Shipment.objects.create(
            order=self.order,
            carrier="LEOSOFT Delivery",
            tracking_number="TRACK-001",
            status=Shipment.STATUS_IN_TRANSIT,
            note="Delivery is in progress",
        )

    def test_secret_order_lookup_includes_progress_and_private_cache_headers(self):
        response = self.client.get(
            reverse("api_order_lookup"),
            {
                "reference": self.order.reference,
                "view_key": str(self.order.view_key),
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status_display"], "Dispatched")
        self.assertEqual(payload["progress"]["steps"][4]["state"], "current")
        self.assertEqual(payload["shipment"]["tracking_number"], "TRACK-001")
        self.assertIn("private", response.headers["Cache-Control"])
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow, noarchive")

    def test_order_lookup_still_requires_both_secret_parts(self):
        response = self.client.get(
            reverse("api_order_lookup"),
            {"reference": self.order.reference},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow, noarchive")
