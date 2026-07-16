from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from commerce.fulfillment import transition_order
from commerce.models import Order, Shipment
from crm.models import Customer


class ShipmentAtomicityTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="shipment-staff",
            password="safe-password-123",
            is_staff=True,
        )
        customer = Customer.objects.create(
            name="Shipment Customer",
            email="shipment@example.com",
        )
        self.order = Order.objects.create(
            reference="ORD-SHIPMENT-001",
            customer=customer,
            contact_name=customer.name,
            contact_email=customer.email,
            billing_summary="Kampala",
            shipping_summary="Kampala",
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
        )
        self.client.force_login(self.staff)

    def shipment_payload(self, status):
        return {
            "carrier": "Test Carrier",
            "tracking_number": "TRACK-001",
            "tracking_url": "",
            "status": status,
            "estimated_delivery": "",
            "note": "Transaction reliability test",
        }

    def test_invalid_shipment_transition_rolls_back_shipment(self):
        response = self.client.post(
            reverse("staff_order_shipment", args=[self.order.pk]),
            self.shipment_payload(Shipment.STATUS_IN_TRANSIT),
        )

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_PENDING)
        self.assertFalse(Shipment.objects.filter(order=self.order).exists())

    def test_valid_shipment_and_order_transition_commit_together(self):
        order = transition_order(
            self.order,
            Order.STATUS_CONFIRMED,
            actor=self.staff,
            note="Confirmed",
        )
        order = transition_order(
            order,
            Order.STATUS_PROCESSING,
            actor=self.staff,
            note="Processing",
        )
        transition_order(
            order,
            Order.STATUS_READY,
            actor=self.staff,
            note="Ready for dispatch",
        )

        response = self.client.post(
            reverse("staff_order_shipment", args=[self.order.pk]),
            self.shipment_payload(Shipment.STATUS_IN_TRANSIT),
        )

        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        shipment = Shipment.objects.get(order=self.order)
        self.assertEqual(self.order.status, Order.STATUS_DISPATCHED)
        self.assertEqual(shipment.status, Shipment.STATUS_IN_TRANSIT)
        self.assertIsNotNone(shipment.dispatched_at)
