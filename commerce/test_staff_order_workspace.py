from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from commerce.models import Order
from crm.models import Customer


class StaffOrderWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("order-staff", password="pw", is_staff=True)
        cls.customer = Customer.objects.create(
            name="Workspace Customer",
            email="workspace-customer@example.com",
            phone="0700000000",
        )
        cls.pending_order = Order.objects.create(
            reference="ORD-WORKSPACE-1",
            customer=cls.customer,
            status=Order.STATUS_PENDING,
            contact_name=cls.customer.name,
            contact_email=cls.customer.email,
            contact_phone=cls.customer.phone,
            total=Decimal("150000"),
        )
        cls.dispatched_order = Order.objects.create(
            reference="ORD-WORKSPACE-2",
            customer=cls.customer,
            status=Order.STATUS_DISPATCHED,
            contact_name=cls.customer.name,
            contact_email=cls.customer.email,
            contact_phone=cls.customer.phone,
            total=Decimal("250000"),
        )

    def setUp(self):
        self.client.force_login(self.user)

    def test_order_workspace_renders_metrics_and_status_pills(self):
        response = self.client.get(reverse("staff_orders"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["order_stats"]["total"], 2)
        self.assertEqual(response.context["order_stats"]["active"], 2)
        self.assertEqual(response.context["order_stats"]["dispatched"], 1)
        self.assertContains(response, "Sales operations")
        self.assertContains(response, "staff-summary-grid")
        self.assertContains(response, "staff-status-pill--warning")
        self.assertContains(response, "staff-status-pill--primary")

    def test_order_workspace_searches_customer_and_reference(self):
        by_customer = self.client.get(reverse("staff_orders"), {"q": "Workspace Customer"})
        by_reference = self.client.get(reverse("staff_orders"), {"q": "ORD-WORKSPACE-2"})

        self.assertEqual(by_customer.context["paginator"].count, 2)
        self.assertEqual(by_reference.context["paginator"].count, 1)
        self.assertContains(by_reference, "ORD-WORKSPACE-2")
        self.assertNotContains(by_reference, "ORD-WORKSPACE-1")
