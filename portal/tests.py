from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from billing.models import CommercialDocument
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


class PortalInvoicePaymentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "portal-payer", password="pw", email="payer@example.com"
        )
        self.customer = Customer.objects.create(
            name="Portal payer", email="payer@example.com", user=self.user
        )
        self.other_user = User.objects.create_user("portal-other", password="pw")
        self.other_customer = Customer.objects.create(
            name="Other customer", email="other@example.com", user=self.other_user
        )
        self.invoice = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number="INV-PORTAL-PAY-1",
            customer=self.customer,
            customer_name=self.customer.name,
            status=CommercialDocument.STATUS_ISSUED,
            total=Decimal("85000.00"),
        )

    def test_customer_can_open_secure_payment_page_for_own_invoice(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("portal_document_payment", args=[self.invoice.pk])
        )
        self.invoice.refresh_from_db()
        self.assertIsNotNone(self.invoice.payment_request_token)
        self.assertRedirects(
            response,
            reverse(
                "payment_request_portal",
                kwargs={"token": self.invoice.payment_request_token},
            ),
        )

    def test_customer_cannot_generate_link_for_someone_elses_invoice(self):
        self.client.force_login(self.other_user)
        response = self.client.post(
            reverse("portal_document_payment", args=[self.invoice.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.invoice.refresh_from_db()
        self.assertIsNone(self.invoice.payment_request_token)

    def test_invoice_list_shows_balance_and_pay_action(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("portal_documents"))
        self.assertContains(response, "INV-PORTAL-PAY-1")
        self.assertContains(response, "Pay")
        self.assertContains(response, "85000.00")

    def test_cancelled_invoice_cannot_be_paid(self):
        self.invoice.status = CommercialDocument.STATUS_CANCELLED
        self.invoice.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("portal_document_payment", args=[self.invoice.pk])
        )
        self.assertRedirects(response, reverse("portal_documents"))
        self.invoice.refresh_from_db()
        self.assertIsNone(self.invoice.payment_request_token)
