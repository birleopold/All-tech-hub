from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from commerce.models import Order, OrderStatusEvent, Shipment
from crm.models import Customer
from operations.models import JobCard


class PortalIsolationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user("portal-a", password="pw")
        self.user_b = User.objects.create_user("portal-b", password="pw")
        self.customer_a = Customer.objects.create(
            name="A", email="a@example.com", user=self.user_a
        )
        self.customer_b = Customer.objects.create(
            name="B", email="b@example.com", user=self.user_b
        )
        self.job_b = JobCard.objects.create(customer=self.customer_b, title="Private")

    def test_customer_cannot_view_another_customers_job(self):
        self.client.force_login(self.user_a)
        response = self.client.get(
            reverse("portal_job_detail", args=[self.job_b.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_external_wishlist_next_is_rejected(self):
        from decimal import Decimal

        from catalog.models import Category, Product

        category = Category.objects.create(name="Portal", slug="portal-test")
        product = Product.objects.create(
            category=category,
            name="Portal item",
            slug="portal-item",
            price=Decimal("1"),
        )
        self.client.force_login(self.user_a)
        response = self.client.post(
            reverse("portal_wishlist_add", args=[product.pk]),
            {"next": "https://evil.example/"},
        )
        self.assertRedirects(response, product.get_absolute_url())

    def test_customer_sees_order_tracking_timeline(self):
        order = Order.objects.create(
            reference="ORD-PORTAL-TRACK",
            customer=self.customer_a,
            contact_name="A",
            contact_email="a@example.com",
            status=Order.STATUS_DISPATCHED,
        )
        OrderStatusEvent.objects.create(
            order=order,
            from_status=Order.STATUS_READY,
            to_status=Order.STATUS_DISPATCHED,
            note="On the way",
        )
        Shipment.objects.create(
            order=order,
            carrier="Courier",
            tracking_number="ABC123",
            status=Shipment.STATUS_IN_TRANSIT,
        )
        self.client.force_login(self.user_a)
        response = self.client.get(reverse("portal_order_detail", args=[order.pk]))
        self.assertContains(response, "ABC123")
        self.assertContains(response, "On the way")
