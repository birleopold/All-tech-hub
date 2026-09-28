"""The same sale remains coherent across staff views and permission levels."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from billing.models import CommercialDocument, CommercialLine, DocumentPayment
from catalog.models import Category, Product
from commerce.models import Order
from commerce.stock import decrement_line_stock
from core.models import ContactMessage
from crm.models import Customer
from inventory.models import StockMovement


class BusinessJourneyTests(TestCase):
    def test_enquiry_quote_sale_payment_and_stock_are_visible_in_the_right_places(self):
        owner = get_user_model().objects.create_user(
            "journey-owner", is_staff=True, is_superuser=True
        )
        customer = Customer.objects.create(name="Journey Buyer", email="journey@example.com")
        product = Product.objects.create(
            category=Category.objects.create(name="Journey", slug="journey"),
            name="Journey Router", slug="journey-router", kind=Product.KIND_PHYSICAL,
            price=Decimal("100.00"), stock_quantity=5, track_inventory=True,
        )
        ContactMessage.objects.create(
            name=customer.name, email=customer.email, product=product,
            subject="Router enquiry", message="Please quote one router.",
        )
        quote = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_QUOTE, number="QUO-JOURNEY",
            customer=customer, customer_name=customer.name, total=Decimal("100.00"),
        )
        order = Order.objects.create(
            reference="ORD-JOURNEY", customer=customer, contact_name=customer.name,
            contact_email=customer.email, subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
        )
        order.lines.create(product=product, description=product.name,
                           quantity=1, unit_price=Decimal("100.00"))
        decrement_line_stock(product=product, variant=None, qty=1, reference=order.reference)
        invoice = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE, number="INV-JOURNEY",
            customer=customer, customer_name=customer.name, order=order,
            source_document=quote, status=CommercialDocument.STATUS_PARTIALLY_PAID,
            total=Decimal("100.00"), amount_paid=Decimal("40.00"),
        )
        CommercialLine.objects.create(
            document=invoice, product=product, description=product.name,
            quantity=1, unit_price=Decimal("100.00"), unit_cost=Decimal("60.00"),
        )
        DocumentPayment.objects.create(document=invoice, amount=Decimal("40.00"),
                                       method=DocumentPayment.METHOD_CASH)

        self.client.force_login(owner)
        dashboard = self.client.get(reverse("staff_dashboard"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.context["payments_recorded_7d"], Decimal("40.00"))
        self.assertEqual(dashboard.context["receivables_balance"], Decimal("60.00"))
        self.assertEqual(dashboard.context["order_value_7d"], Decimal("100.00"))

        profile = self.client.get(reverse("staff_customer_detail", args=[customer.pk]))
        self.assertContains(profile, "ORD-JOURNEY")
        self.assertContains(profile, "QUO-JOURNEY")
        self.assertContains(profile, "INV-JOURNEY")
        self.assertContains(profile, "Router enquiry")
        self.assertEqual(profile.context["outstanding_balance"], Decimal("60.00"))

        product_review = self.client.get(reverse("staff_product_commercial_review", args=[product.pk]))
        self.assertEqual(product_review.status_code, 200)
        self.assertEqual(product_review.context["product_sales"]["units"], 1)
        self.assertEqual(product_review.context["product_margin"]["profit"], Decimal("40.00"))
        product.refresh_from_db()
        self.assertEqual(product.stock_quantity, 4)
        self.assertTrue(StockMovement.objects.filter(product=product, reference=order.reference).exists())

        restricted = get_user_model().objects.create_user("journey-limited", is_staff=True)
        self.client.force_login(restricted)
        search = self.client.get(reverse("staff_search"), {"q": "JOURNEY"})
        self.assertEqual(search.status_code, 200)
        self.assertNotContains(search, "INV-JOURNEY")
        self.assertNotContains(search, "ORD-JOURNEY")
        private_dashboard = self.client.get(reverse("staff_dashboard"))
        self.assertNotContains(private_dashboard, "Outstanding invoices")
        self.assertNotContains(private_dashboard, "ORD-JOURNEY")
