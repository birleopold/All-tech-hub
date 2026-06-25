from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from billing.models import (
    CommercialDocument,
    CommercialLine,
    DocumentPayment,
    allocate_document_number,
)
from catalog.models import Category, Product
from crm.models import Customer


class ReportAccessTests(TestCase):
    def test_export_requires_staff(self):
        response = self.client.get(reverse("staff_export_orders_csv"))
        self.assertEqual(response.status_code, 404)

    def test_staff_export_is_csv(self):
        user = User.objects.create_user("reporter", password="pw", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse("staff_export_orders_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))

    def test_report_contains_fulfillment_summary(self):
        user = User.objects.create_user("analyst", password="pw", is_staff=True)
        self.client.force_login(user)
        response = self.client.get(reverse("staff_reports"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("fulfillment_counts", response.context)

    def test_report_contains_phase_three_bi_metrics(self):
        user = User.objects.create_user("bi-analyst", password="pw", is_staff=True)
        customer = Customer.objects.create(name="BI Customer", email="bi@example.com")
        category = Category.objects.create(name="BI", slug="bi")
        product = Product.objects.create(
            category=category,
            name="BI Router",
            slug="bi-router",
            price=Decimal("120.00"),
            stock_quantity=5,
        )
        document = CommercialDocument.objects.create(
            doc_type=CommercialDocument.TYPE_INVOICE,
            number=allocate_document_number("INV"),
            customer=customer,
            status=CommercialDocument.STATUS_ISSUED,
            issue_date=timezone.localdate(),
            due_date=timezone.localdate(),
            subtotal=Decimal("120.00"),
            total=Decimal("120.00"),
        )
        CommercialLine.objects.create(
            document=document,
            product=product,
            description="BI Router",
            quantity=Decimal("1"),
            unit_price=Decimal("120.00"),
            unit_cost=Decimal("80.00"),
        )
        DocumentPayment.objects.create(
            document=document,
            amount=Decimal("20.00"),
            method=DocumentPayment.METHOD_MOBILE_MONEY,
            recorded_by=user,
        )
        self.client.force_login(user)
        response = self.client.get(reverse("staff_reports"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("document_margin_30", response.context)
        self.assertEqual(response.context["document_margin_30"]["profit"], Decimal("40.00"))
        self.assertEqual(response.context["payment_exceptions"]["unreconciled_count"], 1)
        self.assertContains(response, "Gross profit (30d)")
